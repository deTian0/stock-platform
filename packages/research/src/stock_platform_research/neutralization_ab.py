"""Industry-neutralization A/B — two arms through the **same** engine (milestone ``S4``).

The acceptance criterion for ``S4`` is *「回测对照有中性化前后差异」*: the
neutralized book must be compared against the un-neutralized book **by the same
engine**, so the difference is attributable to neutralization and nothing else.

- **arm A (``raw``)**     — the pre-``S4`` book: ``score_lvrev`` without neutralization.
- **arm B (``neutral``)** — the same loop with ``neutralize`` set, plus an optional
  ``max_per_industry`` candidate cap (the exposure constraint).

Both arms consume the *same* feature frame and the *same*
:func:`book_replay.replay_book` loop (the ``X4`` single definition), so the two
equity curves differ only by the treatment. ``delta = neutral − raw`` needs no
re-normalisation; the ``sameDefinition`` identity block proves it.

The payload also carries an **industry exposure** profile per arm (equal-weighted
across every code the arm actually picked) — the concentration metric that makes
"did neutralization reduce a sector bet?" answerable at a glance.

``delta`` / ``review`` / ``sameDefinition`` are imported from
:mod:`strategy_ab` rather than re-implemented, so the ``S1`` and ``S4`` A/Bs
report on one contract. SIMULATE only; off the brief / picks path; not investment
advice.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

import pandas as pd

from .backtest import prepare_book_frame
from .book_replay import ReplayParams, replay_book, screener_entry_provider
from .neutralization import NeutralizeParams, attach_industry, industry_exposure
from .portfolio import compute_metrics
from .strategy_ab import (  # single definition — the A/B contract is S1's
    AB_METRIC_KEYS,
    _delta_metrics,
    _review_block,
    _same_definition,
)

#: The two arms of the comparison, in delta order (``delta = neutral − raw``).
NEUTRALIZATION_ARMS = ("raw", "neutral")


def _industry_lookup(feats: pd.DataFrame, col: str) -> dict[str, str] | None:
    if col not in feats.columns:
        return None
    return dict(zip(feats["code"].astype(str), feats[col].astype(str)))


def _picked_codes(loop: Mapping[str, Any]) -> list[str]:
    """Every distinct code the arm actually held (closed trades + still open)."""
    seen: list[str] = []
    known: set[str] = set()
    for row in list(loop.get("trades") or []) + list(loop.get("open_positions") or []):
        code = str(row.get("code"))
        if code not in known:
            known.add(code)
            seen.append(code)
    return seen


def run_neutralization_book(
    feats: pd.DataFrame,
    *,
    neutralize: NeutralizeParams | None = None,
    params: ReplayParams | None = None,
    max_per_industry: int | None = None,
    min_pick_score: float = 0.80,
    weights: Mapping[str, float] | None = None,
    gate_params: Any = None,
    value_factor: bool = False,
    reversal_q: float | None = None,
) -> dict[str, Any]:
    """Replay one arm through the shared loop and attach metrics + exposure.

    ``neutralize=None`` reproduces the pre-``S4`` screener book exactly (the frame
    is only read, never rewritten).
    """
    provider = screener_entry_provider(
        reversal_q=reversal_q,
        min_pick_score=min_pick_score,
        value_factor=value_factor,
        weights=weights,
        gate_params=gate_params,
        neutralize=neutralize,
        max_per_industry=max_per_industry,
    )
    loop = replay_book(feats, entry_provider=provider, params=params)
    initial = (params or ReplayParams()).initial_capital
    col = neutralize.industry_col if neutralize is not None else "industry"
    return {
        "ok": True,
        "equity_curve": loop["equity_curve"],
        "trades": loop["trades"],
        "open_positions": loop.get("open_positions") or [],
        "n_days": loop["n_days"],
        "final_equity": loop["final_equity"],
        "initial_capital": loop["initial_capital"],
        "metrics": compute_metrics(
            loop["equity_curve"], loop["trades"], initial_capital=initial
        ),
        "review": _review_block(loop["trades"], loop.get("open_positions")),
        "picksExposure": industry_exposure(
            _picked_codes(loop), _industry_lookup(feats, col)
        ),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "disclaimer": "Research only; not investment advice.",
    }


def _arm_block(arm: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "finalEquity": arm.get("final_equity"),
        "tradeCount": len(arm.get("trades") or []),
        "metrics": arm.get("metrics"),
        "review": arm.get("review"),
        "picksExposure": arm.get("picksExposure"),
        "equityCurve": arm.get("equity_curve"),
    }


def _pick_winner(m_raw: Mapping[str, Any], m_neu: Mapping[str, Any]) -> str:
    """Sharpe first (when both arms traded), else final equity; ``"tie"`` otherwise."""
    if m_raw.get("n_trades") and m_neu.get("n_trades"):
        s_raw = float(m_raw.get("sharpe") or 0.0)
        s_neu = float(m_neu.get("sharpe") or 0.0)
        if s_neu > s_raw:
            return "neutral"
        if s_raw > s_neu:
            return "raw"
    f_raw = float(m_raw.get("final_equity") or 0.0)
    f_neu = float(m_neu.get("final_equity") or 0.0)
    if f_neu > f_raw:
        return "neutral"
    if f_raw > f_neu:
        return "raw"
    return "tie"


def compare_neutralization_ab(
    feats: pd.DataFrame,
    *,
    neutralize: NeutralizeParams | None = None,
    industry_map: Mapping[str, str] | None = None,
    params: ReplayParams | None = None,
    max_per_industry: int | None = None,
    min_pick_score: float = 0.80,
    weights: Mapping[str, float] | None = None,
    value_factor: bool = False,
    reversal_q: float | None = None,
) -> dict[str, Any]:
    """Compare the raw book against the industry-neutral book on one screen.

    ``industry_map`` (``code → industry``) is attached to the frame when given;
    otherwise the frame must already carry the ``neutralize.industry_col`` column.
    An unknown industry degrades to a global de-mean (see
    :mod:`neutralization`) — never a crash.
    """
    neu = neutralize if neutralize is not None else NeutralizeParams()
    frame = feats
    if industry_map is not None:
        frame = attach_industry(feats, industry_map, col=neu.industry_col)

    common = dict(
        params=params,
        min_pick_score=min_pick_score,
        weights=weights,
        value_factor=value_factor,
        reversal_q=reversal_q,
    )
    raw = run_neutralization_book(frame, neutralize=None, **common)
    neutral = run_neutralization_book(
        frame, neutralize=neu, max_per_industry=max_per_industry, **common
    )

    has_industry = neu.industry_col in frame.columns
    out: dict[str, Any] = {
        "ok": True,
        "neutralize": asdict(neu),
        "maxPerIndustry": max_per_industry,
        "industryColumn": neu.industry_col,
        "industryAvailable": bool(has_industry),
        "nIndustries": int(frame[neu.industry_col].nunique()) if has_industry else 0,
        "minPickScore": min_pick_score,
        "a": _arm_block(raw),
        "b": _arm_block(neutral),
        "delta": _delta_metrics(raw.get("metrics") or {}, neutral.get("metrics") or {}),
        "winner": _pick_winner(raw.get("metrics") or {}, neutral.get("metrics") or {}),
        "exposure": {
            "raw": raw.get("picksExposure"),
            "neutral": neutral.get("picksExposure"),
        },
        "sameDefinition": _same_definition(),
        "replacesPicks": False,
        "panelSource": "engine",
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "metaKeys": list(AB_METRIC_KEYS),
        "metricNote": (
            "两臂同一帧、同一引擎（book_replay 单点定义）；delta = 中性化 − 原始，"
            "同口径无需二次归一。"
        ),
        "disclaimer": (
            "行业中性化 A/B 同源对照（研究指标）；非投资建议；SIMULATE；"
            "不改主路径权重与 picks。"
        ),
    }
    if not has_industry:
        out["warning"] = (
            f"frame 无 {neu.industry_col!r} 列：中性化退化为全局去均值，"
            "行业口径不可用（请传 industry_map 或先 attach_industry）。"
        )
    if not (out["a"]["metrics"] or {}).get("n_trades") or not (
        out["b"]["metrics"] or {}
    ).get("n_trades"):
        out["winnerNote"] = (
            "有一臂零成交，胜负仅供参考（零成交臂既未暴露风险也未产生收益）。"
        )
    return out


def neutralization_ab_from_bars(
    bars: pd.DataFrame,
    *,
    neutralize: NeutralizeParams | None = None,
    industry_map: Mapping[str, str] | None = None,
    universe: str = "stock",
    start: str | None = None,
    end: str | None = None,
    pct_scale: str = "auto",
    params: ReplayParams | None = None,
    max_per_industry: int | None = None,
    min_pick_score: float = 0.80,
    weights: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """``bars`` → shared feature frame (+ industry join) → engine A/B (CLI / API).

    Fail-closed: an empty frame returns ``ok=False`` with a reason rather than two
    zero-filled curves.
    """
    feats = prepare_book_frame(
        bars,
        universe=universe,
        start=start,
        end=end,
        pct_scale=pct_scale,
        industry_map=industry_map,
    )
    if feats.empty:
        return {
            "ok": False,
            "reason": "no bars in range",
            "universe": universe,
            "start": start,
            "end": end,
            "environment": "SIMULATE",
            "liveTradingEnabled": False,
            "disclaimer": "Research only; not investment advice.",
        }
    out = compare_neutralization_ab(
        feats,
        neutralize=neutralize,
        params=params,
        max_per_industry=max_per_industry,
        min_pick_score=min_pick_score,
        weights=weights,
    )
    out["universe"] = universe
    out["start"] = start
    out["end"] = end
    return out


__all__ = [
    "NEUTRALIZATION_ARMS",
    "compare_neutralization_ab",
    "neutralization_ab_from_bars",
    "run_neutralization_book",
]
