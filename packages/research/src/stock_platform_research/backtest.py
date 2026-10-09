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
- an explicit cost model (``portfolio.CostModel``, milestone ``B3``) aligned with
  ``a-stock-engine/local_backtest.py``: commission 万0.854 on both sides, stamp
  duty 万5 **sell-only**, ETF exempt, plus a configurable per-side **slippage**
  applied to fill prices only (default ``0`` = zero-friction B1/B2 baseline)
- a real equity curve plus portfolio metrics (CAGR / max drawdown / Sharpe /
  Sortino / Calmar / turnover / win-rate), including a per-asset-class
  ``by_asset`` breakdown for mixed stock / ETF books (milestone ``B4``)
- a selectable ``universe`` (``stock`` / ``etf`` / ``all``) so the book can be
  stocks-only (baseline), ETFs-only, or a mixed pool; classification and the ETF
  stamp exemption share one definition (:func:`portfolio.asset_class`)
- **every trading decision** delegates to :mod:`stock_platform_research.rules`
  (milestone ``B5``): the exit call (:func:`rules.evaluate_exit`), the peak
  advance and the price-limit checks are the *same* functions the online book
  review (:func:`position_review.review_positions`) calls — one definition, two
  call paths, no room for the two to drift

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
from typing import Any, Mapping, Sequence

import pandas as pd

from .gates import apply_entry_gates
from .lvrev import score_lvrev
from .portfolio import (  # noqa: F401 (re-export: B2 metrics + B3 cost model + B4 asset classes)
    DEFAULT_COMMISSION_RATE,
    DEFAULT_STAMP_SELL_RATE,
    CostModel,
    asset_class,
    compute_metrics,
    hhi,
    is_etf,
    is_fund,
    max_drawdown_from_curve,
    norm_code,
    trade_cost,
)
from .rules import (  # noqa: F401 (re-export: B5 trading-rule single definition)
    CooldownPolicy,
    DriftPolicy,
    ExitDecision,
    ExitPolicy,
    PositionState,
    advance_peak,
    evaluate_exit,
    is_limit_down,
    is_limit_up,
    limit_pct,
)

TRADING_DAYS_PER_YEAR = 252

# Valid ``universe`` selectors (B4). ``stock`` reproduces the B1/B2/B3 baseline.
UNIVERSES = ("stock", "etf", "all")

# ``B5``: ``PositionState`` (in ``rules``) is the shared position record; the old
# private name is kept as an alias so the rest of this module reads unchanged.
_Position = PositionState


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
    slippage_bps: float = 0.0,
    min_commission: float = 0.0,
    value_factor: bool = False,
    weights: Mapping[str, float] | None = None,
    universe: str = "stock",
    exclude_funds: bool | None = None,
    cooldown_days: int = 0,
    drift_band: float | None = None,
    regime: Mapping[str, bool] | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Run a long-only book over ``bars`` and return curve + trades + metrics.

    ``universe`` (``B4``) selects the tradable set: ``"stock"`` drops all
    ``1xxxxx`` / ``5xxxxx`` funds (the engine-aligned B1/B2/B3 baseline default),
    ``"etf"`` keeps only on-exchange funds in the ETF prefix table, ``"all"`` is a
    mixed stock + ETF book. ETF sells are stamp-exempt through :class:`CostModel`.
    The legacy ``exclude_funds`` flag still works: when passed it overrides
    ``universe`` (``True`` → ``"stock"``, ``False`` → ``"all"``).

    ``regime`` optionally maps ``YYYY-MM-DD`` → tradable flag (caller-supplied
    L0 gate); when a day maps to ``False`` no new positions are opened.

    Costs come from a single :class:`~stock_platform_research.portfolio.CostModel`
    built from ``commission_rate`` / ``stamp_sell_rate`` / ``slippage_bps`` /
    ``min_commission``. Slippage moves the **fill price** only — every signal and
    every stop / target / trailing trigger still reads the reference close — so
    the defaults (0 slippage, no floor) reproduce the B1 / B2 baseline exactly.

    ``B5``: **every** trading decision here is delegated to
    :mod:`stock_platform_research.rules` — the exit call is
    :func:`rules.evaluate_exit`, the peak is advanced by :func:`rules.advance_peak`
    and the price-limit checks are :func:`rules.is_limit_up` /
    :func:`rules.is_limit_down` — the *same* functions
    :func:`position_review.review_positions` calls on the online path. The new
    ``B5`` knobs default to *off*: ``cooldown_days = 0`` (no 冷静期) and
    ``drift_band = None`` (no 持仓偏差 rule), so the default run stays
    bit-for-bit the ``B1``–``B4`` baseline.
    """
    if exclude_funds is not None:
        universe = "stock" if exclude_funds else "all"
    universe = str(universe).strip().lower()
    if universe not in UNIVERSES:
        raise ValueError(f"universe must be one of {UNIVERSES}, got {universe!r}")

    # B5: one policy object, one evaluation call — shared with the online path.
    exit_policy = ExitPolicy(
        stop_loss=stop_loss,
        take_profit=take_profit,
        target_base=target_base,
        trail_stop_pct=trail_stop_pct,
        trail_min_peak_ret=trail_min_peak_ret,
        min_hold=min_hold,
        max_hold_days=max_hold_days,
    )
    cooldown_policy = CooldownPolicy(cooldown_days=int(cooldown_days))
    drift_policy = DriftPolicy(band=drift_band)

    cost_model = CostModel(
        commission_rate=commission_rate,
        stamp_sell_rate=stamp_sell_rate,
        slippage_bps=slippage_bps,
        min_commission=min_commission,
    )
    feats = compute_features(bars)
    if universe == "stock":
        feats = feats[~feats["code"].map(is_fund)]
    elif universe == "etf":
        feats = feats[feats["code"].map(is_etf)]
    if start is not None:
        feats = feats[feats["trade_date"] >= pd.Timestamp(start)]
    if end is not None:
        feats = feats[feats["trade_date"] <= pd.Timestamp(end)]
    if feats.empty:
        return _empty_result(initial_capital, "no bars in range")

    cash = float(initial_capital)
    positions: dict[str, _Position] = {}
    last_exit_idx: dict[str, int] = {}  # B5 冷静期 bookkeeping (no-op at default)
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
            if is_limit_down(code, pct_by_code.get(code)):
                continue
            # B5: peak advance + the exit decision itself come from the shared
            # rules layer — the online review calls the very same functions.
            pos.peak = advance_peak(pos.peak, px)
            held = di - pos.entry_idx

            row_ma20 = frame.loc[frame["code"] == code, "ma20"]
            row_ma60 = frame.loc[frame["code"] == code, "ma60"]
            ma20 = float(row_ma20.iloc[0]) if len(row_ma20) else None
            ma60 = float(row_ma60.iloc[0]) if len(row_ma60) else None

            decision = evaluate_exit(
                px=px,
                entry_price=pos.entry_price,
                target=pos.target,
                peak=pos.peak,
                held_days=held,
                ma20=ma20,
                ma60=ma60,
                policy=exit_policy,
            )

            if decision is not None:
                reason = decision.reason
                # Fill at the slipped price; both legs price through the shared
                # CostModel so the basis is symmetric with the buy side.
                sell_fill = cost_model.fill_price(px, is_buy=False)
                gross_fill = pos.shares * sell_fill
                proceeds = gross_fill - cost_model.costs(gross_fill, code, is_buy=False)
                entry_notional = pos.shares * pos.entry_price
                cost_basis = entry_notional + cost_model.costs(
                    entry_notional, code, is_buy=True
                )
                cash += proceeds
                trades.append(
                    {
                        "code": code,
                        "asset_class": asset_class(code),
                        "entry_idx": pos.entry_idx,
                        "exit_idx": di,
                        "held_days": held,
                        "entry_price": pos.entry_price,
                        "exit_price": sell_fill,
                        "entry_value": round(entry_notional, 2),
                        "exit_value": round(gross_fill, 2),
                        "gross_ret": round((sell_fill / pos.entry_price - 1.0) * 100.0, 4),
                        "net_ret": round((proceeds / cost_basis - 1.0) * 100.0, 4)
                        if cost_basis
                        else 0.0,
                        "reason": reason,
                        "exit_date": day_str,
                    }
                )
                last_exit_idx[code] = di
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
            px = float(row["close"])  # reference close — signal / limit checks only
            if px <= 0 or pd.isna(px):
                continue
            # limit-up: cannot fill a buy at the sealed price (shared rule)
            if is_limit_up(code, row.get("pct_chg")):
                continue
            # B5 冷静期: skip a code still inside its post-exit cooldown window
            # (no-op at the default ``cooldown_days = 0``).
            if cooldown_policy.blocks(last_exit_idx=last_exit_idx.get(code), current_idx=di):
                continue
            fill = cost_model.fill_price(px, is_buy=True)
            budget = min(cash, slot_value)
            shares = math.floor(budget / fill / lot_size) * lot_size
            if shares <= 0:
                continue
            gross = shares * fill
            cost = gross + cost_model.costs(gross, code, is_buy=True)
            if cost > cash:
                continue
            cash -= cost
            positions[code] = _Position(
                code=code,
                entry_price=fill,
                shares=float(shares),
                entry_idx=di,
                target=exit_policy.target_price(fill),
                peak=fill,
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
            "slippage_bps": slippage_bps,
            "min_commission": min_commission,
            "value_factor": value_factor,
            "universe": universe,
            # B5: policy echo so an online review can be proven to run the same
            # parameters the backtest did (asserted in tests/test_rules.py).
            "cooldown_days": cooldown_policy.cooldown_days,
            "drift_band": drift_policy.band,
            "exit_policy": {
                "stop_loss": exit_policy.stop_loss,
                "take_profit": exit_policy.take_profit,
                "target_base": exit_policy.target_base,
                "trail_stop_pct": exit_policy.trail_stop_pct,
                "trail_min_peak_ret": exit_policy.trail_min_peak_ret,
                "min_hold": exit_policy.min_hold,
                "max_hold_days": exit_policy.max_hold_days,
                "trail_min_held": exit_policy.trail_min_held,
            },
        },
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "disclaimer": "Research only; not investment advice.",
    }


# ``compute_metrics`` now lives in ``portfolio.py`` — the single source of truth
# for metric conventions (milestone B2) — and is re-exported at the top of this
# module so existing ``from .backtest import compute_metrics`` callers keep working.
