"""TradingCalendar tests (static CN closed days; no network)."""

from __future__ import annotations

from datetime import date

import pytest

from stock_platform_providers import SymbolError, get_trading_calendar


def test_cn_weekend_not_trading() -> None:
    cal = get_trading_calendar("CN")
    assert not cal.is_trading_day(date(2026, 9, 5))  # Saturday
    assert not cal.is_trading_day(date(2026, 9, 6))  # Sunday
    assert cal.is_trading_day(date(2026, 9, 4))  # Friday


def test_cn_spring_festival_2025() -> None:
    cal = get_trading_calendar("CN")
    assert not cal.is_trading_day(date(2025, 1, 28))
    assert not cal.is_trading_day(date(2025, 2, 3))
    assert cal.is_trading_day(date(2025, 1, 27))
    assert cal.is_trading_day(date(2025, 2, 5))


def test_cn_national_day_2024_next_prev() -> None:
    cal = get_trading_calendar("CN")
    # Last session before National Day holiday: 2024-09-30
    assert cal.is_trading_day(date(2024, 9, 30))
    assert not cal.is_trading_day(date(2024, 10, 1))
    assert cal.next_trading_day(date(2024, 9, 30)) == date(2024, 10, 8)
    assert cal.prev_trading_day(date(2024, 10, 8)) == date(2024, 9, 30)


def test_us_weekday_stub() -> None:
    cal = get_trading_calendar("US")
    assert cal.is_trading_day(date(2026, 7, 3))  # Friday; US holiday table not in M10
    assert not cal.is_trading_day(date(2026, 7, 4))  # Saturday


def test_unknown_market() -> None:
    with pytest.raises(SymbolError):
        get_trading_calendar("JP")
