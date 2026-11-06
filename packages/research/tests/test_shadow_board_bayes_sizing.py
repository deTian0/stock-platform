"""Set B Beta-prior sizing (docs/plans/multi-strategy-final-board.md §11.9).

Pins: (1) zero sample → multiplier exactly 1.0 (D-equivalent); (2) PIT: a trade is
visible only when ``exit_idx < signal day``; (3) attribution via the loop's entry
record; (4) default-off replay is bit-identical to the pre-knob budget; (5) the
four pre-registered criteria, all-or-nothing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from stock_platform_research.book_replay import ReplayParams, replay_book
from stock_platform_research.shadow_board import bayes_sizing as bs
from stock_platform_research.shadow_board.backtest import (
    prepare_shadow_frame,
    run_shadow_book,
)


def test_zero_sample_multiplier_is_exactly_one():
    assert bs.slot_multiplier([]) == 1.0
    assert bs.posterior_expected_return([]) == 0.0


def test_multiplier_is_clipped_and_directional():
    winners = [8.0] * 60
    losers = [-8.0] * 60
    assert bs.slot_multiplier(winners) == bs.MULT_HI
    assert bs.slot_multiplier(losers) == bs.MULT_LO
    assert bs.slot_multiplier([1.0, -1.0]) < 1.5


def test_window_keeps_only_most_recent_trades():
    old_losers = [-20.0] * 30
    recent_winners = [6.0] * bs.WINDOW
    # Old losses fall outside the rolling window → only winners count.
    assert bs.slot_multiplier(old_losers + recent_winners) == bs.slot_multiplier(recent_winners)


def test_pit_excludes_trades_not_strictly_closed_before_signal_day():
    trades = [
        {"code": "600000.SH", "entry_idx": 0, "exit_idx": 5, "net_ret": -9.0},
        {"code": "600000.SH", "entry_idx": 0, "exit_idx": 10, "net_ret": -9.0},
    ]
    school = {(0, "600000.SH"): "S3"}
    # Signal day 5: exit on day 5 is NOT visible (same-session close) → no sample.
    assert bs.bayes_school_mults(trades, school, 5) == {}
    # Signal day 6: only the exit at 5 is visible.
    assert "S3" in bs.bayes_school_mults(trades, school, 6)
    # Signal day 11: both visible.
    m_both = bs.bayes_school_mults(trades, school, 11)["S3"]
    m_one = bs.bayes_school_mults(trades, school, 6)["S3"]
    assert m_both < m_one


def test_attribution_follows_entry_school_record():
    trades = [{"code": "600001.SH", "entry_idx": 2, "exit_idx": 3, "net_ret": 4.0}]
    assert bs.bayes_school_mults(trades, {(2, "600001.SH"): "S1"}, 9) == {
        "S1": bs.slot_multiplier([4.0])
    }
    assert bs.bayes_school_mults(trades, {}, 9) == {}


def _bars(seed: int = 7, n_codes: int = 20, n_days: int = 150) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2025-01-02", periods=n_days)
    rows = []
    for i in range(n_codes):
        px = 10.0 + i
        for d in days:
            pct = float(np.clip(rng.normal(0.1, 2.0), -9.0, 9.0))
            px *= 1.0 + pct / 100.0
            rows.append(
                {
                    "code": f"{600000 + i:06d}.SH",
                    "date": d.date().isoformat(),
                    "close": round(px, 3),
                    "pct_chg": round(pct, 4),
                    "amount": 5e7,
                }
            )
    return pd.DataFrame(rows)


def test_default_off_budget_is_bit_identical_to_factory():
    """A row without ``slot_mult`` and one with ``slot_mult=1.0`` size identically."""
    feats = prepare_shadow_frame(_bars(), industry_map=None)
    params = ReplayParams(initial_capital=50000.0, max_positions=5, max_picks_per_day=3)

    def provider_with(mult):
        def _p(ctx):
            rows = []
            for code, px, pct in zip(
                ctx.frame["code"], ctx.frame["close"], ctx.frame["pct_chg"]
            ):
                row = {"code": str(code), "close": float(px), "pct_chg": float(pct)}
                if mult is not None:
                    row["slot_mult"] = mult
                rows.append(row)
                if len(rows) >= 3:
                    break
            return rows

        return _p

    a = replay_book(feats, entry_provider=provider_with(None), params=params)
    b = replay_book(feats, entry_provider=provider_with(1.0), params=params)
    assert a["equity_curve"] == b["equity_curve"]
    assert a["trades"] == b["trades"]


def test_run_shadow_book_default_has_no_bayes_flag_and_matches_explicit_off():
    feats = prepare_shadow_frame(_bars(), industry_map=None)
    p = ReplayParams(initial_capital=50000.0, max_positions=5)
    default = run_shadow_book(feats, params=p, top_k=4)
    off = run_shadow_book(feats, params=p, top_k=4, bayes_sizing=False)
    assert default["equityCurve"] == off["equityCurve"]
    assert default["trades"] == off["trades"]
    assert "bayesSizing" not in default["shadow"]


def _arm(total, sharpe, mdd, trades=10):
    return {
        "metrics": {"total_return": total, "sharpe": sharpe, "max_drawdown": mdd},
        "trades": [{}] * trades,
    }


def _years(rets, sharpes):
    return {
        str(2021 + i): {"total_return": r, "sharpe": s}
        for i, (r, s) in enumerate(zip(rets, sharpes))
    }


def test_criteria_all_pass():
    d = _arm(0.10, 0.20, -0.25)
    b = _arm(0.15, 0.30, -0.26)
    dy = _years([0.02] * 6, [0.1] * 6)
    by = _years([0.03] * 6, [0.2, 0.2, 0.2, 0.2, 0.05, 0.05])
    out = bs.evaluate_bayes_criteria(d, b, dy, by)
    assert out["passed"] is True
    # Last two years: B sharpe 0.05 < D sharpe 0.1 → 4 of 6 years win (C3 needs ≥ 4).
    assert out["c3"]["sharpe_wins"] == 4


def test_criteria_fail_on_drawdown_beyond_two_points():
    d = _arm(0.10, 0.20, -0.25)
    b = _arm(0.15, 0.30, -0.28)  # 3pp deeper → C2 fails
    dy = _years([0.02] * 6, [0.1] * 6)
    by = _years([0.03] * 6, [0.2] * 6)
    out = bs.evaluate_bayes_criteria(d, b, dy, by)
    assert out["c2"]["ok"] is False
    assert out["passed"] is False


def test_criteria_fail_on_single_year_concentration():
    d = _arm(0.10, 0.20, -0.25)
    b = _arm(0.15, 0.30, -0.25)
    dy = _years([0.0] * 6, [0.1] * 6)
    # All excess in 2024 → contribution 100% > 60%.
    by = _years([0.0, 0.0, 0.0, 0.10, 0.0, 0.0], [0.2] * 6)
    out = bs.evaluate_bayes_criteria(d, b, dy, by)
    assert out["c4"]["ok"] is False
    assert out["passed"] is False


def test_render_markdown_has_verdict_line():
    payload = {
        "ok": True,
        "start": "2021-01-04",
        "end": "2026-11-05",
        "d": {"metrics": {"total_return": 0.1, "sharpe": 0.2, "max_drawdown": -0.2},
              "excessReturn": None},
        "b": {"metrics": {"total_return": 0.12, "sharpe": 0.25, "max_drawdown": -0.2},
              "excessReturn": None},
        "years": {"d": _years([0.02] * 6, [0.1] * 6), "b": _years([0.03] * 6, [0.2] * 6)},
        "criteria": bs.evaluate_bayes_criteria(
            _arm(0.1, 0.2, -0.2), _arm(0.12, 0.25, -0.2),
            _years([0.02] * 6, [0.1] * 6), _years([0.03] * 6, [0.2] * 6),
        ),
        "limitations": ["x"],
        "disclaimer": "d",
    }
    md = bs.render_bayes_markdown(payload)
    assert "总判：通过" in md
    assert "| 2021 |" in md
