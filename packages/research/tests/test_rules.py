"""Tests for the ``B5`` trading-rule single definition (``rules.py``)."""

from __future__ import annotations

from dataclasses import asdict

import pytest

from stock_platform_research import backtest, rules
from stock_platform_research.rules import (
    CooldownPolicy,
    DriftPolicy,
    ExitPolicy,
    advance_peak,
    evaluate_drift,
    evaluate_exit,
    is_limit_down,
    is_limit_up,
    limit_pct,
    portfolio_weights,
)


# ---------- single definition (the B5 contract) ----------

def test_backtest_reexports_the_very_same_rule_objects():
    """Both call paths must share one implementation — identity, not equality."""
    assert backtest.evaluate_exit is rules.evaluate_exit
    assert backtest.ExitPolicy is rules.ExitPolicy
    assert backtest.CooldownPolicy is rules.CooldownPolicy
    assert backtest.DriftPolicy is rules.DriftPolicy
    assert backtest.PositionState is rules.PositionState
    assert backtest.advance_peak is rules.advance_peak
    assert backtest.limit_pct is rules.limit_pct
    assert backtest.is_limit_up is rules.is_limit_up
    assert backtest.is_limit_down is rules.is_limit_down
    # the old private position type is an alias, not a second class
    assert backtest._Position is rules.PositionState


def test_default_policy_pins_the_b1_b4_baseline_values():
    p = ExitPolicy()
    assert (p.stop_loss, p.take_profit, p.target_base) == (8.0, 0.0, 5.0)
    assert (p.trail_stop_pct, p.trail_min_peak_ret, p.trail_min_held) == (6.0, 2.0, 3)
    assert (p.min_hold, p.max_hold_days) == (45, 60)
    # the new B5 knobs are off by default so the baseline cannot move
    assert CooldownPolicy().active is False
    assert DriftPolicy().active is False


def test_backtest_default_params_equal_rules_defaults():
    """Parameter consistency: the engine's defaults *are* the rules defaults."""
    import pandas as pd

    days = pd.bdate_range("2023-01-02", periods=80)
    bars = pd.DataFrame(
        [
            {"code": "600519.SH", "date": d.date().isoformat(), "close": 10.0 + i * 0.02, "pct_chg": 0.002}
            for i, d in enumerate(days)
        ]
    )
    res = backtest.run_portfolio_backtest(bars, min_pick_score=0.0)
    assert res["params"]["exit_policy"] == asdict(ExitPolicy())
    assert res["params"]["cooldown_days"] == 0
    assert res["params"]["drift_band"] is None


# ---------- exit branches (reason strings are frozen) ----------

def _call(**kw):
    base = dict(
        px=10.0, entry_price=10.0, target=10.5, peak=10.0, held_days=50,
        ma20=3.0, ma60=2.0, policy=ExitPolicy(),
    )
    base.update(kw)
    return evaluate_exit(**base)


def test_stop_loss_fires_and_formats_reason():
    d = _call(px=9.0)
    assert d is not None
    assert d.reason == "stop_loss(-10.0%)"
    assert d.ret_pct == pytest.approx(-10.0)


def test_stop_loss_bypasses_min_hold():
    d = _call(px=9.0, held_days=0)
    assert d is not None and d.reason.startswith("stop_loss(")


def test_take_profit_is_opt_in():
    assert _call(px=12.0, held_days=1) is None  # take_profit=0 → disabled
    d = _call(px=12.0, held_days=1, policy=ExitPolicy(take_profit=15.0))
    assert d is not None and d.reason == "take_profit(+20.0%)"


def test_min_hold_gates_discretionary_exits():
    # target reached but too early → hold
    assert _call(px=11.0, held_days=10) is None
    assert _call(px=11.0, held_days=45) is not None


def test_target_then_trend_break_then_trail_then_max_hold_priority():
    assert _call(px=10.6).reason == "target(+6.0%)"
    assert _call(px=10.4, ma20=1.0, ma60=2.0).reason == "trend_break(+4.0%)"
    # ma20 > ma60 disables trend_break; 6 % give-back from the peak → trailing
    assert _call(px=10.0, peak=10.7, ma20=3.0, ma60=2.0).reason == "trail_stop(+0.0%)"
    assert _call(px=10.0, peak=10.0, ma20=3.0, ma60=2.0, held_days=61).reason == "max_hold(61d)"


def test_trailing_needs_a_peak_above_the_threshold():
    # peak only +1 % → below trail_min_peak_ret=2 → no trailing exit
    assert _call(px=10.0, peak=10.1, ma20=3.0, ma60=2.0) is None


def test_missing_ma_is_treated_as_unavailable_not_zero():
    # ma20=None must NOT be read as 0 ≤ ma60 (which would fire trend_break)
    d = _call(px=10.1, ma20=None, ma60=None)
    assert d is None
    d = _call(px=10.1, ma20=float("nan"), ma60=2.0)
    assert d is None


def test_hold_returns_none():
    assert _call(px=10.1) is None


# ---------- helpers ----------

def test_advance_peak_only_moves_up():
    assert advance_peak(10.0, 11.0) == 11.0
    assert advance_peak(10.0, 9.0) == 10.0
    assert advance_peak(10.0, 10.0) == 10.0


def test_target_price():
    assert ExitPolicy().target_price(10.0) == pytest.approx(10.5)


def test_portfolio_weights_normalises_and_handles_empty():
    assert portfolio_weights([1.0, 1.0, 2.0]) == pytest.approx([0.25, 0.25, 0.5])
    assert portfolio_weights([]) == []
    assert portfolio_weights([0.0, 0.0]) == []


# ---------- cooldown (冷静期) ----------

def test_cooldown_blocks_window_and_default_off():
    assert CooldownPolicy(cooldown_days=3).blocks(last_exit_idx=10, current_idx=10) is True
    assert CooldownPolicy(cooldown_days=3).blocks(last_exit_idx=10, current_idx=12) is True
    assert CooldownPolicy(cooldown_days=3).blocks(last_exit_idx=10, current_idx=13) is False
    assert CooldownPolicy().blocks(last_exit_idx=10, current_idx=10) is False
    assert CooldownPolicy(cooldown_days=3).blocks(last_exit_idx=None, current_idx=50) is False


def test_cooldown_remaining():
    cd = CooldownPolicy(cooldown_days=3)
    assert cd.remaining(last_exit_idx=10, current_idx=10) == 3
    assert cd.remaining(last_exit_idx=10, current_idx=12) == 1
    assert cd.remaining(last_exit_idx=10, current_idx=13) == 0


# ---------- drift (持仓偏差) ----------

def test_drift_disabled_by_default():
    d = evaluate_drift(weight=0.5, target_weight=0.1)
    assert d.action == "hold" and d.deviation is None


def test_drift_trim_add_hold():
    p = DriftPolicy(band=0.30)
    assert evaluate_drift(weight=0.20, target_weight=0.10, policy=p).action == "trim"
    assert evaluate_drift(weight=0.01, target_weight=0.10, policy=p).action == "add"
    assert evaluate_drift(weight=0.11, target_weight=0.10, policy=p).action == "hold"


def test_drift_missing_inputs_never_fabricate():
    p = DriftPolicy(band=0.30)
    assert evaluate_drift(weight=None, target_weight=0.1, policy=p).action == "hold"
    assert evaluate_drift(weight=0.2, target_weight=None, policy=p).action == "hold"
    assert evaluate_drift(weight=0.2, target_weight=0.0, policy=p).action == "hold"


# ---------- price limits (shared tradeability) ----------

def test_limit_pct_by_board():
    assert limit_pct("600519.SH") == pytest.approx(0.10)
    assert limit_pct("000001.SZ") == pytest.approx(0.10)
    assert limit_pct("300750.SZ") == pytest.approx(0.20)
    assert limit_pct("688981.SH") == pytest.approx(0.20)
    assert limit_pct("600519.SH", is_st=True) == pytest.approx(0.05)


def test_limit_up_down_boundaries_match_the_b1_engine():
    assert is_limit_up("600519.SH", 9.98) is False
    assert is_limit_up("600519.SH", 9.99) is True   # eps = 0.01, as in B1
    assert is_limit_up("600519.SH", 10.0) is True
    assert is_limit_up("300750.SZ", 19.98) is False
    assert is_limit_up("300750.SZ", 19.99) is True
    assert is_limit_down("600519.SH", -9.98) is False
    assert is_limit_down("600519.SH", -9.99) is True
    assert is_limit_up("600519.SH", None) is False
    assert is_limit_up("600519.SH", float("nan")) is False
    assert is_limit_down("600519.SH", "not-a-number") is False
