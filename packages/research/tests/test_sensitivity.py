"""``S3``: entry-gate sensitivity sweep + the ``EntryGateParams`` single point.

Two layers are pinned:

* the **pure** verdict kernel :func:`sensitivity.summarize_sweep` (robust /
  fragile / flat / insufficient, plus the ``min`` direction) — no engine needed;
* the **integration** path :func:`sensitivity.sweep_entry_gate` /
  :func:`sensitivity.build_sensitivity_report` on a synthetic feature frame —
  contract only (grid preserved, metrics attached, fail-closed on bad input).
"""

from __future__ import annotations

import pandas as pd
import pytest

from stock_platform_research.backtest import prepare_book_frame
from stock_platform_research.book_replay import ReplayParams
from stock_platform_research.gates import EntryGateParams, apply_entry_gates
from stock_platform_research.sensitivity import (
    DEFAULT_GRIDS,
    SWEEP_KNOBS,
    build_sensitivity_report,
    gate_params_for,
    score_floor_for,
    summarize_sweep,
    sweep_entry_gate,
)

NAN = float("nan")


# ---------------------------------------------------------------------------
# EntryGateParams single point
# ---------------------------------------------------------------------------
def _gate_frame() -> pd.DataFrame:
    close = [10.0, 12.0, 9.5, 20.0, 7.0, 15.0]
    ma20 = [9.0, 9.5, 9.6, 18.0, 8.0, 14.0]
    ma60 = [8.5, 8.6, 8.7, 17.0, 9.0, 13.0]  # last row: ma20(14) > ma60(13) ok
    vol20 = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06]
    rev_chg = [-0.30, -0.10, 0.00, 0.10, 0.20, 0.30]
    return pd.DataFrame(
        {"close": close, "ma20": ma20, "ma60": ma60, "vol20": vol20, "rev_chg": rev_chg}
    )


def test_default_params_reproduce_pre_s3_behaviour():
    df = _gate_frame()
    assert list(apply_entry_gates(df)) == list(apply_entry_gates(df, reversal_q=0.30))
    assert list(apply_entry_gates(df)) == list(apply_entry_gates(df, params=EntryGateParams()))


def test_explicit_reversal_q_overrides_params():
    df = _gate_frame()
    loose = apply_entry_gates(df, params=EntryGateParams(reversal_q=0.90))
    overridden = apply_entry_gates(df, 0.10, params=EntryGateParams(reversal_q=0.90))
    assert list(overridden) == list(apply_entry_gates(df, reversal_q=0.10))


def test_narrow_ma_band_never_removes_rows():
    df = _gate_frame()
    base = apply_entry_gates(df)
    # The band is a *rejection* floor: reject when ``close < ma * band``. A
    # smaller band therefore rejects fewer rows — it can only admit more.
    narrow = apply_entry_gates(df, params=EntryGateParams(ma20_band=0.5, ma60_band=0.5))
    assert int(narrow.sum()) >= int(base.sum())


def test_vol_filter_off_never_removes_rows():
    df = _gate_frame()
    off = apply_entry_gates(df, params=EntryGateParams(vol_filter=False))
    on = apply_entry_gates(df, params=EntryGateParams(vol_filter=True))
    assert int(off.sum()) >= int(on.sum())


def test_gate_params_for_moves_one_knob_only():
    base = EntryGateParams()
    assert gate_params_for("reversal_q", 0.42, base).reversal_q == pytest.approx(0.42)
    band = gate_params_for("ma_band", 0.95, base)
    assert band.ma20_band == pytest.approx(0.95) and band.ma60_band == pytest.approx(0.95)
    # ``min_pick_score`` is the provider floor, not an EntryGateParams field.
    assert gate_params_for("min_pick_score", 0.6, base) is base
    assert gate_params_for("min_pick_score", 0.6, base).reversal_q == pytest.approx(0.30)


def test_gate_params_for_rejects_unknown_knob():
    with pytest.raises(ValueError):
        gate_params_for("nope", 1.0)


def test_score_floor_only_moves_for_min_pick_score():
    assert score_floor_for("min_pick_score", 0.55, 0.80) == pytest.approx(0.55)
    assert score_floor_for("reversal_q", 0.55, 0.80) == pytest.approx(0.80)


# ---------------------------------------------------------------------------
# summarize_sweep — pure verdict kernel
# ---------------------------------------------------------------------------
def _pts(values, objectives, key: str = "sharpe"):
    return [
        {"value": v, "nTrades": 1, "metrics": {key: o}}
        for v, o in zip(values, objectives)
    ]


def test_summarize_robust_on_plateau():
    pts = _pts([0.1, 0.2, 0.3, 0.4, 0.5], [0.10, 0.50, 1.00, 0.95, 0.40])
    out = summarize_sweep(pts, objective="sharpe", tolerance=0.10)
    assert out["verdict"] == "robust"
    assert out["best"] == pytest.approx(0.3)
    assert out["robustRange"]["lo"] == pytest.approx(0.3)
    assert out["robustRange"]["hi"] == pytest.approx(0.4)
    assert out["robustRange"]["n"] == 2
    assert out["stability"] == pytest.approx(0.4)


def test_summarize_fragile_on_lone_spike():
    pts = _pts([0.1, 0.2, 0.3, 0.4, 0.5], [0.10, 0.20, 1.00, 0.30, 0.10])
    out = summarize_sweep(pts, objective="sharpe", tolerance=0.10)
    assert out["verdict"] == "fragile"
    assert out["best"] == pytest.approx(0.3)
    assert out["robustRange"]["n"] == 1


def test_summarize_flat_when_objective_barely_moves():
    pts = _pts([0.1, 0.2, 0.3, 0.4, 0.5], [0.50, 0.50, 0.50, 0.50, 0.50])
    out = summarize_sweep(pts, objective="sharpe")
    assert out["verdict"] == "flat"
    assert out["stability"] == pytest.approx(1.0)


def test_summarize_insufficient_below_three_points():
    out = summarize_sweep(_pts([0.1, 0.2], [0.1, 0.2]), objective="sharpe")
    assert out["verdict"] == "insufficient"
    assert out["best"] is None


def test_summarize_insufficient_when_metric_missing():
    pts = [{"value": v, "metrics": {}} for v in (0.1, 0.2, 0.3)]
    out = summarize_sweep(pts, objective="sharpe")
    assert out["verdict"] == "insufficient"
    assert out["nPoints"] == 0


def test_summarize_honours_min_direction():
    # max_drawdown: lower is better → min direction.
    pts = _pts([0.1, 0.2, 0.3, 0.4, 0.5], [0.30, 0.10, 0.11, 0.40, 0.50], key="max_drawdown")
    out = summarize_sweep(pts, objective="max_drawdown", tolerance=0.10)
    assert out["direction"] == "min"
    assert out["best"] == pytest.approx(0.2)
    assert out["verdict"] == "robust"


# ---------------------------------------------------------------------------
# sweep_entry_gate / build_sensitivity_report — engine integration (contract)
# ---------------------------------------------------------------------------
def _bars() -> pd.DataFrame:
    n = 260
    days = pd.bdate_range("2023-01-02", periods=n)
    rows = []
    for code, base in (("600519.SH", 10.0), ("000001.SZ", 8.0), ("601318.SH", 6.0)):
        for i, d in enumerate(days):
            wave = 1.0 + 0.0008 * i + 0.05 * ((i % 20) - 10) / 10.0
            rows.append(
                {
                    "code": code,
                    "date": d.date().isoformat(),
                    "close": base * wave,
                    "pct_chg": 0.0 if i == 0 else 0.0008,
                    "vol": 1_000_000.0 + 1000.0 * (i % 7),
                }
            )
    return pd.DataFrame(rows)


def _feats() -> pd.DataFrame:
    return prepare_book_frame(_bars(), universe="stock")


def test_sweep_entry_gate_preserves_grid_and_attaches_metrics():
    feats = _feats()
    grid = (0.2, 0.3, 0.4)
    out = sweep_entry_gate(
        feats,
        knob="reversal_q",
        values=grid,
        params=ReplayParams(initial_capital=100000.0, max_positions=3),
    )
    assert out["ok"] is True and out["knob"] == "reversal_q"
    assert [p["value"] for p in out["points"]] == list(grid)
    for pt in out["points"]:
        assert "sharpe" in pt["metrics"]
        assert pt["effective"]["gateParams"]["reversal_q"] == pytest.approx(pt["value"])


def test_sweep_entry_gate_min_pick_score_moves_the_floor():
    feats = _feats()
    out = sweep_entry_gate(feats, knob="min_pick_score", values=(0.0, 0.9))
    assert out["points"][0]["effective"]["minPickScore"] == pytest.approx(0.0)
    assert out["points"][1]["effective"]["minPickScore"] == pytest.approx(0.9)
    # The gate constant stays untouched when the score floor is the knob.
    assert out["points"][0]["effective"]["gateParams"]["reversal_q"] == pytest.approx(0.30)


def test_sweep_entry_gate_fails_closed():
    feats = _feats()
    with pytest.raises(ValueError):
        sweep_entry_gate(feats, knob="not_a_knob", values=(0.3,))
    with pytest.raises(ValueError):
        sweep_entry_gate(feats, knob="reversal_q", values=())


def test_build_sensitivity_report_contract():
    feats = _feats()
    knobs = ["reversal_q", "ma_band"]
    grids = {"reversal_q": (0.2, 0.3, 0.4), "ma_band": (0.90, 0.93, 0.96)}
    report = build_sensitivity_report(
        feats,
        knobs=knobs,
        grids=grids,
        objective="sharpe",
        params=ReplayParams(initial_capital=100000.0, max_positions=3),
    )
    assert report["ok"] is True
    assert set(report["knobs"]) == set(knobs)
    assert set(report["verdicts"]) == set(knobs)
    for verdict in report["verdicts"].values():
        assert verdict in {"robust", "fragile", "flat", "insufficient"}
    assert report["overall"] in {"robust", "fragile", "flat", "insufficient"}
    assert report["liveTradingEnabled"] is False


def test_build_sensitivity_report_defaults_cover_every_knob():
    # Every sweepable knob must ship a default grid, or the default report breaks.
    for knob in SWEEP_KNOBS:
        assert len(DEFAULT_GRIDS[knob]) >= 5
