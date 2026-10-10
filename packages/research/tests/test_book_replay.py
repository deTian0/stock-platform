"""``X4``: the shared replay loop is a **pure refactor** of the pre-X4 engine.

The digest fixture (``fixtures/book_replay_baseline.json``) was captured from
``run_portfolio_backtest`` *before* the loop moved into
:mod:`stock_platform_research.book_replay`. Eight scenarios — stocks, ETFs, mixed,
slippage, zero-cost, cooldown and the legacy ``verbatim`` pct scale — are pinned
by ``curve_sha256`` / ``trades_sha256`` plus the whole metric block, so any drift
in the extraction fails loudly instead of silently moving the baseline.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from stock_platform_research import backtest, book_replay, rules
from stock_platform_research.book_replay import ReplayParams, replay_book

FIXTURE = Path(__file__).parent / "fixtures" / "book_replay_baseline.json"


def _make_bars(series: dict[str, list[float]], start: str = "2023-01-02") -> pd.DataFrame:
    n = len(next(iter(series.values())))
    days = pd.bdate_range(start, periods=n)
    rows = []
    for code, prices in series.items():
        prev = None
        for d, p in zip(days, prices):
            pct = 0.0 if prev in (None, 0) else (p / prev - 1.0)
            rows.append(
                {
                    "code": code,
                    "date": d.date().isoformat(),
                    "close": float(p),
                    "pct_chg": float(pct),
                }
            )
            prev = p
    return pd.DataFrame(rows)


MIXED = {
    "600519.SH": [10.0 * (1.0 + 0.002 * i) for i in range(200)],
    "000001.SZ": [8.0 * (1.0 + 0.001 * i) for i in range(200)],
    "510300.SH": [4.0 * (1.0 + 0.0015 * i) for i in range(200)],
    "159915.SZ": [3.0 * (1.0 + 0.0012 * i) for i in range(200)],
}

# Must stay in lock-step with the digest fixture (same as baseline_capture.py).
SCENARIOS: dict[str, tuple[dict[str, list[float]], dict]] = {
    "stock_baseline": (MIXED, dict(min_pick_score=0.0, min_hold=5, max_positions=5, max_picks_per_day=2, universe="stock")),
    "all_mixed": (MIXED, dict(min_pick_score=0.0, min_hold=5, max_positions=5, max_picks_per_day=4, universe="all")),
    "etf_only": (MIXED, dict(min_pick_score=0.0, min_hold=5, max_positions=5, max_picks_per_day=4, universe="etf")),
    "slippage_50bp": (MIXED, dict(min_pick_score=0.0, min_hold=5, max_positions=3, max_picks_per_day=1, slippage_bps=50.0)),
    "cost_off": (MIXED, dict(min_pick_score=0.0, min_hold=5, max_positions=3, max_picks_per_day=1, commission_rate=0.0, stamp_sell_rate=0.0)),
    "cooldown_3": (MIXED, dict(min_pick_score=0.0, min_hold=5, max_positions=5, max_picks_per_day=3, cooldown_days=3)),
    "verbatim_scale": (MIXED, dict(min_pick_score=0.0, min_hold=5, max_positions=5, max_picks_per_day=3, pct_scale="verbatim")),
    "single_code": (
        {"600519.SH": [10.0 * (1.0 + 0.002 * i) for i in range(200)]},
        dict(min_pick_score=0.0, min_hold=5, max_positions=3, max_picks_per_day=1),
    ),
}


def _canon(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha(obj) -> str:
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


def test_pre_x4_baseline_is_bit_for_bit_identical():
    """The extraction moved no number: curve, trades and metrics are unchanged."""
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert set(expected) == set(SCENARIOS), "scenario set drifted from the fixture"

    for name, (series, kw) in SCENARIOS.items():
        res = backtest.run_portfolio_backtest(_make_bars(series), **kw)
        want = expected[name]
        assert res["n_days"] == want["n_days"], name
        assert res["final_equity"] == want["final_equity"], name
        assert res["initial_capital"] == want["initial_capital"], name
        assert len(res["trades"]) == want["trade_count"], name
        assert _sha(res["equity_curve"]) == want["curve_sha256"], f"{name}: equity curve drifted"
        assert _sha(res["trades"]) == want["trades_sha256"], f"{name}: trade log drifted"
        assert res["metrics"] == want["metrics"], f"{name}: metrics drifted"


def test_backtest_and_book_replay_are_one_function():
    """Identity, not equivalence — the wrapper re-exports the shared loop."""
    assert backtest.replay_book is book_replay.replay_book
    assert backtest.ReplayParams is book_replay.ReplayParams
    assert backtest.empty_result is book_replay.empty_result


def test_book_replay_uses_the_shared_rule_objects():
    """The loop must call the rules single definition, not a private copy."""
    assert book_replay.evaluate_exit is rules.evaluate_exit
    assert book_replay.advance_peak is rules.advance_peak
    assert book_replay.is_limit_up is rules.is_limit_up
    assert book_replay.is_limit_down is rules.is_limit_down
    assert book_replay.PositionState is rules.PositionState
    assert book_replay.ExitPolicy is rules.ExitPolicy
    assert book_replay.CooldownPolicy is rules.CooldownPolicy


def test_replay_params_defaults_are_the_baseline():
    p = ReplayParams()
    assert p.initial_capital == 50000.0
    assert (p.max_positions, p.max_picks_per_day, p.lot_size) == (15, 8, 100)
    assert p.exit_policy == rules.ExitPolicy()
    assert p.cooldown_policy.cooldown_days == 0
    assert p.regime is None


def test_replay_book_empty_frame_is_neutral():
    """An empty frame is a *wrapper-level* outcome: no ok/reason/metrics invented."""
    out = replay_book(pd.DataFrame(), entry_provider=lambda ctx: [], params=ReplayParams())
    assert out["n_days"] == 0
    assert out["equity_curve"] == []
    assert out["trades"] == []
    assert out["final_equity"] == 50000.0
    assert "metrics" not in out
    assert "ok" not in out


def test_entry_provider_cannot_bypass_max_positions():
    """The loop owns the caps — a greedy provider is still clamped."""
    bars = _make_bars({"600519.SH": [10.0 * (1.0 + 0.002 * i) for i in range(80)]})
    feats = backtest.prepare_book_frame(bars, universe="all")
    greedy = lambda ctx: [  # noqa: E731 — every session, unconditionally
        {"code": "600519.SH", "close": float(ctx.frame["close"].iloc[0]), "pct_chg": 0.0}
    ]
    out = replay_book(
        feats,
        entry_provider=greedy,
        params=ReplayParams(
            max_positions=1,
            max_picks_per_day=5,
            exit_policy=rules.ExitPolicy(min_hold=5),
        ),
    )
    assert all(point["n_positions"] <= 1 for point in out["equity_curve"])


def test_regime_false_blocks_entries_even_with_a_greedy_provider():
    bars = _make_bars({"600519.SH": [10.0 * (1.0 + 0.002 * i) for i in range(80)]})
    feats = backtest.prepare_book_frame(bars, universe="all")
    days = {d: False for d in bars["date"].unique()}
    greedy = lambda ctx: [  # noqa: E731
        {"code": "600519.SH", "close": float(ctx.frame["close"].iloc[0]), "pct_chg": 0.0}
    ]
    out = replay_book(
        feats,
        entry_provider=greedy,
        params=ReplayParams(
            max_positions=3,
            max_picks_per_day=1,
            exit_policy=rules.ExitPolicy(min_hold=5),
            regime=days,
        ),
    )
    assert out["trades"] == []
    assert all(point["n_positions"] == 0 for point in out["equity_curve"])
