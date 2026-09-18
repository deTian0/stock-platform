"""M-R3 empirical baseline compare tests (zero public net)."""

from __future__ import annotations

from stock_platform_research.empirical_compare import (
    compare_empirical_baseline,
    extract_engine_fold_returns,
)


def test_extract_engine_fold_returns_percent() -> None:
    payload = {
        "folds": {
            "2021": {"return_pct": 20.42},
            "2022": {"return_pct": 0.71},
        }
    }
    out = extract_engine_fold_returns(payload)
    assert out["2021"] == 0.2042
    assert out["2022"] == 0.0071


def test_compare_empirical_baseline_within_tolerance() -> None:
    engine = {
        "calibration": {
            "return_pct": 10.0,
            "max_drawdown_pct": 12.0,
            "sharpe": 0.5,
        },
        "folds": {"2021": {"return_pct": 8.0}},
    }
    platform = {
        "compounded_oos_return": 0.09,
        "avg_oos_objective": 0.04,
        "degradation": 0.01,
        "consistency": 0.5,
        "n_folds": 2,
    }
    report = compare_empirical_baseline(engine, platform, tolerance=0.02)
    assert report["ok"] is True
    assert report["dualSchedule"] is False
    assert report["liveTradingEnabled"] is False
    assert report["engine"]["calibration_return"] == 0.1
    assert report["platform"]["compounded_oos_return"] == 0.09
    assert report["delta_compounded_return"] == -0.01
    assert report["within_tolerance"] is True


def test_compare_empirical_baseline_wrapper_summary() -> None:
    engine = {"calibration": {"return_pct": 5.0}, "folds": {}}
    wrapper = {"summary": {"compounded_oos_return": 0.2, "n_folds": 1}}
    report = compare_empirical_baseline(engine, wrapper, tolerance=0.01)
    assert report["within_tolerance"] is False
    assert report["delta_compounded_return"] == 0.15
