"""Round1 — five school candidate pools (MVP: S3/S4 real-enough; S1/S2/S5 fail-closed stubs)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..secondary_pick import select_secondary

SCHOOL_IDS: tuple[str, ...] = ("S1", "S2", "S3", "S4", "S5")

SCHOOL_NAMES: dict[str, str] = {
    "S1": "宏观/择时",
    "S2": "事件/主题",
    "S3": "质量/防守",
    "S4": "短线动量",
    "S5": "资金流/流动性",
}

# Default holding periods for rule-filled structured reasons.
_HOLDING: dict[str, str] = {
    "S1": "5–15 交易日",
    "S2": "3–10 交易日",
    "S3": "10–20 交易日",
    "S4": "2–5 交易日",
    "S5": "5–10 交易日",
}


def _row_code(row: Mapping[str, Any]) -> str:
    for key in ("code", "symbol", "ts_code"):
        raw = row.get(key)
        if raw is None or raw == "":
            continue
        s = str(raw).strip().upper()
        digits = "".join(ch for ch in s if ch.isdigit())
        if len(digits) >= 6:
            return digits[-6:]
        if digits:
            return digits.zfill(6)
    return ""


def _candidate(
    row: Mapping[str, Any],
    *,
    school: str,
    score: float,
    reason_seed: str,
) -> dict[str, Any]:
    code = _row_code(row)
    name = str(row.get("name") or "").strip() or code
    industry = str(row.get("industry") or row.get("sector") or "").strip() or None
    return {
        "code": code,
        "name": name,
        "school": school,
        "schoolName": SCHOOL_NAMES.get(school, school),
        "score": float(score),
        "industry": industry,
        "holdingPeriod": _HOLDING.get(school, "5–10 交易日"),
        "trigger": reason_seed,
        "expectation": f"相对同校池在评分窗口内排名靠前（规则预期；学校 {school}）",
        "invalidation": "跌破硬闸条件，或评分所需字段缺失 / 学校池撤销",
        "excludedFromPerformance": True,
        "sourceFields": {
            k: row.get(k)
            for k in ("amount", "rev_chg", "rs20", "vol20", "pct_chg", "composite_score")
            if k in row
        },
    }


def _empty(school: str, reason: str) -> dict[str, Any]:
    return {
        "school": school,
        "schoolName": SCHOOL_NAMES.get(school, school),
        "status": "empty",
        "reason": reason,
        "candidates": [],
    }


def _from_secondary(
    items: Sequence[Mapping[str, Any]] | None,
    *,
    school: str,
    profile: str,
    top_k: int,
) -> dict[str, Any]:
    if not items:
        return _empty(school, "输入截面为空，学校池 fail-closed")
    result = select_secondary(list(items), profile=profile, top_k=top_k)  # type: ignore[arg-type]
    selected = result.get("selected") or []
    candidates: list[dict[str, Any]] = []
    for row in selected:
        seed = str(row.get("secondaryReason") or f"{SCHOOL_NAMES.get(school, school)}规则入选")
        score = float(row.get("secondaryScore") or row.get("composite_score") or 0.0)
        cand = _candidate(row, school=school, score=score, reason_seed=seed)
        if cand["code"]:
            candidates.append(cand)
    note = (result.get("stats") or {}).get("note")
    if not candidates:
        return _empty(
            school,
            note or "二次精选后无入选；空池合法",
        )
    return {
        "school": school,
        "schoolName": SCHOOL_NAMES.get(school, school),
        "status": "ok",
        "reason": note,
        "candidates": candidates,
        "profile": result.get("profile"),
    }


def school_s1_macro(universe: Sequence[Mapping[str, Any]] | None, **_: Any) -> dict[str, Any]:
    """Stub: needs regime / timing series — fail-closed empty when absent."""
    _ = universe
    return _empty("S1", "MVP 未接入宏观/择时数据源；fail-closed 空池")


def school_s2_theme(universe: Sequence[Mapping[str, Any]] | None, **_: Any) -> dict[str, Any]:
    """Stub: theme/event signals must pass FACTOR_LIBRARY before production weights."""
    _ = universe
    return _empty(
        "S2",
        "MVP 未接入已准入主题因子；未过 FACTOR_LIBRARY 的信号不得进生产权重",
    )


def school_s3_quality(
    universe: Sequence[Mapping[str, Any]] | None,
    *,
    top_k: int = 8,
    **_: Any,
) -> dict[str, Any]:
    """Quality/defensive pool via secondary_pick quality profile (lvrev-adjacent)."""
    return _from_secondary(universe, school="S3", profile="quality", top_k=top_k)


def school_s4_short(
    universe: Sequence[Mapping[str, Any]] | None,
    *,
    top_k: int = 8,
    **_: Any,
) -> dict[str, Any]:
    """Short momentum via secondary_pick short weights."""
    return _from_secondary(universe, school="S4", profile="short", top_k=top_k)


def school_s5_flow(universe: Sequence[Mapping[str, Any]] | None, **_: Any) -> dict[str, Any]:
    """Stub: fund-flow / liquidity structure — empty when flow columns missing."""
    rows = [r for r in (universe or []) if isinstance(r, Mapping)]
    has_flow = any(
        r.get("main_net_inflow") is not None or r.get("fund_flow") is not None for r in rows
    )
    if not has_flow:
        return _empty("S5", "缺资金流字段（main_net_inflow / fund_flow）；fail-closed 空池")
    # Future: rank by flow; MVP still empty with explicit reason when thin.
    return _empty("S5", "MVP 资金流排序未启用；有字段亦不入选（故意薄骨架）")


_SCHOOL_RUNNERS = {
    "S1": school_s1_macro,
    "S2": school_s2_theme,
    "S3": school_s3_quality,
    "S4": school_s4_short,
    "S5": school_s5_flow,
}


def run_round1(
    universe: Sequence[Mapping[str, Any]] | None,
    *,
    top_k: int = 8,
) -> dict[str, dict[str, Any]]:
    """Run all five schools; returns mapping school_id → pool payload."""
    out: dict[str, dict[str, Any]] = {}
    for sid in SCHOOL_IDS:
        runner = _SCHOOL_RUNNERS[sid]
        out[sid] = runner(universe, top_k=top_k)
    return out


__all__ = [
    "SCHOOL_IDS",
    "SCHOOL_NAMES",
    "run_round1",
    "school_s1_macro",
    "school_s2_theme",
    "school_s3_quality",
    "school_s4_short",
    "school_s5_flow",
]
