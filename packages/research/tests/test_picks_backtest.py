"""``X4``: logged picks and the backtest run **one** engine on one set of rules."""

from __future__ import annotations

import pandas as pd
import pytest

from stock_platform_research import backtest
from stock_platform_research.picks_backtest import (
    append_picks_ledger,
    compare_picks_vs_screener,
    load_picks_ledger,
    normalize_picks,
    picks_from_brief,
    picks_schedule,
    run_picks_backtest,
)


def _make_bars(series: dict[str, list[float]], start: str = "2023-01-02") -> pd.DataFrame:
    n = len(next(iter(series.values())))
    days = pd.bdate_range(start, periods=n)
    rows = []
    for code, prices in series.items():
        prev = None
        for d, p in zip(days, prices):
            pct = 0.0 if prev in (None, 0) else (p / prev - 1.0)
            rows.append(
                {"code": code, "date": d.date().isoformat(), "close": float(p), "pct_chg": float(pct)}
            )
            prev = p
    return pd.DataFrame(rows)


SERIES = {
    "600519.SH": [10.0 * (1.0 + 0.002 * i) for i in range(200)],
    "000001.SZ": [8.0 * (1.0 + 0.001 * i) for i in range(200)],
    "510300.SH": [4.0 * (1.0 + 0.0015 * i) for i in range(200)],
}
BARS = _make_bars(SERIES)
DAYS = sorted(BARS["date"].unique())


# ---------- pick rows ----------


def test_normalize_picks_accepts_aliases_and_drops_bad_rows():
    rows = normalize_picks(
        [
            {"date": "2023-04-10", "code": "600519.SH", "rank": "2", "score": "0.9"},
            {"asof": "2023-04-10", "symbol": "000001.SZ"},          # alias keys
            {"date": "2023-04-10"},                                  # no code -> dropped
            {"code": "600519.SH"},                                   # no date -> dropped
            {"date": "2023-04-11", "code": "600519.SH", "rank": None, "score": "bad"},
            {"date": "2023-04-10", "code": "600519.SH"},             # duplicate (date, code)
            "not-a-mapping",                                         # dropped
        ]
    )
    assert [(r["date"], r["code"]) for r in rows] == [
        ("2023-04-10", "600519.SH"),
        ("2023-04-10", "000001.SZ"),
        ("2023-04-11", "600519.SH"),
    ]
    assert rows[0]["rank"] == 2 and rows[0]["score"] == 0.9
    assert "rank" not in rows[1]
    assert "score" not in rows[2]  # unparseable score is dropped, not zero-filled


def test_picks_schedule_groups_by_date_and_orders_by_rank():
    sched = picks_schedule(
        [
            {"date": "d1", "code": "C", "rank": 2},
            {"date": "d1", "code": "A", "rank": 1},
            {"date": "d2", "code": "B"},
            {"date": "d1", "code": "D"},  # no rank -> after the ranked ones
        ]
    )
    assert [r["code"] for r in sched["d1"]] == ["A", "C", "D"]
    assert [r["code"] for r in sched["d2"]] == ["B"]


def test_picks_from_brief_head_and_board_slug():
    brief = {
        "asof": "2026-10-09",
        "picks": [
            {"rank": 1, "symbol": "600519.SH", "composite_score": 0.91},
            {"rank": 2, "symbol": "000001.SZ", "composite_score": 0.88},
        ],
        "rankings": {"boards": {"quality": {"items": [{"rank": 1, "symbol": "600519.SH"}]}}},
    }
    head = picks_from_brief(brief)
    assert [(r["date"], r["code"], r["rank"]) for r in head] == [
        ("2026-10-09", "600519.SH", 1),
        ("2026-10-09", "000001.SZ", 2),
    ]
    assert head[0]["score"] == 0.91
    board = picks_from_brief(brief, board="quality")
    assert [r["code"] for r in board] == ["600519.SH"]
    assert board[0]["board"] == "quality"


# ---------- replay contract ----------


def test_picks_replay_reports_the_same_contract_as_the_backtest():
    picks = [
        {"date": DAYS[70], "code": "600519.SH", "rank": 1},
        {"date": DAYS[90], "code": "000001.SZ", "rank": 1},
    ]
    res = run_picks_backtest(picks, BARS, min_hold=5, max_positions=5)
    assert res["ok"] is True
    assert res["entrySource"] == "picks"
    for key in (
        "equity_curve", "trades", "open_positions", "n_days", "final_equity", "initial_capital",
        "metrics", "params", "environment", "liveTradingEnabled", "disclaimer",
    ):
        assert key in res, key
    assert res["environment"] == "SIMULATE"
    assert res["liveTradingEnabled"] is False
    # the params echo is self-describing (same key set as the screener backtest)
    for key in ("exit_policy", "cooldown_days", "universe", "slippage_bps", "pct_scale"):
        assert key in res["params"], key


def test_picks_replay_is_bit_for_bit_the_screener_engine():
    """Same schedule ⇒ same book: the strongest available parity proof.

    ``max_picks_per_day=1`` makes the screener's entry schedule unambiguous, so the
    realised ``(date, code)`` pairs can be fed straight back in as picks. Both runs
    must then produce an identical trade log and equity curve — they are one loop.

    Open positions are appended too: a name still held when the window ends never
    reaches ``trades``, and dropping it would make the schedule incomplete.
    """
    kw = dict(min_pick_score=0.0, min_hold=5, max_positions=2, max_picks_per_day=1, universe="all")
    screener = backtest.run_portfolio_backtest(BARS, **kw)
    assert screener["trades"], "scenario must trade for the parity check to mean anything"

    feats = backtest.prepare_book_frame(BARS, universe="all")
    sessions = sorted(feats["trade_date"].dt.strftime("%Y-%m-%d").unique())
    entries = [(t["entry_idx"], t["code"]) for t in screener["trades"]]
    entries += [(p["entry_idx"], p["code"]) for p in screener["open_positions"]]
    picks = [
        {"date": sessions[idx], "code": code, "rank": i}
        for i, (idx, code) in enumerate(entries)
    ]
    picks_out = run_picks_backtest(picks, BARS, **{k: v for k, v in kw.items() if k != "min_pick_score"})

    assert picks_out["n_days"] == screener["n_days"]
    assert picks_out["trades"] == screener["trades"]
    assert picks_out["equity_curve"] == screener["equity_curve"]
    assert picks_out["metrics"] == screener["metrics"]
    assert len(picks_out["open_positions"]) == len(screener["open_positions"])


def test_picks_replay_respects_the_shared_exit_rules():
    """A pick that only ever falls is stopped out by the shared stop-loss."""
    falling = {"600519.SH": [10.0 * (1.0 - 0.004 * i) for i in range(120)]}
    bars = _make_bars(falling)
    days = sorted(bars["date"].unique())
    res = run_picks_backtest(
        [{"date": days[10], "code": "600519.SH"}], bars, stop_loss=8.0, min_hold=5
    )
    assert res["trades"], "a -8% path must trip the stop"
    assert res["trades"][0]["reason"].startswith("stop_loss(")


def test_ok_counts_a_still_open_position_as_entered():
    """A pick still held when the window closes is a book, not 'no trades'.

    Entry near the end of a gentle rise: fewer than ``min_hold`` sessions remain, so
    no discretionary exit can fire and nothing trips the protective stops. The only
    evidence of the entry is ``open_positions`` — and ``ok`` must reflect it.
    """
    rising = {"600519.SH": [10.0 + 0.01 * i for i in range(60)]}
    bars = _make_bars(rising)
    days = sorted(bars["date"].unique())
    res = run_picks_backtest([{"date": days[55], "code": "600519.SH"}], bars)
    assert res["trades"] == []
    assert res["open_positions"], "the entry must show up as an open position"
    assert res["ok"] is True
    assert res["reason"] is None
    assert res["enteredCodes"] == ["600519.SH"]


def test_universe_stock_drops_an_etf_pick():
    picks = [{"date": DAYS[70], "code": "510300.SH", "rank": 1}]
    all_book = run_picks_backtest(picks, BARS, min_hold=5, universe="all")
    stock_book = run_picks_backtest(picks, BARS, min_hold=5, universe="stock")
    assert all_book["trades"], "the ETF pick must trade under universe=all"
    assert stock_book["trades"] == []  # dropped by the stocks-only filter


def test_empty_picks_is_fail_closed():
    res = run_picks_backtest([], BARS)
    assert res["ok"] is False
    assert "picks 为空" in res["reason"]
    assert res["equity_curve"] == []
    assert res["metrics"]["n_days"] == 0


def test_unpriced_and_out_of_window_picks_are_counted_not_guessed():
    picks = [
        {"date": DAYS[70], "code": "600519.SH", "rank": 1},   # priced
        {"date": DAYS[70], "code": "999999.SZ", "rank": 2},   # no bar -> dropped
        {"date": "1999-01-01", "code": "600519.SH", "rank": 3},  # outside the frame
    ]
    res = run_picks_backtest(picks, BARS, min_hold=5)
    assert res["pickCount"] == 3
    assert [d["code"] for d in res["droppedPicks"]] == ["999999.SZ"]
    assert [d["date"] for d in res["picksOutsideWindow"]] == ["1999-01-01"]
    assert res["pricedPicks"] == 1


# ---------- comparison ----------


def test_compare_reports_a_key_by_key_delta_and_an_identity_proof():
    picks = [
        {"date": DAYS[70], "code": "600519.SH", "rank": 1},
        {"date": DAYS[90], "code": "000001.SZ", "rank": 1},
    ]
    out = compare_picks_vs_screener(
        picks,
        BARS,
        picks_kwargs=dict(min_hold=5, max_positions=5),
        screener_kwargs=dict(min_pick_score=0.0, min_hold=5, max_positions=5, max_picks_per_day=2),
    )
    assert set(out["delta"]) == set(out["deltaKeys"])
    assert out["sameDefinition"]["singleLoopDefinition"] is True
    assert out["sameDefinition"]["singleExitDefinition"] is True
    assert out["sameDefinition"]["loop"] == "book_replay.replay_book"
    # delta is a straight subtraction of identical metric conventions
    p = out["picks"]["metrics"]
    s = out["screener"]["metrics"]
    assert out["delta"]["total_return"] == pytest.approx(
        round(p["total_return"] - s["total_return"], 6)
    )
    assert out["delta"]["final_equity"] == pytest.approx(
        round(p["final_equity"] - s["final_equity"], 6)
    )


# ---------- ledger ----------


def test_ledger_append_is_idempotent_on_date_and_code(tmp_path):
    path = tmp_path / "picks_ledger.jsonl"
    picks = [
        {"date": "2026-10-09", "code": "600519.SH", "rank": 1},
        {"date": "2026-10-09", "code": "000001.SZ", "rank": 2},
    ]
    first = append_picks_ledger(path, picks)
    second = append_picks_ledger(path, picks)
    third = append_picks_ledger(path, picks + [{"date": "2026-10-10", "code": "600519.SH"}])

    assert len(first) == 2
    assert second == []            # same asof regenerated -> no double count
    assert len(third) == 1         # only the genuinely new session/code
    assert len(load_picks_ledger(path)) == 3
    # round-trips to the frozen pick-row shape
    assert load_picks_ledger(path)[0] == {"date": "2026-10-09", "code": "600519.SH", "rank": 1}


def test_ledger_round_trips_into_a_replay(tmp_path):
    path = tmp_path / "picks_ledger.jsonl"
    append_picks_ledger(path, [{"date": DAYS[70], "code": "600519.SH", "rank": 1}])
    res = run_picks_backtest(load_picks_ledger(path), BARS, min_hold=5)
    assert res["trades"], "a ledger round-trip must still be replayable"
