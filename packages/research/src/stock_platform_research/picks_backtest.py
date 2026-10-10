"""Logged-picks ↔ backtest parity — the *picks* entry provider (``X4``).

Why this module exists
----------------------
``X2`` / ``X3`` already produce, archive and count the daily recommendation
boards. What was still missing was the ``X4`` half of the roadmap line: *「每日
picks 自动进回测对照；推荐绩效与回测口径同源」*.

The legacy recommendation yardstick (:func:`performance.performance_summary`,
``direction_accuracy``) is a **T+N fixed-hold, no-cost, unadjusted** mark. It is a
perfectly good hit-rate, but it answers a *different* question from the portfolio
engine: "this name rose" and "this position cleared its exit rules after costs"
are not the same claim, and until ``X4`` the two numbers had no shared definition.

This module closes that gap by handing the **same** loop
(:func:`book_replay.replay_book`) a *picks* entry provider. A pick ledger becomes a
per-session entry schedule and is replayed with the shared exit rules
(:func:`rules.evaluate_exit`), the shared cost model
(:class:`portfolio.CostModel`) and the shared metric conventions
(:func:`portfolio.compute_metrics`) — so 「推荐绩效」 and 「回测绩效」 are one
arithmetic on one book.

Contract (frozen in ``docs/contracts/picks-backtest.md``)
---------------------------------------------------------
- a **pick row** is ``{date, code, rank?, score?}``; ``date`` is the signal session
  (the brief's ``asof``), ``code`` the ticker as recommended (suffix optional)
- the **ledger** is append-only JSONL, deduplicated on ``(date, code)``, so
  regenerating one ``asof`` can never double-count a recommendation
- entries fill at the **pick session's reference close** (same as the engine). A
  pick for a session with no bar for that code is **dropped and counted**, never
  fabricated at a made-up price
- the picks replay defaults to ``universe="all"`` (a pick is honoured as
  recommended, ETF or stock) while the screener side of the comparison keeps its
  own ``stock`` baseline; whichever universe ran is echoed in ``params``
- fail-closed: an empty ledger / no bars ⇒ ``ok=False`` with a Chinese reason and
  **no** zero-filled curve

SIMULATE only. ``liveTradingEnabled=False``. Not investment advice.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from . import backtest as _backtest_mod
from . import book_replay as _book_replay_mod
from .backtest import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_STAMP_SELL_RATE,
    prepare_book_frame,
    run_portfolio_backtest,
)
from .book_replay import (
    EntryContext,
    EntryProvider,
    ReplayParams,
    empty_result,
    replay_book,
)
from .performance import append_jsonl, load_jsonl
from .portfolio import CostModel, compute_metrics
from .rules import CooldownPolicy, ExitPolicy
from .rules import evaluate_exit as _rules_evaluate_exit

PICK_LEDGER_FILENAME = "picks_ledger.jsonl"

ENV_PICKS_LEDGER = "STOCK_PLATFORM_PICKS_LEDGER"

# Metric keys compared in :func:`compare_picks_vs_screener` (numeric, same keys
# on both sides because both run ``portfolio.compute_metrics``).
_COMPARABLE_METRIC_KEYS: tuple[str, ...] = (
    "total_return",
    "cagr",
    "max_drawdown",
    "sharpe",
    "sortino",
    "calmar",
    "n_trades",
    "win_rate",
    "avg_hold_days",
    "turnover_per_year",
    "final_equity",
)


# --------------------------------------------------------------------------- #
# pick rows / brief extraction
# --------------------------------------------------------------------------- #


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out  # NaN-safe without importing math


def normalize_picks(picks: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """Coerce loose pick rows into the frozen ``{date, code, rank?, score?}`` shape.

    Accepts ``date``/``asof`` and ``code``/``symbol`` aliases (a brief and a ledger
    row are both accepted). Rows with no parseable date **or** no code are dropped
    rather than guessed at; exact ``(date, code)`` duplicates are collapsed,
    keeping the first occurrence.
    """
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in picks or []:
        if not isinstance(raw, Mapping):
            continue
        day = str(raw.get("date") or raw.get("asof") or "")[:10]
        code = str(raw.get("code") or raw.get("symbol") or "").strip()
        if not day or not code:
            continue
        key = (day, code)
        if key in seen:
            continue
        seen.add(key)
        row: dict[str, Any] = {"date": day, "code": code}
        rank = raw.get("rank")
        if rank is not None:
            try:
                row["rank"] = int(rank)
            except (TypeError, ValueError):
                pass
        score = raw.get("score", raw.get("composite_score"))
        score_f = _as_float(score)
        if score_f is not None:
            row["score"] = score_f
        out.append(row)
    return out


def picks_from_brief(
    brief: Mapping[str, Any],
    *,
    board: str | None = None,
) -> list[dict[str, Any]]:
    """Extract pick rows from a brief payload.

    ``board=None`` (default) reads ``brief["picks"]`` — the ②A quality head, whose
    meaning is frozen since ``X2``. ``board`` names a ranking-board *slug*
    (``quality`` / ``short_term`` / ``holdings`` / ``actions`` / ``watchlist``) and
    reads that board's ``items`` from ``brief["rankings"]["boards"]``. The
    session date is the brief's ``asof`` for every row.
    """
    asof = str(brief.get("asof") or "")[:10]
    if board is None:
        rows_in = list(brief.get("picks") or [])
    else:
        boards = ((brief.get("rankings") or {}).get("boards") or {})
        rows_in = list((boards.get(board) or {}).get("items") or [])
    out: list[dict[str, Any]] = []
    for raw in rows_in:
        if not isinstance(raw, Mapping):
            continue
        code = str(raw.get("symbol") or raw.get("code") or "").strip()
        if not asof or not code:
            continue
        row: dict[str, Any] = {"date": asof, "code": code}
        if raw.get("rank") is not None:
            try:
                row["rank"] = int(raw["rank"])
            except (TypeError, ValueError):
                pass
        score = _as_float(raw.get("composite_score", raw.get("score")))
        if score is not None:
            row["score"] = score
        out.append(row)
    # ``normalize_picks`` freezes the row to ``{date, code, rank?, score?}``; the
    # board slug is provenance, re-attached afterwards so the frozen shape holds.
    rows = normalize_picks(out)
    for row in rows:
        row["board"] = board or "picks"
    return rows


def picks_schedule(
    picks: Sequence[Mapping[str, Any]] | None,
) -> dict[str, list[dict[str, Any]]]:
    """Group pick rows by session date, ordered by ``rank`` (missing ranks last).

    ``rank`` is the recommendation's own ordering, so a session's entries are
    attempted top-down exactly as recommended. Rows without a rank keep their
    input order after the ranked ones.
    """
    schedule: dict[str, list[dict[str, Any]]] = {}
    for idx, row in enumerate(normalize_picks(picks)):
        schedule.setdefault(row["date"], []).append({**row, "_seq": idx})
    for day, rows in schedule.items():
        rows.sort(key=lambda r: (r.get("rank") is None, r.get("rank") or 0, r["_seq"]))
        for r in rows:
            r.pop("_seq", None)
    return schedule


# --------------------------------------------------------------------------- #
# entry provider
# --------------------------------------------------------------------------- #


def picks_entry_provider(schedule: Mapping[str, Sequence[Mapping[str, Any]]]) -> EntryProvider:
    """The *picks* entry provider — the day's scheduled codes, in rank order.

    The reference ``close`` is read from the **session frame**, never from the
    stored pick, so pricing is identical to the screener path; a scheduled code
    with no bar that session simply yields no candidate.
    """

    def _provider(ctx: EntryContext) -> list[dict[str, Any]]:
        rows = schedule.get(ctx.day)
        if not rows:
            return []
        px_by_code = dict(zip(ctx.frame["code"], ctx.frame["close"]))
        pct_by_code = (
            dict(zip(ctx.frame["code"], ctx.frame["pct_chg"]))
            if "pct_chg" in ctx.frame.columns
            else {}
        )
        out: list[dict[str, Any]] = []
        for row in rows:
            code = str(row.get("code"))
            px = px_by_code.get(code)
            if px is None or pd.isna(px):
                continue
            out.append({"code": code, "close": float(px), "pct_chg": pct_by_code.get(code)})
        return out

    return _provider


def _drop_unpriced_picks(
    feats: pd.DataFrame,
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split pick rows into (priced, dropped) against the sessions the frame has.

    Cheap by construction: only the picked codes are looked up, so this stays a
    small ``isin`` on the picked subset even for a full-market frame.
    """
    if not rows:
        return [], []
    picked_codes = {str(r["code"]) for r in rows}
    sub = feats[feats["code"].isin(picked_codes)]
    have = set(
        zip(
            sub["trade_date"].dt.strftime("%Y-%m-%d"),
            sub["code"].astype(str),
        )
    )
    priced: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for r in rows:
        (priced if (str(r["date"]), str(r["code"])) in have else dropped).append(dict(r))
    return priced, dropped


# --------------------------------------------------------------------------- #
# replay
# --------------------------------------------------------------------------- #


def _build_replay_params(
    *,
    initial_capital: float,
    max_positions: int,
    max_picks_per_day: int,
    lot_size: int,
    min_hold: int,
    max_hold_days: int,
    stop_loss: float,
    target_base: float,
    take_profit: float,
    trail_stop_pct: float,
    trail_min_peak_ret: float,
    commission_rate: float,
    stamp_sell_rate: float,
    slippage_bps: float,
    min_commission: float,
    cooldown_days: int,
    regime: Mapping[str, bool] | None,
) -> ReplayParams:
    """The shared loop's parameter bundle — built from the *same* knobs the
    screener backtest exposes, so a matched comparison is a matter of passing the
    same numbers."""
    return ReplayParams(
        initial_capital=initial_capital,
        max_positions=max_positions,
        max_picks_per_day=max_picks_per_day,
        lot_size=lot_size,
        exit_policy=ExitPolicy(
            stop_loss=stop_loss,
            take_profit=take_profit,
            target_base=target_base,
            trail_stop_pct=trail_stop_pct,
            trail_min_peak_ret=trail_min_peak_ret,
            min_hold=min_hold,
            max_hold_days=max_hold_days,
        ),
        cooldown_policy=CooldownPolicy(cooldown_days=int(cooldown_days)),
        cost_model=CostModel(
            commission_rate=commission_rate,
            stamp_sell_rate=stamp_sell_rate,
            slippage_bps=slippage_bps,
            min_commission=min_commission,
        ),
        regime=regime,
    )


def _params_echo(p: ReplayParams, *, universe: str, start: str | None, end: str | None,
                 pct_scale: str) -> dict[str, Any]:
    """Self-describing parameter block (same key set as the screener backtest)."""
    return {
        "max_picks_per_day": p.max_picks_per_day,
        "max_positions": p.max_positions,
        "min_hold": p.exit_policy.min_hold,
        "max_hold_days": p.exit_policy.max_hold_days,
        "stop_loss": p.exit_policy.stop_loss,
        "target_base": p.exit_policy.target_base,
        "take_profit": p.exit_policy.take_profit,
        "trail_stop_pct": p.exit_policy.trail_stop_pct,
        "commission_rate": p.cost_model.commission_rate,
        "stamp_sell_rate": p.cost_model.stamp_sell_rate,
        "slippage_bps": p.cost_model.slippage_bps,
        "min_commission": p.cost_model.min_commission,
        "universe": universe,
        "start": start,
        "end": end,
        "pct_scale": pct_scale,
        "cooldown_days": p.cooldown_policy.cooldown_days,
        "exit_policy": {
            "stop_loss": p.exit_policy.stop_loss,
            "take_profit": p.exit_policy.take_profit,
            "target_base": p.exit_policy.target_base,
            "trail_stop_pct": p.exit_policy.trail_stop_pct,
            "trail_min_peak_ret": p.exit_policy.trail_min_peak_ret,
            "min_hold": p.exit_policy.min_hold,
            "max_hold_days": p.exit_policy.max_hold_days,
            "trail_min_held": p.exit_policy.trail_min_held,
        },
    }


def run_picks_backtest(
    picks: Sequence[Mapping[str, Any]] | None,
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
    lot_size: int = 100,
    commission_rate: float = DEFAULT_COMMISSION_RATE,
    stamp_sell_rate: float = DEFAULT_STAMP_SELL_RATE,
    slippage_bps: float = 0.0,
    min_commission: float = 0.0,
    cooldown_days: int = 0,
    universe: str = "all",
    regime: Mapping[str, bool] | None = None,
    start: str | None = None,
    end: str | None = None,
    pct_scale: str = "auto",
    source: str = "picks",
) -> dict[str, Any]:
    """Replay a **pick ledger** through the shared engine (``X4``).

    Same knobs, same loop and same metric block as
    :func:`backtest.run_portfolio_backtest` — the only difference is the entry
    provider, which comes from the picks instead of the ``lvrev`` screener. That is
    what makes 「推荐绩效」and 「回测绩效」 comparable: identical arithmetic on the
    recommendation's own book.

    ``universe`` defaults to ``"all"`` so a pick is honoured as recommended (an ETF
    pick is not silently dropped by the stocks-only baseline). ``start`` / ``end``
    slice the replay window; picks outside it are counted in ``picksOutsideWindow``.
    """
    rows = normalize_picks(picks)
    if not rows:
        return {
            **empty_result(initial_capital, "picks 为空：无可回放的推荐"),
            "entrySource": source,
            "pickCount": 0,
            "scheduledSessions": 0,
            "droppedPicks": [],
            "picksOutsideWindow": [],
            "open_positions": [],
        }

    feats = prepare_book_frame(
        bars, universe=universe, start=None, end=None, pct_scale=pct_scale
    )
    if feats.empty:
        out = empty_result(initial_capital, "no bars in range")
        out["reason"] = "区间内无行情数据（fail-closed）"
        out.update(
            {
                "entrySource": source,
                "pickCount": len(rows),
                "scheduledSessions": len({r["date"] for r in rows}),
                "droppedPicks": [],
                "picksOutsideWindow": [],
                "open_positions": [],
            }
        )
        return out

    window_days = set(feats["trade_date"].dt.strftime("%Y-%m-%d"))
    in_window = [r for r in rows if str(r["date"]) in window_days]
    outside = [r for r in rows if str(r["date"]) not in window_days]

    priced, dropped = _drop_unpriced_picks(feats, in_window)

    params = _build_replay_params(
        initial_capital=initial_capital,
        max_positions=max_positions,
        max_picks_per_day=max_picks_per_day,
        lot_size=lot_size,
        min_hold=min_hold,
        max_hold_days=max_hold_days,
        stop_loss=stop_loss,
        target_base=target_base,
        take_profit=take_profit,
        trail_stop_pct=trail_stop_pct,
        trail_min_peak_ret=trail_min_peak_ret,
        commission_rate=commission_rate,
        stamp_sell_rate=stamp_sell_rate,
        slippage_bps=slippage_bps,
        min_commission=min_commission,
        cooldown_days=cooldown_days,
        regime=regime,
    )
    loop = replay_book(
        feats,
        entry_provider=picks_entry_provider(picks_schedule(priced)),
        params=params,
    )

    # ``ok`` means "the recommendations formed a book". A name still held when the
    # window closes is a real position even though it never reaches ``trades`` —
    # judging on closed round trips alone would call a live book "no trades".
    entered = sorted(
        {t["code"] for t in loop["trades"]}
        | {p["code"] for p in (loop.get("open_positions") or [])}
    )
    return {
        "ok": bool(entered),
        "entrySource": source,
        "pickCount": len(rows),
        "scheduledSessions": len({r["date"] for r in rows}),
        "pricedPicks": len(priced),
        "droppedPicks": dropped,
        "picksOutsideWindow": outside,
        "enteredCodes": entered,
        "reason": None
        if entered
        else "推荐在该窗口内未产生任何可成交建仓（缺行情 / 涨停 / 已满仓 / 资金不足）",
        "equity_curve": loop["equity_curve"],
        "trades": loop["trades"],
        "open_positions": loop.get("open_positions") or [],
        "n_days": loop["n_days"],
        "final_equity": loop["final_equity"],
        "initial_capital": loop["initial_capital"],
        "metrics": compute_metrics(
            loop["equity_curve"], loop["trades"], initial_capital=initial_capital
        ),
        "params": _params_echo(params, universe=universe, start=start, end=end, pct_scale=pct_scale),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "disclaimer": "Research only; not investment advice.",
    }


def compare_picks_vs_screener(
    picks: Sequence[Mapping[str, Any]] | None,
    bars: pd.DataFrame,
    *,
    picks_kwargs: Mapping[str, Any] | None = None,
    screener_kwargs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the picks replay **and** the screener backtest over the same bars.

    Both sides call the shared loop, so the metric keys are identical and the
    ``delta`` block is a straight key-by-key subtraction — no re-normalisation, no
    second metric definition. ``sameDefinition`` carries the identity proof.
    """
    picks_out = run_picks_backtest(picks, bars, **(dict(picks_kwargs or {})))
    screener_out = run_portfolio_backtest(bars, **(dict(screener_kwargs or {})))

    picks_metrics = picks_out.get("metrics") or {}
    screener_metrics = screener_out.get("metrics") or {}
    delta: dict[str, Any] = {}
    for key in _COMPARABLE_METRIC_KEYS:
        a = picks_metrics.get(key)
        b = screener_metrics.get(key)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            delta[key] = round(float(a) - float(b), 6)
        else:
            delta[key] = None

    shared = {
        "loop": "book_replay.replay_book",
        "picksEntryProvider": "picks_backtest.picks_entry_provider",
        "screenerEntryProvider": "book_replay.screener_entry_provider",
        "exitRule": "rules.evaluate_exit",
        "costModel": "portfolio.CostModel",
        "metrics": "portfolio.compute_metrics",
        # identity, not equality: both wrappers literally call *one* loop function,
        # and the loop's exit call is the very same object the rules layer defines.
        "singleLoopDefinition": _backtest_mod.replay_book is _book_replay_mod.replay_book,
        "singleExitDefinition": _book_replay_mod.evaluate_exit is _rules_evaluate_exit,
    }
    return {
        "ok": bool(picks_out.get("ok")) or bool(screener_out.get("ok")),
        "picks": picks_out,
        "screener": screener_out,
        "delta": delta,
        "deltaKeys": list(_COMPARABLE_METRIC_KEYS),
        "sameDefinition": shared,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "note": (
            "两侧同引擎同口径（book_replay.replay_book）；delta = picks 指标 − 回测指标；"
            "picks 侧默认 universe=all，回测侧默认 universe=stock（各自 params 有回显）。"
        ),
        "disclaimer": "研究口径对照；非投资建议；默认 SIMULATE。",
    }


# --------------------------------------------------------------------------- #
# ledger (append-only, deduped on (date, code))
# --------------------------------------------------------------------------- #


def default_picks_ledger_path() -> Path:
    """Resolve the ledger path from env, else a package-local default under cwd."""
    env = os.environ.get(ENV_PICKS_LEDGER)
    if env:
        return Path(env)
    return Path.cwd() / "data" / PICK_LEDGER_FILENAME


def load_picks_ledger(path: str | Path) -> list[dict[str, Any]]:
    """Read a picks ledger and coerce it to the frozen pick-row shape."""
    return normalize_picks(load_jsonl(path))


def append_picks_ledger(
    path: str | Path,
    picks: Sequence[Mapping[str, Any]] | None,
    *,
    skip_existing: bool = True,
) -> list[dict[str, Any]]:
    """Append pick rows to the ledger; skip ``(date, code)`` already present.

    Idempotent by default: re-running the same ``asof`` (or the same brief
    regeneration) appends nothing. Returns only the rows actually written.
    """
    rows = normalize_picks(picks)
    if not rows:
        return []
    existing: set[tuple[str, str]] = set()
    if skip_existing:
        for e in load_picks_ledger(path):
            existing.add((str(e["date"]), str(e["code"])))
    appended: list[dict[str, Any]] = []
    for row in rows:
        key = (str(row["date"]), str(row["code"]))
        if skip_existing and key in existing:
            continue
        append_jsonl(path, row)
        appended.append(row)
        existing.add(key)
    return appended
