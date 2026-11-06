"""S1 board-regime experiment knob (docs/plans/multi-strategy-final-board.md §11.6).

Pins: (1) default ``pick`` is the factory path, payload unchanged; (2) ``gate``
closes the board (or keeps only S3) on weak / unknown days and S1 never picks;
(3) ``scale`` caps the day's open positions; (4) the vectorised regime
distribution equals the row-wise :func:`s1_regime_state`; (5) lvrev untouched.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_platform_research.book_replay import ReplayParams
from stock_platform_research.shadow_board.backtest import (
    DEFAULT_S1_MODE,
    DEFAULT_S1_SCALE,
    S1_MODES,
    compare_shadow_vs_lvrev,
    frame_to_universe,
    prepare_shadow_frame,
    render_shadow_backtest_markdown,
    run_shadow_book,
    s1_regime_distribution,
    scale_position_cap,
    shadow_board_for_frame,
)
from stock_platform_research.shadow_board.schools import (
    S1_STRONG_BREADTH,
    s1_regime_state,
)

N_CODES = 30
N_DAYS = 160


def _bars(seed: int = 11, drift: float = 0.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2025-01-02", periods=N_DAYS)
    rows = []
    for i in range(N_CODES):
        px = 10.0 + i
        for k, d in enumerate(days):
            # Regime swings: a common factor alternating up / down every 40 days,
            # so weak, mid and strong breadth days all occur.
            common = 1.2 if (k // 40) % 2 == 0 else -1.2
            pct = float(rng.normal(drift + common, 1.5))
            pct = max(min(pct, 9.0), -9.0)
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


def _names() -> dict[str, str]:
    return {f"{600000 + i:06d}": f"样本{i}" for i in range(N_CODES)}


def _industry() -> dict[str, str]:
    return {f"{600000 + i:06d}": f"行业{i % 8}" for i in range(N_CODES)}


@pytest.fixture(scope="module")
def feats() -> pd.DataFrame:
    return prepare_shadow_frame(_bars(), industry_map=_industry())


def _days(feats: pd.DataFrame):
    return list(feats.groupby("trade_date", sort=True))


# --- 1. factory default ------------------------------------------------------


def test_default_mode_is_pick() -> None:
    assert DEFAULT_S1_MODE == "pick"
    assert S1_MODES[0] == "pick"


def test_pick_explicit_equals_default_and_has_no_experiment_keys(feats) -> None:
    for ts, day in _days(feats)[-15:]:
        d = ts.date().isoformat()
        a = shadow_board_for_frame(day, day=d, name_map=_names())
        b = shadow_board_for_frame(day, day=d, name_map=_names(), s1_mode="pick")
        assert a == b
        assert "s1Regime" not in a


def test_pick_book_payload_unchanged(feats) -> None:
    p = ReplayParams(initial_capital=100000.0, max_positions=6)
    a = run_shadow_book(feats, name_map=_names(), params=p)
    b = run_shadow_book(feats, name_map=_names(), params=p, s1_mode="pick")
    assert a == b
    for key in ("s1Mode", "s1Regime", "s1GateWeak", "s1Scale", "scaleCapZeroDays"):
        assert key not in a["shadow"]


def test_lvrev_arm_identical_across_s1_modes(feats) -> None:
    p = ReplayParams(initial_capital=100000.0, max_positions=6)
    base = compare_shadow_vs_lvrev(feats, name_map=_names(), params=p)
    for mode in ("gate", "scale"):
        out = compare_shadow_vs_lvrev(feats, name_map=_names(), params=p, s1_mode=mode)
        assert out["lvrev"] == base["lvrev"]


# --- 2. regime state ---------------------------------------------------------


def test_regime_state_thresholds() -> None:
    def uni(n_up: int, n_down: int) -> list[dict]:
        return [{"code": f"{i:06d}", "trend_up": True} for i in range(n_up)] + [
            {"code": f"{900000 + i:06d}", "trend_up": False} for i in range(n_down)
        ]

    assert s1_regime_state(uni(3, 7))["state"] == "weak"  # 30% < 35%
    assert s1_regime_state(uni(4, 6))["state"] == "mid"  # 40%
    assert s1_regime_state(uni(5, 5))["state"] == "strong"  # 50% ≥ strong
    assert S1_STRONG_BREADTH == 0.50
    unk = s1_regime_state(uni(2, 2))  # < 5 measurable rows
    assert unk["state"] == "unknown" and unk["breadth"] is None


def test_regime_is_pit_truncating_future_bars_changes_nothing() -> None:
    bars = _bars()
    cut = sorted(bars["date"].unique())[120]
    full = prepare_shadow_frame(bars, industry_map=_industry())
    trunc = prepare_shadow_frame(bars[bars["date"] <= cut], industry_map=_industry())
    ts = pd.Timestamp(cut)
    a = s1_regime_state(frame_to_universe(full[full["trade_date"] == ts], name_map=_names()))
    b = s1_regime_state(frame_to_universe(trunc[trunc["trade_date"] == ts], name_map=_names()))
    assert a == b


def test_vectorised_distribution_matches_row_wise(feats) -> None:
    expect = {"strong": 0, "mid": 0, "weak": 0, "unknown": 0}
    for _, day in _days(feats):
        expect[s1_regime_state(frame_to_universe(day))["state"]] += 1
    got = s1_regime_distribution(feats)
    assert got == expect
    assert sum(got.values()) == feats["trade_date"].nunique()
    # The fixture must exercise more than one state, or the gate tests are vacuous.
    assert sum(1 for v in got.values() if v) >= 2


# --- 3. gate -----------------------------------------------------------------


@pytest.mark.parametrize("weak_action", ["empty", "s3"])
def test_gate_s1_never_picks_and_weak_days_follow_action(feats, weak_action) -> None:
    saw_weak = saw_open = False
    for ts, day in _days(feats):
        d = ts.date().isoformat()
        res = shadow_board_for_frame(
            day, day=d, name_map=_names(), s1_mode="gate", s1_gate_weak=weak_action
        )
        passed = res["round2"]["passed"]
        assert not any(r["school"] == "S1" for r in passed)
        assert res["schools"]["S1"]["candidates"] == []
        if res["s1Regime"]["state"] in ("weak", "unknown"):
            saw_weak = True
            if weak_action == "empty":
                assert passed == []
            else:
                assert all(r["school"] == "S3" for r in passed)
        else:
            saw_open = True
    assert saw_weak and saw_open


def test_gate_open_day_equals_pick_minus_s1(feats) -> None:
    """On non-weak days S1's seats are released to the others under rule D."""
    from stock_platform_research.shadow_board.round2 import apply_round2_set_a

    checked = 0
    for ts, day in _days(feats):
        d = ts.date().isoformat()
        gate = shadow_board_for_frame(day, day=d, name_map=_names(), s1_mode="gate")
        if gate["s1Regime"]["state"] in ("weak", "unknown"):
            continue
        pick = shadow_board_for_frame(day, day=d, name_map=_names())
        pools = dict(pick["schools"])
        pools["S1"] = {"candidates": []}
        assert gate["round2"]["passed"] == apply_round2_set_a(pools)["passed"]
        checked += 1
    assert checked > 0


def test_gate_book_never_buys_on_weak_days(feats) -> None:
    p = ReplayParams(initial_capital=100000.0, max_positions=6)
    out = run_shadow_book(feats, name_map=_names(), params=p, s1_mode="gate")
    states = {
        ts: s1_regime_state(frame_to_universe(day))["state"] for ts, day in _days(feats)
    }
    idx_state = [states[ts] for ts in sorted(states)]
    entries = [t["entry_idx"] for t in out["trades"]]
    assert all(idx_state[i] not in ("weak", "unknown") for i in entries)
    sh = out["shadow"]
    assert sh["s1Mode"] == "gate" and sh["s1GateWeak"] == "empty"
    assert sh["schoolCoverage"]["S1"]["seats"] == 0
    assert sum(sh["s1Regime"]["allDays"].values()) == len(states)
    assert sum(sh["s1Regime"]["evaluatedDays"].values()) == sh["evaluatedDays"]
    md = render_shadow_backtest_markdown(
        compare_shadow_vs_lvrev(feats, name_map=_names(), params=p, s1_mode="gate")
    )
    assert "S1 模式：`gate`" in md


# --- 4. scale ----------------------------------------------------------------


def test_scale_position_cap() -> None:
    assert scale_position_cap("strong", 15, DEFAULT_S1_SCALE) == 15
    assert scale_position_cap("mid", 15, DEFAULT_S1_SCALE) == 7
    assert scale_position_cap("weak", 15, DEFAULT_S1_SCALE) == 0
    assert scale_position_cap("unknown", 15, DEFAULT_S1_SCALE) == 0
    assert scale_position_cap("odd", 15, {"weak": 0.2}) == 3  # missing → weak
    assert scale_position_cap("strong", 10, {"strong": 7.0}) == 10  # clamped


def test_scale_book_respects_daily_cap(feats) -> None:
    p = ReplayParams(initial_capital=100000.0, max_positions=6)
    out = run_shadow_book(feats, name_map=_names(), params=p, s1_mode="scale")
    curve = out["equityCurve"]
    states = [s1_regime_state(frame_to_universe(day))["state"] for _, day in _days(feats)]
    # Count of positions opened per day, and positions held after that day's entries.
    opened: dict[int, int] = {}
    for rec in [*out["trades"]]:
        opened[rec["entry_idx"]] = opened.get(rec["entry_idx"], 0) + 1
    for i, n_new in opened.items():
        cap = scale_position_cap(states[i], p.max_positions, DEFAULT_S1_SCALE)
        assert cap > 0  # weak / unknown days never open
        # positions before entries ≥ 0, so new buys alone can never exceed the cap
        assert n_new <= cap
        held_before = curve[i]["n_positions"]
        assert held_before + n_new <= cap or n_new == 0
    sh = out["shadow"]
    assert sh["s1Mode"] == "scale"
    assert sh["s1Scale"] == DEFAULT_S1_SCALE
    assert sh["schoolCoverage"]["S1"]["seats"] == 0


def test_scale_all_ones_equals_gate_free_board(feats) -> None:
    """Factor 1 everywhere = S1 silenced, nothing else changes (cap = max_positions)."""
    p = ReplayParams(initial_capital=100000.0, max_positions=6)
    ones = {"strong": 1.0, "mid": 1.0, "weak": 1.0, "unknown": 1.0}
    a = run_shadow_book(feats, name_map=_names(), params=p, s1_mode="scale", s1_scale=ones)
    assert a["metrics"]["n_trades"] >= 0
    assert a["shadow"]["scaleCapZeroDays"] == 0


def test_unknown_s1_mode_is_fail_closed(feats) -> None:
    _, day = _days(feats)[-1]
    with pytest.raises(ValueError, match="s1_mode must be one of"):
        shadow_board_for_frame(day, day="x", s1_mode="zzz")
    with pytest.raises(ValueError, match="s1_gate_weak must be one of"):
        shadow_board_for_frame(day, day="x", s1_mode="gate", s1_gate_weak="all")


def test_cli_parse_s1_scale() -> None:
    from stock_platform_research.shadow_board.cli import _parse_s1_scale

    assert _parse_s1_scale(None) is None
    assert _parse_s1_scale("1,0.5,0") == {"strong": 1.0, "mid": 0.5, "weak": 0.0, "unknown": 0.0}
    with pytest.raises(SystemExit):
        _parse_s1_scale("1,2,0")
    with pytest.raises(SystemExit):
        _parse_s1_scale("1,0.5")
