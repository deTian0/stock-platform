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

``X4`` (picks ↔ backtest parity)
--------------------------------
The daily loop itself no longer lives here. It is the **single definition**
:func:`book_replay.replay_book`, and this module is now a thin wrapper that only
supplies the *screener* entry provider
(:func:`book_replay.screener_entry_provider`). The logged-picks path
(:func:`picks_backtest.run_picks_backtest`) calls the **very same** loop with a
different provider, so a recommendation and a backtest position are judged by one
engine. ``tests/test_book_replay.py`` pins the pre-``X4`` numbers bit for bit.

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

from typing import Any, Mapping, Sequence

import pandas as pd

from .book_replay import (  # noqa: F401 (re-export: X4 shared replay loop)
    EntryCandidate,
    EntryContext,
    EntryProvider,
    ReplayParams,
    empty_result,
    replay_book,
    screener_entry_provider,
)
from .gates import apply_entry_gates  # noqa: F401 (screener policy, re-exported)
from .lvrev import score_lvrev  # noqa: F401 (screener policy, re-exported)
from .neutralization import attach_industry  # S4: industry join single point
from .portfolio import (  # noqa: F401 (re-export: B2 metrics + B3 cost model + B4 asset classes)
    DEFAULT_COMMISSION_RATE,
    DEFAULT_STAMP_SELL_RATE,
    CostModel,
    asset_class,
    compute_metrics,
    drawdown_series,
    hhi,
    is_etf,
    is_fund,
    max_drawdown_from_curve,
    norm_code,
    trade_cost,
)
from .pct_scale import normalize_pct_chg
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

# ``X4``: the pre-refactor private empty-result helper is now the shared one.
_empty_result = empty_result


def compute_features(
    bars: pd.DataFrame,
    *,
    pct_scale: str = "auto",
    keep_extra: Sequence[str] = (),
) -> pd.DataFrame:
    """Per-code rolling features. Uses only bars up to each date (PIT-safe).

    Adds ``trade_date`` / ``ret1`` / ``vol20`` / ``rev_chg`` / ``ma20`` / ``ma60``.
    ``keep_extra`` optionally carries additional raw columns (e.g. ``vol`` /
    ``amount`` for the ``S2`` factor library) through the adjustment step.
    Rolling windows require a full history (``min_periods`` == window), so the
    first N bars per code produce NaN and are naturally gated out.

    ``pct_scale`` governs the mixed-scale ``pct_chg`` column — see
    :func:`pct_scale.detect_pct_scale`. ``"auto"`` (default) fits the scale
    against the ``close`` series and rewrites ``pct_chg`` into **percent points**,
    the contract scale for :func:`rules.is_limit_up` / :func:`rules.is_limit_down`.
    ``"verbatim"`` is the legacy behaviour, kept only for A/B comparison.
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
    # ``pct_chg`` ships on a *mixed* scale. Under ``pct_scale="auto"`` the per-code
    # scale is fitted against the ``close`` series (``pct_scale.normalize_pct_chg``)
    # and the column is rewritten into **percent points** — the very scale
    # ``rules.is_limit_up`` / ``is_limit_down`` compare against, so those checks
    # finally see values they can act on. ``"verbatim"`` keeps the legacy
    # whole-table median heuristic and leaves the column untouched.
    df["raw_close"] = df["close"].astype(float)
    if "pct_chg" in df.columns and df["pct_chg"].notna().any():
        if pct_scale == "verbatim":
            pct = df["pct_chg"].astype(float)
            med = float(pct.abs().median())
            frac = (pct / 100.0 if med > 0.5 else pct).fillna(0.0).clip(-0.6, 0.6)
        else:
            points, _ = normalize_pct_chg(df)
            df["pct_chg"] = points
            frac = (points / 100.0).fillna(0.0).clip(-0.6, 0.6)
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
    # ``keep_extra`` opts a caller into carrying raw columns through the
    # adjustment step (e.g. the S2 factor library needs ``vol`` / ``amount``);
    # default ``()`` keeps the legacy column set byte-identical.
    keep = [
        "code", "trade_date", "close", "pct_chg",
        "ret1", "vol20", "rev_chg", "ma20", "ma60",
        *keep_extra,
    ]
    out = df[[c for c in keep if c in df.columns]].copy()
    for col in ("close", "pct_chg", "ret1", "vol20", "rev_chg", "ma20", "ma60", *keep_extra):
        if col in out.columns and pd.api.types.is_numeric_dtype(out[col]):
            out[col] = out[col].astype("float32")
    return out


def prepare_book_frame(
    bars: pd.DataFrame,
    *,
    universe: str = "stock",
    exclude_funds: bool | None = None,
    start: str | None = None,
    end: str | None = None,
    pct_scale: str = "auto",
    industry_map: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """The shared ``bars`` → tradable feature frame step (``X4``).

    Applies, in order: ``compute_features`` → the ``universe`` filter → the
    ``start`` / ``end`` window slice. Both the screener backtest and the
    logged-picks replay call this, so the two paths cannot disagree about which
    rows are tradable.
    """
    if exclude_funds is not None:
        universe = "stock" if exclude_funds else "all"
    universe = str(universe).strip().lower()
    if universe not in UNIVERSES:
        raise ValueError(f"universe must be one of {UNIVERSES}, got {universe!r}")

    feats = compute_features(bars, pct_scale=pct_scale)
    if universe == "stock":
        feats = feats[~feats["code"].map(is_fund)]
    elif universe == "etf":
        feats = feats[feats["code"].map(is_etf)]
    if start is not None:
        feats = feats[feats["trade_date"] >= pd.Timestamp(start)]
    if end is not None:
        feats = feats[feats["trade_date"] <= pd.Timestamp(end)]
    if industry_map is not None:
        # S4: optional industry label column (code → industry), read-only source.
        feats = attach_industry(feats, industry_map)
    return feats


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
    pct_scale: str = "auto",
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

    ``X4``: the loop itself is :func:`book_replay.replay_book` — the *same*
    function the logged-picks replay (:func:`picks_backtest.run_picks_backtest`)
    runs. This wrapper contributes only the screener entry provider, so the two
    paths share one engine and cannot drift.

    ``pct_scale`` (default ``"auto"``) forwards to :func:`compute_features` and
    repairs the mixed-scale ``pct_chg`` dump, so the price-limit checks receive
    percent points rather than whatever the loader left in the column. This
    **does** move the baseline — sealed limits now actually defer / skip trades —
    which is the point; ``"verbatim"`` reproduces the pre-fix numbers for A/B.
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

    feats = prepare_book_frame(
        bars,
        universe=universe,
        start=start,
        end=end,
        pct_scale=pct_scale,
    )
    if feats.empty:
        return empty_result(initial_capital, "no bars in range")

    loop = replay_book(
        feats,
        entry_provider=screener_entry_provider(
            reversal_q=reversal_q,
            min_pick_score=min_pick_score,
            value_factor=value_factor,
            weights=weights,
        ),
        params=ReplayParams(
            initial_capital=initial_capital,
            max_positions=max_positions,
            max_picks_per_day=max_picks_per_day,
            lot_size=lot_size,
            exit_policy=exit_policy,
            cooldown_policy=cooldown_policy,
            cost_model=cost_model,
            regime=regime,
        ),
    )

    return {
        "ok": True,
        "equity_curve": loop["equity_curve"],
        "trades": loop["trades"],
        "open_positions": loop.get("open_positions") or [],
        "n_days": loop["n_days"],
        "final_equity": loop["final_equity"],
        "initial_capital": loop["initial_capital"],
        "metrics": compute_metrics(
            loop["equity_curve"], loop["trades"], initial_capital=initial_capital
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
            # B6.1: the scale in force for ``pct_chg`` — echo it so an A/B run is
            # self-describing (``"verbatim"`` == the pre-fix baseline).
            "pct_scale": pct_scale,
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
