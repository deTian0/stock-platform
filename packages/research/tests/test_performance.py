"""Deterministic fixtures for recommend performance metrics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stock_platform_research.performance import (
    brief_picks_to_pending,
    compute_performance,
    load_jsonl,
    performance_summary,
    settle_pending_entries,
    settled_records,
)


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "recommend_decisions.jsonl"


def test_settled_direction_accuracy_and_naming() -> None:
    entries = load_jsonl(FIXTURE)
    records = settled_records(entries)
    assert len(records) == 4
    stats = compute_performance(records)
    # Buy+up, Buy+up, Sell+down = 3 hits; Buy+down = miss → 3/4
    assert stats.directional_count == 4
    assert stats.direction_accuracy == pytest.approx(0.75)
    assert stats.up_rate == pytest.approx(0.5)  # 2 up / 4 (Sell-down is not "up")
    assert stats.avg_return is not None
    # Naming: up_rate is path of name, not judgment — Sell with negative return
    # still counts toward direction_accuracy but not up_rate.
    summary = performance_summary(entries=entries)
    assert "direction_accuracy" in summary["metricDefinitions"]
    assert summary["settledCount"] == 4
    assert summary["environment"] == "SIMULATE"
    assert summary["liveTradingEnabled"] is False


def test_hold_excluded_from_direction() -> None:
    entries = [
        {
            "date": "2026-09-01",
            "symbol": "A",
            "rating": "Hold",
            "raw": "+1.0%",
            "alpha": None,
            "holding": "5d",
            "pending": False,
        },
        {
            "date": "2026-09-01",
            "symbol": "B",
            "rating": "Buy",
            "raw": "+2.0%",
            "alpha": None,
            "holding": "5d",
            "pending": False,
        },
    ]
    stats = compute_performance(settled_records(entries))
    assert stats.count == 2
    assert stats.directional_count == 1
    assert stats.direction_accuracy == pytest.approx(1.0)


def test_brief_to_pending_and_settle_map() -> None:
    brief = {
        "asof": "2026-09-02",
        "picks": [
            {"rank": 1, "symbol": "600519", "composite_score": 0.9},
            {"rank": 2, "symbol": "000001", "composite_score": 0.8},
        ],
    }
    pending = brief_picks_to_pending(brief, holding="5d")
    assert all(r["pending"] for r in pending)
    settled = settle_pending_entries(
        pending,
        returns={
            ("2026-09-02", "600519"): 0.03,
            ("2026-09-02", "000001"): -0.01,
        },
    )
    assert settled[0]["pending"] is False
    assert settled[0]["raw"] == "+3.00%"
    assert settled[1]["raw"] == "-1.00%"


def test_pending_skipped_in_metrics() -> None:
    entries = [
        {
            "date": "2026-09-01",
            "symbol": "X",
            "rating": "Buy",
            "raw": None,
            "holding": "5d",
            "pending": True,
        }
    ]
    assert settled_records(entries) == []
    assert performance_summary(entries=entries)["settledCount"] == 0
