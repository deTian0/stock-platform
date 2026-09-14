"""Thin portfolio metrics on top of PIT long-only (ADR 0043).

Not a full quant platform: equal-weight day returns from ``run_pit_long_only``,
approx turnover from ``n_picks`` changes, max drawdown from the equity curve.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import pandas as pd

from .pit import run_pit_long_only


def max_drawdown_from_curve(equity_curve: Sequence[Mapping[str, Any]]) -> float:
    """Peak-to-trough drawdown (≤ 0) over an equity curve of ``{equity: float}``."""
    peak = 1.0
    max_dd = 0.0
    for point in equity_curve:
        eq = float(point.get("equity") or 0.0)
        if eq <= 0:
            continue
        if eq > peak:
            peak = eq
        if peak:
            max_dd = min(max_dd, (eq / peak) - 1.0)
    return max_dd


def approx_turnover_from_curve(equity_curve: Sequence[Mapping[str, Any]]) -> float:
    """Approx turnover: mean absolute day-to-day change in ``n_picks``.

    Thin proxy only — does not track symbol identity or share weights.
    """
    if len(equity_curve) < 2:
        return 0.0
    total = 0.0
    steps = 0
    prev = int(equity_curve[0].get("n_picks") or 0)
    for point in equity_curve[1:]:
        cur = int(point.get("n_picks") or 0)
        total += abs(cur - prev)
        steps += 1
        prev = cur
    return total / steps if steps else 0.0


def portfolio_metrics(
    equity_curve: Sequence[Mapping[str, Any]] | None = None,
    trades: Sequence[Mapping[str, Any]] | None = None,
    *,
    final_equity: float | None = None,
) -> dict[str, Any]:
    """Compute thin portfolio-level metrics from a PIT result slice.

    Accepts equity curve and/or trades shaped like ``run_pit_long_only`` output.
    """
    curve = list(equity_curve or [])
    trade_rows = list(trades or [])
    fe = final_equity
    if fe is None:
        fe = float(curve[-1]["equity"]) if curve else 1.0
    return {
        "max_drawdown": max_drawdown_from_curve(curve),
        "turnover": approx_turnover_from_curve(curve),
        "n_trades": len(trade_rows),
        "final_equity": float(fe),
        "equal_weight_note": (
            "Day returns average equal-weight across same-day picks "
            "(run_pit_long_only); turnover approx from |Δ n_picks| — not a "
            "full portfolio accounting engine."
        ),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
    }


def run_portfolio_pit(panel: pd.DataFrame, **kwargs: Any) -> dict[str, Any]:
    """Wrap ``run_pit_long_only`` and attach ``portfolio_metrics``."""
    result = run_pit_long_only(panel, **kwargs)
    metrics = portfolio_metrics(
        result.get("equity_curve") or [],
        result.get("trades") or [],
        final_equity=result.get("final_equity"),
    )
    return {
        **result,
        "metrics": metrics,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
    }
