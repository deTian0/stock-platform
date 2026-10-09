"""Portfolio-level long-only backtest over engine daily bars (B1 backtest baseline).

Why this module exists
----------------------
``pit.run_pit_long_only`` is a *daily full-rotation* sketch: every session it
re-picks top-N and equal-weights a **1-day** hold. That answers "is the signal
rank informative" but cannot answer "what does a realistic book look like" —
it has no holding period, no cost model and no position state.

This module adds the missing layer on top of the **same** kernels
(``lvrev.score_lvrev`` + ``gates.apply_entry_gates``):

- explicit positions with entry price / shares / running peak
- MIN_HOLD holding period, hard stop-loss, target take-profit, trailing stop,
  max-hold safety valve
- max concurrent positions + equal-weight sizing + 100-share lot rounding
- an explicit cost model aligned with ``a-stock-engine/local_backtest.py``:
  commission 万0.854 on both sides, stamp duty 万5 **sell-only**, ETF exempt
- a real equity curve plus portfolio metrics (CAGR / max drawdown / Sharpe /
  Sortino / Calmar / turnover / win-rate)

Data source is injected as a plain ``bars`` DataFrame (``code`` / ``date`` /
``close``, optional ``pct_chg``). This module never opens SQLite and never
imports providers — the caller owns read-only ``market.db`` access.

Known deltas vs. the engine (call out, never hide)
--------------------------------------------------
- ``market.db.daily_price`` stores **close only** (no open/high/low), so fills
  are modelled at the same-session close, exactly like the engine
  (``get_price_on_date``). No T+1 open fill.
- ``close`` in the dump is **unadjusted**; ``compute_features`` rebuilds a
  dividend-adjusted series from ``pct_chg`` (mixed fraction / percent scale,
  auto-detected) so splits do not masquerade as losses.
- The engine's L0 bear gate (index MA200 + valuation percentile) needs an index
  series this module does not receive; ``bear_gate`` is therefore opt-in and
  driven by a caller-supplied ``regime`` mapping.
- ST blacklisting needs the ``fundamentals.name`` column; not available here.

SIMULATE only. ``liveTradingEnabled=False``. Not investment advice.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import pandas as pd

from .gates import apply_entry_gates
from .lvrev import score_lvrev
from .portfolio import compute_metrics, hhi, max_drawdown_from_curve  # noqa: F401 (re-export)

# --- cost model: aligned with a-stock-engine/local_backtest.py (v4.31) ---
DEFAULT_COMMISSION_RATE = 0.0000854  # 万0.854, 免5 (both sides)
DEFAULT_STAMP_SELL_RATE = 0.0005  # 万5 stamp duty, sell side only
TRADING_DAYS_PER_YEAR = 252

# Prefixes treated as ETF / on-exchange fund (stamp-duty exempt).
_ETF_PREFIXES = (
    "15", "51", "56", "58", "510", "511", "512", "513", "515", "516", "517",
    "518", "519", "520", "560", "561", "562", "563", "564", "565", "566",
    "567", "568", "588", "501", "502", "505", "506", "507", "508",
)


def norm_code(raw: Any) -> str:
    """``'000001.SZ'`` / ``'000001'`` → ``'000001'`` (6 digits)."""
    return str(raw).replace(".", "")[:6]


def is_fund(code: Any) -> bool:
    """``1xxxxx`` / ``5xxxxx`` prefixes = on-exchange fund / ETF / bond."""
    return norm_code(code).startswith(("1", "5"))


def is_etf(code: Any) -> bool:
    """ETF / on-exchange fund → stamp-duty exempt (mirrors engine ``_is_etf``)."""
    return norm_code(code).startswith(_ETF_PREFIXES)


def limit_pct(code: Any, *, is_st: bool = False) -> float:
    """Daily price limit: ST ±5% / STAR+ChiNext (30/68) ±20% / main board ±10%."""
    c = norm_code(code)
    if is_st:
        return 0.05
    return 0.20 if c.startswith(("30", "68")) else 0.10


def trade_cost(
    code: Any,
    *,
    is_buy: bool,
    commission_rate: float = DEFAULT_COMMISSION_RATE,
    stamp_sell_rate: float = DEFAULT_STAMP_SELL_RATE,
) -> float:
    """Round-trip-leg cost rate: commission both sides; stamp only on sell (stocks)."""
    if is_etf(code):
        return commission_rate
    return commission_rate if is_buy else commission_rate + stamp_sell_rate


def compute_features(bars: pd.DataFrame) -> pd.DataFrame:
    """Per-code rolling features. Uses only bars up to each date (PIT-safe).

    Adds ``trade_date`` / ``ret1`` / ``vol20`` / ``rev_chg`` / ``ma20`` / ``ma60``.
    Rolling windows require a full history (``min_periods`` == window), so the
    first N bars per code produce NaN and are naturally gated out.
    """
    need = {"code", "date", "close"}
    missing = need - set(bars.columns)
    if missing:
        raise ValueError(f"bars missing columns: {sorted(missing)}")

    df = bars.copy()
    df["trade_date"] = pd.to_datetime(df["date"]).dt.normalize()
    df = df.sort_values(["code", "trade_date"]).reset_index(drop=True)

    # The engine dump stores an *unadjusted* ``close`` next to a true daily
    # return in ``pct_chg``. Corporate actions (splits / dividends) therefore
    # appear as fake gaps in ``close`` (B1 repro: 600551.SH moves -32.6% while
    # ``pct_chg`` stays inside ±10%). Rebuild a dividend-adjusted price series
    # from ``pct_chg`` so both features and P&L are corporate-action clean.
    # ``pct_chg`` ships on a *mixed* scale (fractions for most rows, percent
    # points for some), so the scale is detected per load from median magnitude.
    df["raw_close"] = df["close"].astype(float)
    if "pct_chg" in df.columns and df["pct_chg"].notna().any():
        pct = df["pct_chg"].astype(float)
        med = float(pct.abs().median())
        frac = (pct / 100.0 if med > 0.5 else pct).fillna(0.0).clip(-0.6, 0.6)
        base = df.groupby("code", sort=False)["raw_close"].transform("first")
        df["close"] = base * (1.0 + frac).groupby(df["code"], sort=False).cumprod()

    df["ret1"] = df.groupby("code", sort=False)["close"].pct_change()
    df["vol20"] = (
        df.groupby("code", sort=False)["ret1"]
        .rolling(21, min_periods=21)
        .std()
        .reset_index(level=0, drop=True)
    )
    df["rev_chg"] = df.groupby("code", sort=False)["close"].pct_change(20)
    df["ma20"] = (
        df.groupby("code", sort=False)["close"]
        .rolling(20, min_periods=20)
        .mean()
        .reset_index(level=0, drop=True)
    )
    df["ma60"] = (
        df.groupby("code", sort=False)["close"]
        .rolling(60, min_periods=60)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Full-market runs hold ~8.8M rows; keep only what the loop needs and
    # downcast to shrink the peak footprint (float32 is ample for prices).
    keep = [
        "code", "trade_date", "close", "pct_chg",
        "ret1", "vol20", "rev_chg", "ma20", "ma60",
    ]
    out = df[[c for c in keep if c in df.columns]].copy()
    for col in ("close", "pct_chg", "ret1", "vol20", "rev_chg", "ma20", "ma60"):
        if col in out.columns:
            out[col] = out[col].astype("float32")
    return out


@dataclass
class _Position:
    code: str
    entry_price: float
    shares: float
    entry_idx: int
    target: float
    peak: float


def _empty_result(initial_capital: float, reason: str) -> dict[str, Any]:
    return {
        "ok": False,
        "reason": reason,
        "equity_curve": [],
        "trades": [],
        "metrics": compute_metrics([], [], initial_capital=initial_capital),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "disclaimer": "Research only; not investment advice.",
    }


def run_portfolio_backtest(
    bars: pd.DataFrame,
    *,
    initial_capital: float = 50000.0,
    max_picks_per_day: int = 8,
    max_positions: int = 15,
    min_hold: int = 45,
    max_hold_days: int = 60,
    stop_loss: float = 8.0,
    target_base: float = 5.0,
    take_profit: float = 0.0,
    trail_stop_pct: float = 6.0,
    trail_min_peak_ret: float = 2.0,
    reversal_q: float = 0.30,
    min_pick_score: float = 0.80,
    lot_size: int = 100,
    commission_rate: float = DEFAULT_COMMISSION_RATE,
    stamp_sell_rate: float = DEFAULT_STAMP_SELL_RATE,
    value_factor: bool = False,
    weights: Mapping[str, float] | None = None,
    exclude_funds: bool = True,
    regime: Mapping[str, bool] | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Run a long-only book over ``bars`` and return curve + trades + metrics.

    ``regime`` optionally maps ``YYYY-MM-DD`` → tradable flag (caller-supplied
    L0 gate); when a day maps to ``False`` no new positions are opened.
    """
    feats = compute_features(bars)
    if exclude_funds:
        feats = feats[~feats["code"].map(is_fund)]
    if start is not None:
        feats = feats[feats["trade_date"] >= pd.Timestamp(start)]
    if end is not None:
        feats = feats[feats["trade_date"] <= pd.Timestamp(end)]
    if feats.empty:
        return _empty_result(initial_capital, "no bars in range")

    cash = float(initial_capital)
    positions: dict[str, _Position] = {}
    equity_curve: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []

    for di, (day, frame) in enumerate(feats.groupby("trade_date", sort=True)):
        day_str = day.date().isoformat()
        px_by_code = dict(zip(frame["code"], frame["close"]))

        # --- 1. position review at today's close ---
        to_close: list[str] = []
        pct_by_code = (
            dict(zip(frame["code"], frame["pct_chg"])) if "pct_chg" in frame.columns else {}
        )
        for code, pos in list(positions.items()):
            px = px_by_code.get(code)
            if px is None or pd.isna(px) or float(px) <= 0:
                continue  # suspended / no bar: hold, retry next session
            px = float(px)
            # limit-down: sell order sealed, cannot fill today -> roll to next session
            dpct = pct_by_code.get(code)
            if dpct is not None and not pd.isna(dpct) and float(dpct) <= -limit_pct(code) * 100.0 + 0.01:
                continue
            if px > pos.peak:
                pos.peak = px
            held = di - pos.entry_idx
            ret_pct = (px / pos.entry_price - 1.0) * 100.0
            peak_ret = (pos.peak / pos.entry_price - 1.0) * 100.0

            row_ma20 = frame.loc[frame["code"] == code, "ma20"]
            row_ma60 = frame.loc[frame["code"] == code, "ma60"]
            ma20 = float(row_ma20.iloc[0]) if len(row_ma20) else float("nan")
            ma60 = float(row_ma60.iloc[0]) if len(row_ma60) else float("nan")

            reason = None
            if ret_pct <= -stop_loss:
                reason = f"stop_loss({ret_pct:+.1f}%)"
            elif take_profit > 0 and ret_pct >= take_profit:
                reason = f"take_profit({ret_pct:+.1f}%)"
            elif held >= min_hold:
                if px >= pos.target:
                    reason = f"target({ret_pct:+.1f}%)"
                elif not pd.isna(ma20) and not pd.isna(ma60) and ma20 <= ma60:
                    reason = f"trend_break({ret_pct:+.1f}%)"
                elif (
                    held > 3
                    and peak_ret >= trail_min_peak_ret
                    and pos.peak > 0
                    and (pos.peak - px) / pos.peak >= trail_stop_pct / 100.0
                ):
                    reason = f"trail_stop({ret_pct:+.1f}%)"
                elif held >= max_hold_days:
                    reason = f"max_hold({held}d)"

            if reason:
                cr = trade_cost(
                    code,
                    is_buy=False,
                    commission_rate=commission_rate,
                    stamp_sell_rate=stamp_sell_rate,
                )
                proceeds = pos.shares * px * (1.0 - cr)
                cost_basis = pos.shares * pos.entry_price * (1.0 + commission_rate)
                cash += proceeds
                trades.append(
                    {
                        "code": code,
                        "entry_idx": pos.entry_idx,
                        "exit_idx": di,
                        "held_days": held,
                        "entry_price": pos.entry_price,
                        "exit_price": px,
                        "entry_value": round(pos.shares * pos.entry_price, 2),
                        "exit_value": round(pos.shares * px, 2),
                        "gross_ret": round(ret_pct, 4),
                        "net_ret": round((proceeds / cost_basis - 1.0) * 100.0, 4)
                        if cost_basis
                        else 0.0,
                        "reason": reason,
                        "exit_date": day_str,
                    }
                )
                to_close.append(code)
        for code in to_close:
            del positions[code]

        # --- 2. mark to market (+ same-day concentration scalars) ---
        total = cash
        holdings: list[float] = []
        for pos in positions.values():
            px = px_by_code.get(pos.code)
            mv = pos.shares * (float(px) if px and not pd.isna(px) else pos.entry_price)
            total += mv
            holdings.append(mv)
        held_value = sum(holdings)
        equity_curve.append(
            {
                "date": day_str,
                "equity": round(total, 2),
                "n_positions": len(positions),
                # B2: same-day concentration (HHI over holding market values,
                # cash excluded) + how much equity was actually deployed.
                "hhi": round(hhi(holdings), 6),
                "top_weight": round(max(holdings) / held_value, 6) if held_value > 0 else 0.0,
                "invested_ratio": round(held_value / total, 6) if total > 0 else 0.0,
            }
        )

        # --- 3. entries at today's close ---
        tradable = True if regime is None else bool(regime.get(day_str, True))
        if not tradable or len(positions) >= max_positions:
            continue

        scored = score_lvrev(frame, value_factor=value_factor, weights=weights)
        mask = apply_entry_gates(scored, reversal_q=reversal_q)
        elig = scored.loc[mask]
        elig = elig[elig["composite_score"] >= min_pick_score]
        if elig.empty:
            continue
        elig = elig[~elig["code"].isin(positions)]

        slot_value = total / max_positions
        for _, row in elig.head(max_picks_per_day).iterrows():
            if len(positions) >= max_positions:
                break
            code = row["code"]
            px = float(row["close"])
            if px <= 0 or pd.isna(px):
                continue
            # limit-up: cannot fill a buy at the sealed price
            upct = row.get("pct_chg")
            if upct is not None and not pd.isna(upct) and float(upct) >= limit_pct(code) * 100.0 - 0.01:
                continue
            budget = min(cash, slot_value)
            shares = math.floor(budget / px / lot_size) * lot_size
            if shares <= 0:
                continue
            cost = shares * px * (1.0 + commission_rate)
            if cost > cash:
                continue
            cash -= cost
            positions[code] = _Position(
                code=code,
                entry_price=px,
                shares=float(shares),
                entry_idx=di,
                target=px * (1.0 + target_base / 100.0),
                peak=px,
            )

    return {
        "ok": True,
        "equity_curve": equity_curve,
        "trades": trades,
        "n_days": len(equity_curve),
        "final_equity": equity_curve[-1]["equity"] if equity_curve else float(initial_capital),
        "initial_capital": initial_capital,
        "metrics": compute_metrics(
            equity_curve, trades, initial_capital=initial_capital
        ),
        "params": {
            "max_picks_per_day": max_picks_per_day,
            "max_positions": max_positions,
            "min_hold": min_hold,
            "max_hold_days": max_hold_days,
            "stop_loss": stop_loss,
            "target_base": target_base,
            "take_profit": take_profit,
            "trail_stop_pct": trail_stop_pct,
            "reversal_q": reversal_q,
            "min_pick_score": min_pick_score,
            "commission_rate": commission_rate,
            "stamp_sell_rate": stamp_sell_rate,
            "value_factor": value_factor,
        },
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "disclaimer": "Research only; not investment advice.",
    }


# ``compute_metrics`` now lives in ``portfolio.py`` — the single source of truth
# for metric conventions (milestone B2) — and is re-exported at the top of this
# module so existing ``from .backtest import compute_metrics`` callers keep working.
