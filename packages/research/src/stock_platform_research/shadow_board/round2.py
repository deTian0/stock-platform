"""Round2 Set A — deterministic hard gates + school-priority arbitration.

Arbitration modes (experiment knob, ADR pending)
-------------------------------------------------
``apply_round2_set_a(..., arbitration=...)`` selects *how the surviving names are
ordered / allocated into the board seats*. The hard gates (ST, liquidity,
limit-up seal, industry concentration cap, seat cap) are **identical** in every
mode — a mode can only change ordering and membership among names that already
passed every hard gate.

====== ===================================================================
Mode   Behaviour
====== ===================================================================
``d``  **Factory default.** Order = ``(school priority, -score, code)``.
       School priority outranks score, so ``S3``'s whole pool precedes
       ``S4``'s, etc. Byte-identical to the pre-knob implementation.
``a``  Priority is used **only** for same-code dedupe (contract §2 literal).
       Board order = within-school score percentile (descending), then
       priority, then code. Cross-school raw scores are not comparable, so
       they are normalised per school before ranking.
``b``  ``d`` plus a floor: every school with at least one survivor gets up
       to ``min_seats`` reserved seats at the front of the board (walking
       down the school's list if its best name hits the industry cap), then
       the remaining seats are filled by the ``d`` rule.
====== ===================================================================

Board **order** is material downstream: the replay loop buys only the first
``max_picks_per_day`` rows of the board, so a mode that merely appends reserved
seats at the tail would not actually give the weak schools forward samples.
Mode ``b`` therefore puts the reserved seats first (in school-priority order).

No mode may pad to N: an empty board stays empty.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..rules import is_limit_up
from ..secondary_pick import AMOUNT_MIN

# Higher index wins on same-code conflicts (contract §2).
SCHOOL_PRIORITY: tuple[str, ...] = ("S3", "S4", "S5", "S2", "S1")
_PRIORITY_RANK = {sid: i for i, sid in enumerate(SCHOOL_PRIORITY)}

MAX_PER_INDUSTRY = 2
MAX_BOARD_SIZE = 10  # soft cap after hard filters — not pad-to-N

#: Experiment knob; ``d`` is the factory default and must stay so until an ADR
#: is signed off (see docs/plans/multi-strategy-final-board.md §11).
ARBITRATION_MODES: tuple[str, ...] = ("d", "a", "b")
DEFAULT_ARBITRATION = "d"
#: Reserved seats per non-empty school in mode ``b``.
DEFAULT_MIN_SEATS = 1


def _is_st(name: str) -> bool:
    return "ST" in (name or "").upper()


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out:  # NaN
        return None
    return out


def _hard_reject(cand: Mapping[str, Any]) -> str | None:
    """Return Chinese rejection reason, or None if the name may proceed."""
    code = str(cand.get("code") or "").strip()
    if not code:
        return "缺 code，硬闸剔除"
    name = str(cand.get("name") or "")
    if _is_st(name):
        return "风险警示股（ST），硬闸剔除"

    src = cand.get("sourceFields") if isinstance(cand.get("sourceFields"), Mapping) else {}
    amount = _num(cand.get("amount"))
    if amount is None:
        amount = _num(src.get("amount")) if isinstance(src, Mapping) else None
    if amount is None:
        return "缺成交额 amount，流动性硬闸 fail-closed"
    if amount < AMOUNT_MIN:
        return f"成交额低于 {AMOUNT_MIN // 10_000} 万元，流动性硬闸剔除"

    pct = _num(cand.get("pct_chg"))
    if pct is None and isinstance(src, Mapping):
        pct = _num(src.get("pct_chg"))
    if pct is not None and is_limit_up(code, pct, is_st=_is_st(name)):
        return "涨停密封，买入不可成交，硬闸剔除"

    return None


def _code(cand: Mapping[str, Any]) -> str:
    return str(cand.get("code") or "")


def _score(cand: Mapping[str, Any]) -> float:
    return float(cand.get("score") or 0.0)


def _industry(cand: Mapping[str, Any]) -> str:
    return str(cand.get("industry") or "").strip() or "_unknown"


def _rank(cand: Mapping[str, Any]) -> int:
    return _PRIORITY_RANK.get(str(cand.get("school")), 99)


def _board_row(cand: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "code": cand.get("code"),
        "name": cand.get("name"),
        "school": cand.get("school"),
        "schoolName": cand.get("schoolName"),
        "score": float(cand.get("score") or 0.0),
        "industry": cand.get("industry"),
        "holdingPeriod": cand.get("holdingPeriod"),
        "trigger": cand.get("trigger"),
        "expectation": cand.get("expectation"),
        "invalidation": cand.get("invalidation"),
        "excludedFromPerformance": True,
    }


def school_score_percentiles(candidates: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """``code → within-school score percentile`` in ``(0, 1]``, 1.0 = school best.

    Cross-school raw ``score`` values are not comparable (S3/S4 come from
    ``secondary_pick`` composites, S5 from an amount/illiq blend, S1 from an
    ``rs20`` offset), so mode ``a`` ranks on a scale-free statistic instead.
    A plain descending rank percentile ``(n − i) / n`` is used rather than a
    z-score: pools are tiny (``top_k`` is 8 by default), so a z-score would be
    dominated by one outlier, while the rank percentile only needs the ordering
    each school already asserts. Ties inside a school are impossible by
    construction (the ``(-score, code)`` sort is total).
    """
    by_school: dict[str, list[Mapping[str, Any]]] = {}
    for cand in candidates:
        by_school.setdefault(str(cand.get("school")), []).append(cand)
    out: dict[str, float] = {}
    for rows in by_school.values():
        ordered = sorted(rows, key=lambda c: (-_score(c), _code(c)))
        n = len(ordered)
        for i, cand in enumerate(ordered):
            out[_code(cand)] = (n - i) / n
    return out


def _ranked_order(
    candidates: Sequence[Mapping[str, Any]],
    *,
    arbitration: str,
) -> list[dict[str, Any]]:
    """Mode-specific board ordering over hard-gate survivors (deduped)."""
    rows = list(candidates)
    if arbitration == "a":
        pct = school_score_percentiles(rows)
        return sorted(
            rows,
            key=lambda c: (-pct.get(_code(c), 0.0), _rank(c), _code(c)),
        )
    # ``d`` and ``b`` share the factory ordering; ``b`` only adds a reserve pass.
    return sorted(rows, key=lambda c: (_rank(c), -_score(c), _code(c)))


def _reserve_groups(
    ranked: Sequence[Mapping[str, Any]],
) -> list[list[Mapping[str, Any]]]:
    """Mode ``b``: per-school survivor lists, schools in priority order.

    Each list keeps the mode ordering (best first). Only names that already
    cleared every hard gate are present, so a reserved seat can never smuggle a
    rejected name onto the board.
    """
    by_school: dict[str, list[Mapping[str, Any]]] = {}
    for cand in ranked:
        by_school.setdefault(str(cand.get("school")), []).append(cand)
    schools = sorted(by_school, key=lambda sid: (_PRIORITY_RANK.get(sid, 99), sid))
    return [by_school[sid] for sid in schools]


def apply_round2_set_a(
    school_pools: Mapping[str, Mapping[str, Any]],
    *,
    max_per_industry: int = MAX_PER_INDUSTRY,
    max_board_size: int = MAX_BOARD_SIZE,
    arbitration: str = DEFAULT_ARBITRATION,
    min_seats: int = DEFAULT_MIN_SEATS,
) -> dict[str, Any]:
    """Hard gates + school priority. Never pads to N; empty board is legal.

    ``arbitration`` defaults to ``"d"`` — the factory behaviour, bit-for-bit
    including the payload keys. Modes ``"a"`` / ``"b"`` are offline experiments
    (see the module docstring and ``docs/plans/multi-strategy-final-board.md``
    §11); they never relax a hard gate.
    """
    mode = str(arbitration or DEFAULT_ARBITRATION).strip().lower()
    if mode not in ARBITRATION_MODES:
        raise ValueError(f"arbitration must be one of {ARBITRATION_MODES}, got {arbitration!r}")

    flat: list[dict[str, Any]] = []
    for sid, pool in school_pools.items():
        for cand in pool.get("candidates") or []:
            if isinstance(cand, Mapping):
                row = dict(cand)
                row.setdefault("school", sid)
                flat.append(row)

    rejected: list[dict[str, Any]] = []
    survivors: list[dict[str, Any]] = []
    for cand in flat:
        reason = _hard_reject(cand)
        if reason:
            rejected.append(
                {
                    "code": cand.get("code"),
                    "name": cand.get("name"),
                    "school": cand.get("school"),
                    "reason": reason,
                }
            )
        else:
            survivors.append(cand)

    # Same-code conflict: keep highest school priority, then higher score.
    # This is the *only* place school priority is used in mode ``a``.
    by_code: dict[str, dict[str, Any]] = {}
    for cand in survivors:
        code = str(cand.get("code") or "")
        prev = by_code.get(code)
        if prev is None:
            by_code[code] = cand
            continue
        rank_new = _PRIORITY_RANK.get(str(cand.get("school")), 99)
        rank_old = _PRIORITY_RANK.get(str(prev.get("school")), 99)
        score_new = float(cand.get("score") or 0.0)
        score_old = float(prev.get("score") or 0.0)
        prefer_new = (rank_new < rank_old) or (rank_new == rank_old and score_new > score_old)
        if prefer_new:
            rejected.append(
                {
                    "code": prev.get("code"),
                    "name": prev.get("name"),
                    "school": prev.get("school"),
                    "reason": f"同票冲突：学校优先级仲裁保留 {cand.get('school')}",
                }
            )
            by_code[code] = cand
        else:
            rejected.append(
                {
                    "code": cand.get("code"),
                    "name": cand.get("name"),
                    "school": cand.get("school"),
                    "reason": f"同票冲突：学校优先级仲裁保留 {prev.get('school')}",
                }
            )

    ranked = _ranked_order(by_code.values(), arbitration=mode)

    # Industry concentration hard cap (+ seat cap) — same gates in every mode.
    industry_counts: dict[str, int] = {}
    passed: list[dict[str, Any]] = []
    chosen: set[str] = set()

    if mode == "b" and min_seats > 0:
        # Reserve pass: each non-empty school's best names go in first, walking
        # down the school's list until ``min_seats`` are taken. A name blocked by
        # the industry cap here is skipped — the main pass records its reason, so
        # no rejection is double-counted and no hard gate is bypassed.
        for group in _reserve_groups(ranked):
            taken = 0
            for cand in group:
                if taken >= min_seats or len(passed) >= max_board_size:
                    break
                code = _code(cand)
                if code in chosen:
                    continue
                ind = _industry(cand)
                if industry_counts.get(ind, 0) >= max_per_industry:
                    continue
                industry_counts[ind] = industry_counts.get(ind, 0) + 1
                chosen.add(code)
                passed.append(_board_row(cand))
                taken += 1

    for cand in ranked:
        if _code(cand) in chosen:
            continue
        ind = _industry(cand)
        if industry_counts.get(ind, 0) >= max_per_industry:
            rejected.append(
                {
                    "code": cand.get("code"),
                    "name": cand.get("name"),
                    "school": cand.get("school"),
                    "reason": f"行业/主题集中度上限（{ind} ≥ {max_per_industry}）",
                }
            )
            continue
        if len(passed) >= max_board_size:
            rejected.append(
                {
                    "code": cand.get("code"),
                    "name": cand.get("name"),
                    "school": cand.get("school"),
                    "reason": f"董事会席位上限 {max_board_size}（非凑满；超额落选）",
                }
            )
            continue
        industry_counts[ind] = industry_counts.get(ind, 0) + 1
        chosen.add(_code(cand))
        passed.append(_board_row(cand))

    out: dict[str, Any] = {
        "arbiter": "set_a",
        "rejected": rejected,
        "passed": passed,
        "stats": {
            "input": len(flat),
            "passed": len(passed),
            "rejected": len(rejected),
        },
    }
    if mode != DEFAULT_ARBITRATION:
        # Factory payload shape is untouched; experiment runs are self-describing.
        out["arbitration"] = mode
        if mode == "a":
            out["normalization"] = "school_score_percentile"
        if mode == "b":
            out["minSeats"] = int(min_seats)
    return out


def set_b_cannot_override_hard_reject(
    set_a_rejected: Sequence[Mapping[str, Any]],
    advisory_codes: Sequence[str] | None,
) -> list[str]:
    """Safety: any code hard-rejected by A must not appear as B 'pass' suggestions."""
    hard = {str(r.get("code") or "") for r in set_a_rejected}
    return [c for c in (advisory_codes or []) if c and c not in hard]


__all__ = [
    "ARBITRATION_MODES",
    "DEFAULT_ARBITRATION",
    "DEFAULT_MIN_SEATS",
    "MAX_BOARD_SIZE",
    "MAX_PER_INDUSTRY",
    "SCHOOL_PRIORITY",
    "apply_round2_set_a",
    "school_score_percentiles",
    "set_b_cannot_override_hard_reject",
]
