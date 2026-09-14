"""Timing and freshness tests."""

from __future__ import annotations

from datetime import datetime

import pytest

from stock_platform_execution import (
    completed_bar_cutoff,
    execution_window_status,
    planned_execution_date,
    signal_bar_is_completed,
)
from stock_platform_execution.timing import CHINA_TZ, assert_signal_before_execution


def test_completed_bar_cutoff_before_1505() -> None:
    now = datetime(2026, 9, 4, 15, 0, tzinfo=CHINA_TZ)
    assert completed_bar_cutoff(now).isoformat() == "2026-09-03"


def test_completed_bar_cutoff_after_1505() -> None:
    now = datetime(2026, 9, 4, 15, 5, tzinfo=CHINA_TZ)
    assert completed_bar_cutoff(now).isoformat() == "2026-09-04"


def test_planned_execution_skips_weekend() -> None:
    # Friday signal → Monday execution
    assert planned_execution_date("2026-09-04") == "2026-09-07"


def test_window_open_with_nonzero_seconds() -> None:
    now = datetime(2026, 9, 7, 9, 40, 37, tzinfo=CHINA_TZ)
    assert execution_window_status("2026-09-07", "09:35-10:00", now) == "open"


def test_after_window_and_stale() -> None:
    assert (
        execution_window_status(
            "2026-09-07", "09:35-10:00", datetime(2026, 9, 7, 10, 1, tzinfo=CHINA_TZ)
        )
        == "after_window"
    )
    assert (
        execution_window_status(
            "2026-09-07", "09:35-10:00", datetime(2026, 9, 8, 9, 40, tzinfo=CHINA_TZ)
        )
        == "stale"
    )


def test_signal_must_precede_execution() -> None:
    with pytest.raises(ValueError):
        assert_signal_before_execution("2026-09-07", "2026-09-07")


def test_signal_bar_completed() -> None:
    now = datetime(2026, 9, 4, 16, 0, tzinfo=CHINA_TZ)
    assert signal_bar_is_completed("2026-09-04", now)
    assert not signal_bar_is_completed("2026-09-05", now)
