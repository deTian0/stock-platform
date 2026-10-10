"""Shared long-only book replay — the **single definition** of the trading loop (``X4``).

Why this module exists
----------------------
Until ``X4`` the portfolio engine lived entirely inside
:func:`backtest.run_portfolio_backtest`: the daily review → mark-to-market →
entry loop, the slot sizing and the trade bookkeeping were reachable **only** by
first running the ``lvrev`` screener inline. The roadmap's ``X4`` goal — *「每日
picks 自动进回测对照；推荐绩效与回测口径同源」* — therefore could not be honoured
without a **second copy** of that loop for the logged picks, which is exactly the
duplicate-implementation risk the ``C`` domain warns about.

This module is the **single definition** of the loop. Two call paths consume it:

* **screener** → :func:`backtest.run_portfolio_backtest` (the ``lvrev`` TopN picker)
* **picks**    → :func:`picks_backtest.run_picks_backtest` (a logged pick ledger)

Only the **entry provider** differs. Everything else — the exit decision
(:func:`rules.evaluate_exit`), the peak advance (:func:`rules.advance_peak`), the
price-limit seals (:func:`rules.is_limit_up` / :func:`rules.is_limit_down`), the
cost model (:class:`portfolio.CostModel`), the slot sizing and the metric
conventions (:func:`portfolio.compute_metrics`) — is literally the same code, so a
recommendation can no longer be judged by a different yardstick than a backtest
position.

The extraction is provably a **pure refactor**: ``tests/test_book_replay.py``
pins the pre-``X4`` baseline bit for bit across eight scenarios (a digest captured
from the pre-refactor engine).

Data in, numbers out — no I/O, no DB, no import of ``providers``. The caller owns
the read-only ``market.db`` access and hands in an already-built feature frame.
SIMULATE only. ``liveTradingEnabled=False``. Not investment advice.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from .portfolio import CostModel, asset_class, compute_metrics, hhi
from .rules import (
    CooldownPolicy,
    ExitPolicy,
    PositionState,
    advance_peak,
    evaluate_exit,
    is_limit_down,
    is_limit_up,
)

# A candidate row the loop may open: ``code`` + reference ``close`` (+ ``pct_chg``).
EntryCandidate = Mapping[str, Any]


@dataclass(frozen=True)
class ReplayParams:
    """Every knob of the shared loop. Defaults reproduce the ``B1``–``B5`` baseline."""

    initial_capital: float = 50000.0
    max_positions: int = 15
    max_picks_per_day: int = 8
    lot_size: int = 100
    exit_policy: ExitPolicy = field(default_factory=ExitPolicy)
    cooldown_policy: CooldownPolicy = field(default_factory=CooldownPolicy)
    cost_model: CostModel = field(default_factory=CostModel)
    regime: Mapping[str, bool] | None = None


@dataclass
class EntryContext:
    """Read-only view the entry provider sees on each session.

    The provider returns the day's **candidate** rows (ordered, highest intent
    first). The loop then applies the held-code filter, the ``max_picks_per_day``
    head, the limit-up seal, the cooldown gate and the lot rounding — so an entry
    provider can never bypass a shared rule.
    """

    day_index: int
    day: str
    frame: pd.DataFrame
    positions: Mapping[str, PositionState]
    cash: float
    equity: float
    last_exit_idx: Mapping[str, int]
    params: ReplayParams


EntryProvider = Callable[[EntryContext], Sequence[EntryCandidate]]


def empty_result(initial_capital: float, reason: str) -> dict[str, Any]:
    """Fail-closed all-zero result — no metric is fabricated for empty input."""
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


def replay_book(
    feats: pd.DataFrame,
    *,
    entry_provider: EntryProvider,
    params: ReplayParams | None = None,
) -> dict[str, Any]:
    """Replay one long-only book over an already-built feature frame.

    ``feats`` must carry ``code`` / ``trade_date`` / ``close`` (+ ``pct_chg`` /
    ``ma20`` / ``ma60``); it is expected to be the output of
    :func:`backtest.compute_features`, already filtered to the tradable universe
    and window and sorted by ``trade_date``.

    Per session, in this order:

    1. **review** every open position at the reference close — the exit call is
       :func:`rules.evaluate_exit` (shared with the online book review). A
       limit-down seal defers the sell to the next session.
    2. **mark to market** and append the equity point (plus the same-day
       concentration scalars ``hhi`` / ``top_weight`` / ``invested_ratio``).
    3. **entries** from ``entry_provider`` — subject to the ``regime`` gate,
       ``max_positions``, the held-code filter, ``max_picks_per_day``, the
       limit-up seal, the cooldown gate, equal-weight slot sizing and 100-share
       lot rounding.

    Returns ``equity_curve`` / ``trades`` / ``open_positions`` / ``n_days`` /
    ``final_equity`` / ``initial_capital`` / ``cash``; the wrappers attach
    ``metrics`` / ``params`` / the environment block so both call paths report the
    same shape. ``open_positions`` lists what was still held when the window ended
    (those never appear in ``trades``, so a caller replaying the schedule needs them).
    """
    p = params or ReplayParams()

    if feats.empty:
        # Neutral loop outputs only — the wrapper owns ``ok`` / ``reason`` /
        # ``metrics`` (an empty frame is a *wrapper-level* outcome: the universe
        # or window filter removed everything).
        return {
            "equity_curve": [],
            "trades": [],
            "open_positions": [],
            "n_days": 0,
            "final_equity": float(p.initial_capital),
            "initial_capital": p.initial_capital,
            "cash": float(p.initial_capital),
        }

    cash = float(p.initial_capital)
    positions: dict[str, PositionState] = {}
    last_exit_idx: dict[str, int] = {}
    equity_curve: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []

    cost_model = p.cost_model
    exit_policy = p.exit_policy
    cooldown_policy = p.cooldown_policy

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
        tradable = True if p.regime is None else bool(p.regime.get(day_str, True))
        if not tradable or len(positions) >= p.max_positions:
            continue

        candidates = entry_provider(
            EntryContext(
                day_index=di,
                day=day_str,
                frame=frame,
                positions=positions,
                cash=cash,
                equity=total,
                last_exit_idx=last_exit_idx,
                params=p,
            )
        )
        if not candidates:
            continue
        elig = [c for c in candidates if str(c.get("code")) not in positions]

        slot_value = total / p.max_positions
        for row in elig[: p.max_picks_per_day]:
            if len(positions) >= p.max_positions:
                break
            code = str(row.get("code"))
            px = float(row.get("close"))
            if px <= 0 or pd.isna(px):
                continue
            # limit-up: cannot fill a buy at the sealed price (shared rule)
            if is_limit_up(code, row.get("pct_chg")):
                continue
            # B5 冷静期: skip a code still inside its post-exit cooldown window
            # (no-op at the default ``cooldown_days = 0``).
            if cooldown_policy.blocks(
                last_exit_idx=last_exit_idx.get(code), current_idx=di
            ):
                continue
            fill = cost_model.fill_price(px, is_buy=True)
            budget = min(cash, slot_value)
            shares = math.floor(budget / fill / p.lot_size) * p.lot_size
            if shares <= 0:
                continue
            gross = shares * fill
            cost = gross + cost_model.costs(gross, code, is_buy=True)
            if cost > cash:
                continue
            cash -= cost
            positions[code] = PositionState(
                code=code,
                entry_price=fill,
                shares=float(shares),
                entry_idx=di,
                target=exit_policy.target_price(fill),
                peak=fill,
            )

    last_day_index = len(equity_curve) - 1
    # X4: positions still open when the window ends. They are **not** in ``trades``
    # (nothing was sold), so a caller replaying a schedule needs them to rebuild the
    # full entry set — and a book report wants to know what it is still holding.
    open_positions = [
        {
            "code": code,
            "entry_idx": pos.entry_idx,
            "entry_price": pos.entry_price,
            "shares": pos.shares,
            "target": pos.target,
            "peak": pos.peak,
            "held_days": max(0, last_day_index - pos.entry_idx),
        }
        for code, pos in positions.items()
    ]

    return {
        "equity_curve": equity_curve,
        "trades": trades,
        "open_positions": open_positions,
        "n_days": len(equity_curve),
        "final_equity": equity_curve[-1]["equity"] if equity_curve else float(p.initial_capital),
        "initial_capital": p.initial_capital,
        "cash": cash,
    }


def screener_entry_provider(
    *,
    reversal_q: float = 0.30,
    min_pick_score: float = 0.80,
    value_factor: bool = False,
    weights: Mapping[str, float] | None = None,
) -> EntryProvider:
    """The ``lvrev`` TopN entry provider — the pre-``X4`` in-loop picker, verbatim.

    Scoring (:func:`lvrev.score_lvrev`), gating
    (:func:`gates.apply_entry_gates`) and the score floor are screener *policy*,
    so they live with the screener; every *rule* they must respect stays in the
    shared loop.
    """
    from .gates import apply_entry_gates
    from .lvrev import score_lvrev

    def _provider(ctx: EntryContext) -> list[dict[str, Any]]:
        scored = score_lvrev(ctx.frame, value_factor=value_factor, weights=weights)
        mask = apply_entry_gates(scored, reversal_q=reversal_q)
        elig = scored.loc[mask]
        elig = elig[elig["composite_score"] >= min_pick_score]
        if elig.empty:
            return []
        return [
            {
                "code": str(row["code"]),
                "close": float(row["close"]),
                "pct_chg": row.get("pct_chg"),
            }
            for _, row in elig.iterrows()
        ]

    return _provider


__all__ = [
    "EntryCandidate",
    "EntryContext",
    "EntryProvider",
    "ReplayParams",
    "empty_result",
    "replay_book",
    "screener_entry_provider",
]
