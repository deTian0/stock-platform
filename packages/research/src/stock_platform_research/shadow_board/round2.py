"""Round2 Set A — deterministic hard gates + school-priority arbitration."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..rules import is_limit_up
from ..secondary_pick import AMOUNT_MIN

# Higher index wins on same-code conflicts (contract §2).
SCHOOL_PRIORITY: tuple[str, ...] = ("S3", "S4", "S5", "S2", "S1")
_PRIORITY_RANK = {sid: i for i, sid in enumerate(SCHOOL_PRIORITY)}

MAX_PER_INDUSTRY = 2
MAX_BOARD_SIZE = 10  # soft cap after hard filters — not pad-to-N


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


def apply_round2_set_a(
    school_pools: Mapping[str, Mapping[str, Any]],
    *,
    max_per_industry: int = MAX_PER_INDUSTRY,
    max_board_size: int = MAX_BOARD_SIZE,
) -> dict[str, Any]:
    """Hard gates + school priority. Never pads to N; empty board is legal."""
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

    ranked = sorted(
        by_code.values(),
        key=lambda c: (
            _PRIORITY_RANK.get(str(c.get("school")), 99),
            -float(c.get("score") or 0.0),
            str(c.get("code") or ""),
        ),
    )

    # Industry concentration hard cap.
    industry_counts: dict[str, int] = {}
    passed: list[dict[str, Any]] = []
    for cand in ranked:
        ind = str(cand.get("industry") or "").strip() or "_unknown"
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
        passed.append(
            {
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
        )

    return {
        "arbiter": "set_a",
        "rejected": rejected,
        "passed": passed,
        "stats": {
            "input": len(flat),
            "passed": len(passed),
            "rejected": len(rejected),
        },
    }


def set_b_cannot_override_hard_reject(
    set_a_rejected: Sequence[Mapping[str, Any]],
    advisory_codes: Sequence[str] | None,
) -> list[str]:
    """Safety: any code hard-rejected by A must not appear as B 'pass' suggestions."""
    hard = {str(r.get("code") or "") for r in set_a_rejected}
    return [c for c in (advisory_codes or []) if c and c not in hard]


__all__ = [
    "MAX_BOARD_SIZE",
    "MAX_PER_INDUSTRY",
    "SCHOOL_PRIORITY",
    "apply_round2_set_a",
    "set_b_cannot_override_hard_reject",
]
