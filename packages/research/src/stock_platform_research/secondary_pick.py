"""Display-only secondary pick. Does not change scores, picks, or positions.

Thresholds were calibrated on the 2026-10-27 cross-section: the engine's
lvrev kernel selects names below MA20 by construction, so an absolute
MA20 floor would reject the whole board. Liquidity is a hard floor at a
token amount only; everything else is relative scoring.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping

import pandas as pd

Profile = Literal["quality", "short"]

AMOUNT_MIN = 10_000_000
QUALITY_REV_FLOOR = -0.25
SHORT_REV_FLOOR = -0.15

QUALITY_WEIGHTS: dict[str, float] = {
    "波动稳健": 0.40,
    "反转适度": 0.30,
    "趋势位置": 0.20,
    "流动性": 0.10,
}
SHORT_WEIGHTS: dict[str, float] = {
    "动量": 0.45,
    "量能": 0.30,
    "波动活跃": 0.25,
}

PROFILE_TREND = {
    "quality": "长线选稳：低波动 + 反转钟形（靠近 −10% 最佳）+ 贴近 MA20",
    "short": "短线选势：20 日动量占优 + 量能活跃 + 中高波动",
}

_TOO_FEW = "可评分样本不足 2，不做有效排名"


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out:
        return None
    return out


def _bell(value: float, center: float, halfwidth: float) -> float:
    if halfwidth <= 0:
        return 0.0
    return max(0.0, 1.0 - abs(value - center) / halfwidth)


def _pct_rank(values: list[float], *, higher_better: bool) -> list[float]:
    series = pd.Series(values, dtype="float64")
    if not higher_better:
        series = -series
    return [float(v) for v in series.rank(pct=True, method="average").tolist()]


def _is_st(name: str) -> bool:
    return "ST" in name.upper()


def _gate(row: Mapping[str, Any], profile: Profile) -> str | None:
    """Return a rejection reason, or None when the row may be scored."""
    name = str(row.get("name") or "").strip()
    if not name:
        return "缺 name，不参与二次精选"
    if _is_st(name):
        if profile == "short":
            return "风险警示股，短线不参与"
        return "风险警示股，二次精选剔除"

    amount = _num(row.get("amount"))
    if amount is None:
        return "缺 amount，不参与二次精选"
    if amount < AMOUNT_MIN:
        return f"成交额低于 {AMOUNT_MIN // 10_000} 万元"

    rev = _num(row.get("rev_chg"))
    if rev is None:
        return "缺 rev_chg，不参与二次精选"
    if profile == "quality" and rev < QUALITY_REV_FLOOR:
        return "20 日收益低于 −25%"
    if profile == "short" and rev < SHORT_REV_FLOOR:
        return "20 日收益低于 −15%"

    if _num(row.get("rs20")) is None:
        return "缺 rs20，不参与二次精选"

    if _num(row.get("vol20")) is None:
        return "缺 vol20，不参与二次精选"
    return None


def _dimension_scores(rows: list[Mapping[str, Any]], profile: Profile) -> list[dict[str, float]]:
    vol = [float(_num(r.get("vol20"))) for r in rows]  # type: ignore[arg-type]
    rev = [float(_num(r.get("rev_chg"))) for r in rows]  # type: ignore[arg-type]
    rs = [float(_num(r.get("rs20"))) for r in rows]  # type: ignore[arg-type]
    amt = [float(_num(r.get("amount"))) for r in rows]  # type: ignore[arg-type]
    if profile == "quality":
        vol_score = _pct_rank(vol, higher_better=False)
        amt_score = _pct_rank(amt, higher_better=True)
        pos_score = _pct_rank([abs(x) for x in rs], higher_better=False)  # 离 MA20 越近越好
        out = []
        for i in range(len(rows)):
            out.append(
                {
                    "波动稳健": vol_score[i],
                    "反转适度": _bell(rev[i], -0.10, 0.15),
                    "趋势位置": pos_score[i],
                    "流动性": amt_score[i],
                }
            )
        return out

    amt_score = _pct_rank(amt, higher_better=True)
    momentum = _pct_rank(rev, higher_better=True)  # 20 日收益越高越强
    vol_pct = _pct_rank(vol, higher_better=True)
    out = []
    for i in range(len(rows)):
        p = vol_pct[i]
        if 0.50 <= p <= 0.90:
            active = 1.0
        else:
            distance = (0.50 - p) if p < 0.50 else (p - 0.90)
            active = max(0.0, 1.0 - distance / 0.50)
        out.append(
            {
                "动量": momentum[i],
                "量能": amt_score[i],
                "波动活跃": active,
            }
        )
    return out


def _weights(profile: Profile) -> dict[str, float]:
    return QUALITY_WEIGHTS if profile == "quality" else SHORT_WEIGHTS


def _total(scores: Mapping[str, float], profile: Profile) -> float:
    return sum(scores[name] * weight for name, weight in _weights(profile).items())


def _reason(row: Mapping[str, Any], scores: Mapping[str, float], profile: Profile) -> str:
    weights = _weights(profile)
    ranked = sorted(scores, key=lambda name: scores[name] * weights[name], reverse=True)
    parts = [_phrase(row, name, profile) for name in ranked[:2]]
    return " + ".join(parts)


def _phrase(row: Mapping[str, Any], dimension: str, profile: Profile) -> str:
    vol = _num(row.get("vol20"))
    rev = _num(row.get("rev_chg"))
    rs20 = _num(row.get("rs20"))
    amount = _num(row.get("amount"))
    if dimension == "波动稳健" and vol is not None:
        return f"20 日波动 {vol * 100:.2f}%，全组越低越优"
    if dimension == "反转适度" and rev is not None:
        return f"20 日收益 {rev * 100:+.1f}%，落在 −10% 弹性最优区间"
    if dimension == "趋势位置" and rs20 is not None:
        return f"收盘较 MA20 {rs20:+.1f}%（全组最贴近均线）"
    if dimension == "流动性" and amount is not None:
        return f"成交额 {amount / 1e8:.2f} 亿元"
    if dimension == "动量" and rev is not None:
        return f"20 日收益 {rev * 100:+.1f}%，全组动量靠前"
    if dimension == "量能" and amount is not None:
        return f"成交额 {amount / 1e8:.2f} 亿元"
    if dimension == "波动活跃" and vol is not None:
        return f"20 日波动 {vol * 100:.2f}%，处于中高活跃区间"
    return dimension


def select_secondary(
    items: list[Mapping[str, Any]] | None,
    *,
    profile: Profile,
    top_k: int = 5,
) -> dict[str, Any]:
    """Pick up to ``top_k`` rows. Missing fields reject the row; weights are not renormalized."""
    rows = [dict(r) for r in (items or []) if isinstance(r, Mapping)]
    rejected: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for row in rows:
        reason = _gate(row, profile)
        if reason:
            rejected.append({**row, "rejectReason": reason})
        else:
            candidates.append(row)

    note = None
    selected: list[dict[str, Any]] = []
    if len(candidates) < 2:
        note = _TOO_FEW
        for row in candidates:
            rejected.append({**row, "rejectReason": note})
    else:
        scored = _dimension_scores(candidates, profile)
        ranked = []
        for index, (row, scores) in enumerate(zip(candidates, scored)):
            total = _total(scores, profile)
            ranked.append((total, index, row, scores))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        keep = max(int(top_k), 0)
        for total, _index, row, scores in ranked[:keep]:
            selected.append(
                {
                    **row,
                    "secondaryScore": total,
                    "dimensionScores": scores,
                    "secondaryReason": _reason(row, scores, profile),
                }
            )
        for _score, _index, row, _scores in ranked[keep:]:
            rejected.append({**row, "rejectReason": f"二次精选得分未进入前 {keep}"})
        if len(candidates) < keep:
            note = f"剔除后仅 {len(candidates)} 只符合条件，按规则不补齐"

    return {
        "selected": selected,
        "rejected": rejected,
        "stats": {
            "input": len(rows),
            "selected": len(selected),
            "scoreable": 0 if note == _TOO_FEW else len(candidates),
            "note": note,
            "profile": profile,
        },
        "profile": {
            "name": profile,
            "weights": dict(_weights(profile)),
            "trend": PROFILE_TREND[profile],
        },
    }


__all__ = [
    "AMOUNT_MIN",
    "PROFILE_TREND",
    "QUALITY_REV_FLOOR",
    "QUALITY_WEIGHTS",
    "SHORT_REV_FLOOR",
    "SHORT_WEIGHTS",
    "select_secondary",
]
