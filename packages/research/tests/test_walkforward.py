"""Walk-forward fold / aggregate (M-R2) — zero network."""

from __future__ import annotations

from datetime import date

import pytest

from stock_platform_research.walkforward import (
    aggregate_oos,
    generate_folds,
    summarize_walk_forward,
)


def test_generate_folds_no_leakage_gap() -> None:
    folds = generate_folds(
        date(2020, 1, 1),
        date(2020, 6, 30),
        train_days=30,
        test_days=10,
        step_days=10,
    )
    assert folds
    for f in folds:
        assert (f.test_start - f.train_end).days == 1
        assert f.test_end >= f.test_start


def test_generate_folds_insufficient_raises() -> None:
    with pytest.raises(ValueError, match="不足以切出"):
        generate_folds(date(2020, 1, 1), date(2020, 1, 10), 30, 10, 5)


def test_aggregate_oos_empty_not_fake_edge() -> None:
    summary = aggregate_oos([])
    assert summary["n_folds"] == 0
    assert summary["degradation"] is None
    assert summary["compounded_oos_return"] == 0.0
    assert summary["consistency"] == 0.0


def test_aggregate_oos_compound_and_degradation() -> None:
    records = [
        {
            "index": 0,
            "test_end": "2020-03-01",
            "is_score": 0.2,
            "oos_objective": 0.1,
            "oos_stats": {"total_return": 0.1},
        },
        {
            "index": 1,
            "test_end": "2020-04-01",
            "is_score": 0.15,
            "oos_objective": -0.05,
            "oos_stats": {"total_return": -0.05},
        },
    ]
    summary = aggregate_oos(records)
    assert summary["n_folds"] == 2
    # compounded: 1.1 * 0.95 - 1 = 0.045
    assert summary["compounded_oos_return"] == pytest.approx(0.045, abs=1e-3)
    assert summary["avg_is_objective"] == pytest.approx(0.175, abs=1e-3)
    assert summary["avg_oos_objective"] == pytest.approx(0.025, abs=1e-3)
    assert summary["degradation"] == pytest.approx(0.15, abs=1e-3)
    assert summary["consistency"] == pytest.approx(0.5)


def test_summarize_drops_invalid_folds() -> None:
    out = summarize_walk_forward(
        start=date(2020, 1, 1),
        end=date(2020, 12, 31),
        train_days=60,
        test_days=20,
        step_days=20,
        fold_records=[
            {
                "index": 0,
                "test_end": "2020-05-01",
                "is_score": 0.1,
                "oos_objective": 0.05,
                "oos_stats": {"total_return": 0.05},
            },
            {"index": 1, "error": "failed", "is_score": None},
            {
                "index": 2,
                "test_end": "2020-07-01",
                "is_score": 0.0,
                "oos_objective": 0.0,
                "oos_stats": {"total_return": 0.0},
            },
        ],
    )
    assert out["ok"] is True
    assert out["n_planned_folds"] >= 1
    assert out["n_valid_folds"] == 2
    assert out["summary"]["n_folds"] == 2
    assert out["liveTradingEnabled"] is False
