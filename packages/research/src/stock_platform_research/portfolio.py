"""Portfolio metrics — the **single source of truth** for return / risk /
turnover conventions (ADR 0043, extended by milestone ``B2``).

Both the full portfolio engine (``backtest.run_portfolio_backtest``) and the
thin PIT wrapper (``portfolio_metrics`` / ``run_portfolio_pit``) report through
``compute_metrics`` defined *here*, so every metric has exactly one definition.
This is the groundwork for ``B5`` (backtest ↔ online rule unification): when a
number changes it changes in one place, and both call paths follow.

Conventions (frozen in ``docs/contracts/portfolio-metrics.md``)
---------------------------------------------------------------
- returns are **fractions** (``0.1024`` = +10.24%); ``max_drawdown`` is ``≤ 0``
- annualisation base is **252** trading days; risk-free rate is **0**
- Sharpe / Sortino are **annualised**; Sortino uses the downside deviation of
  negative daily returns (minimum acceptable return = 0)
- turnover is reported under **two** conventions: ``turnover_per_year``
  (trades per year, cheap proxy) and ``turnover_notional_per_year`` (traded
  notional ÷ mean equity ÷ year; ``None`` when trades carry no notional)
- concentration is the **Herfindahl-Hirschman index (HHI)** of same-day holding
  market values, normalised across holdings (cash excluded) and averaged over
  the curve; ``avg_invested_ratio`` says how much equity was actually held
- empty inputs never fabricate a metric: the block is all zeros / ``None`` with
  ``n_days = 0``
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from .pit import run_pit_long_only

TRADING_DAYS_PER_YEAR = 252


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

    Thin proxy for the PIT (daily full-rotation) curve only — it does not track
    symbol identity or share weights. The portfolio engine reports the real
    notional convention via ``compute_metrics``.
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


def hhi(weights: Iterable[float]) -> float:
    """Herfindahl-Hirschman index of a weight vector (share space, ``0–1``).

    Weights are normalised to sum to 1 first, so the index is scale-free and
    accepts raw market values. ``1 / n`` = fully diversified across ``n`` equal
    names; ``1.0`` = a single holding. Returns ``0.0`` for empty / non-positive
    input (no holdings ⇒ no concentration to speak of).
    """
    vals = [float(w) for w in weights if w is not None and float(w) > 0.0]
    total = sum(vals)
    if total <= 0.0:
        return 0.0
    return sum((v / total) ** 2 for v in vals)


def _curve_mean(curve: Sequence[Mapping[str, Any]], key: str) -> float | None:
    """Mean of ``key`` across curve points that actually carry it (else None)."""
    vals = [float(p[key]) for p in curve if p.get(key) is not None]
    return sum(vals) / len(vals) if vals else None


def _empty_metrics(initial_capital: float) -> dict[str, Any]:
    """Fail-closed all-zero block (no metric is faked) for empty input."""
    return {
        "n_days": 0,
        "total_return": 0.0,
        "cagr": 0.0,
        "max_drawdown": 0.0,
        "sharpe": 0.0,
        "sortino": 0.0,
        "calmar": 0.0,
        "n_trades": 0,
        "win_rate": 0.0,
        "avg_hold_days": 0.0,
        "turnover_per_year": 0.0,
        "turnover_notional_per_year": None,
        "avg_hhi": None,
        "avg_top_weight": None,
        "avg_invested_ratio": None,
        "avg_positions": None,
        "max_positions": 0,
        "final_equity": float(initial_capital),
    }


def compute_metrics(
    equity_curve: Sequence[Mapping[str, Any]],
    trades: Sequence[Mapping[str, Any]],
    *,
    initial_capital: float = 50000.0,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> dict[str, Any]:
    """Portfolio metrics from an equity curve + trade log.

    ``total_return`` / ``cagr`` are fractions; ``max_drawdown`` is ≤ 0 fraction.
    Sharpe / Sortino are annualised (rf = 0). Concentration metrics (``avg_hhi``
    / ``avg_top_weight`` / ``avg_invested_ratio`` / ``avg_positions``) are
    ``None`` when the curve does not carry the per-day fields, and
    ``turnover_notional_per_year`` is ``None`` when trades carry no notional —
    never fabricated. Empty input ⇒ all zeros with ``n_days = 0``.
    """
    curve = list(equity_curve or [])
    trade_rows = list(trades or [])
    equities = [float(p.get("equity") or 0.0) for p in curve]
    n_days = len(equities)
    if n_days == 0 or initial_capital <= 0:
        return _empty_metrics(initial_capital)

    final = equities[-1]
    total_return = final / initial_capital - 1.0
    years = n_days / float(periods_per_year)
    cagr = (final / initial_capital) ** (1.0 / years) - 1.0 if years > 0 and final > 0 else -1.0

    rets = [equities[i] / equities[i - 1] - 1.0 for i in range(1, n_days) if equities[i - 1] > 0]
    mean_r = sum(rets) / len(rets) if rets else 0.0
    var = sum((r - mean_r) ** 2 for r in rets) / len(rets) if rets else 0.0
    sd = math.sqrt(var)
    sharpe = (mean_r / sd) * math.sqrt(periods_per_year) if sd > 0 else 0.0

    downside = [r for r in rets if r < 0]
    dvar = sum(r * r for r in downside) / len(downside) if downside else 0.0
    dsd = math.sqrt(dvar)
    sortino = (mean_r / dsd) * math.sqrt(periods_per_year) if dsd > 0 else 0.0

    mdd = max_drawdown_from_curve(curve)
    calmar = cagr / abs(mdd) if mdd < 0 else 0.0

    n_trades = len(trade_rows)
    wins = sum(1 for t in trade_rows if float(t.get("net_ret") or 0.0) > 0)
    win_rate = wins / n_trades if n_trades else 0.0
    avg_hold = (
        sum(float(t.get("held_days") or 0.0) for t in trade_rows) / n_trades
        if n_trades
        else 0.0
    )
    turnover_per_year = n_trades / years if years > 0 else 0.0

    # --- B2 additions: notional turnover + concentration -------------------
    notionals = [
        float(t["entry_value"]) + float(t["exit_value"])
        for t in trade_rows
        if t.get("entry_value") is not None and t.get("exit_value") is not None
    ]
    mean_equity = sum(equities) / n_days
    turnover_notional_per_year: float | None = None
    if notionals and mean_equity > 0 and years > 0:
        turnover_notional_per_year = (sum(notionals) / mean_equity) / years

    avg_hhi = _curve_mean(curve, "hhi")
    avg_top_weight = _curve_mean(curve, "top_weight")
    avg_invested_ratio = _curve_mean(curve, "invested_ratio")
    avg_positions = _curve_mean(curve, "n_positions")
    max_positions = max((int(p.get("n_positions") or 0) for p in curve), default=0)

    return {
        "n_days": n_days,
        "total_return": round(total_return, 6),
        "cagr": round(cagr, 6),
        "max_drawdown": round(mdd, 6),
        "sharpe": round(sharpe, 4),
        "sortino": round(sortino, 4),
        "calmar": round(calmar, 4),
        "n_trades": n_trades,
        "win_rate": round(win_rate, 4),
        "avg_hold_days": round(avg_hold, 2),
        "turnover_per_year": round(turnover_per_year, 1),
        "turnover_notional_per_year": (
            round(turnover_notional_per_year, 2)
            if turnover_notional_per_year is not None
            else None
        ),
        "avg_hhi": round(avg_hhi, 6) if avg_hhi is not None else None,
        "avg_top_weight": round(avg_top_weight, 6) if avg_top_weight is not None else None,
        "avg_invested_ratio": (
            round(avg_invested_ratio, 6) if avg_invested_ratio is not None else None
        ),
        "avg_positions": round(avg_positions, 4) if avg_positions is not None else None,
        "max_positions": max_positions,
        "final_equity": round(final, 2),
    }


def portfolio_metrics(
    equity_curve: Sequence[Mapping[str, Any]] | None = None,
    trades: Sequence[Mapping[str, Any]] | None = None,
    *,
    final_equity: float | None = None,
) -> dict[str, Any]:
    """Thin PIT metrics (ADR 0043) — kept for the daily full-rotation curve.

    Reports the core thin proxy (drawdown / turnover / trade count) alongside the
    standard contract block from :func:`compute_metrics`, so downstream readers
    see consistent keys whether they look at the PIT wrapper or the engine.
    """
    curve = list(equity_curve or [])
    trade_rows = list(trades or [])
    fe = final_equity
    if fe is None:
        fe = float(curve[-1]["equity"]) if curve else 1.0
    # ``run_pit_long_only`` starts from an equity of exactly 1.0, so the PIT
    # curve's initial capital is 1.0 (not its final value).
    core = compute_metrics(curve, trade_rows, initial_capital=1.0)
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
        "cagr": core["cagr"],
        "sharpe": core["sharpe"],
        "sortino": core["sortino"],
        "calmar": core["calmar"],
        "n_days": core["n_days"],
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
