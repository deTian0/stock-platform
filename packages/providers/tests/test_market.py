"""Market strategy table tests — US/HK must not inherit CN settle/limit."""

from __future__ import annotations

from datetime import date

import pytest

from stock_platform_providers import (
    SymbolError,
    get_market_strategy,
    list_market_ids,
)


def test_market_ids() -> None:
    assert set(list_market_ids()) == {"CN", "US", "HK"}


def test_cn_has_t1_and_limits() -> None:
    cn = get_market_strategy("CN")
    assert cn.timezone == "Asia/Shanghai"
    settle = cn.settle_rule("stock")
    assert settle.buy_to_sell_delay_days == 1
    assert settle.name == "T+1"
    limits = cn.limit_rules("600519")
    assert limits is not None and limits.has_limits is True


def test_us_hk_no_cn_assumptions() -> None:
    for mid in ("US", "HK"):
        s = get_market_strategy(mid)
        assert s.settle_rule("stock").buy_to_sell_delay_days == 0
        limits = s.limit_rules("dummy")
        assert limits is not None and limits.has_limits is False


def test_us_timezone_and_session() -> None:
    us = get_market_strategy("US")
    assert us.timezone == "America/New_York"
    segs = us.session_segments(date(2026, 9, 4))  # Friday
    assert segs and segs[0].start == "09:30"
    assert us.session_segments(date(2026, 9, 5)) == []  # Saturday


def test_hk_timezone() -> None:
    assert get_market_strategy("HK").timezone == "Asia/Hong_Kong"


def test_validate_symbol_routes_by_market() -> None:
    assert get_market_strategy("CN").validate_symbol("SH600519").symbol == "600519"
    assert get_market_strategy("US").validate_symbol("aapl").symbol == "AAPL"
    assert get_market_strategy("HK").validate_symbol("0700.HK").symbol == "00700"


def test_cn_strategy_rejects_hk() -> None:
    with pytest.raises(SymbolError):
        get_market_strategy("CN").validate_symbol("00700")


def test_cn_is_trading_day_uses_holiday_calendar() -> None:
    cn = get_market_strategy("CN")
    assert not cn.is_trading_day(date(2024, 10, 1))
    assert cn.is_trading_day(date(2024, 10, 8))


def test_us_is_trading_day_uses_holiday_calendar() -> None:
    us = get_market_strategy("US")
    assert not us.is_trading_day(date(2025, 7, 4))
    assert not us.is_trading_day(date(2024, 12, 25))
    assert us.is_trading_day(date(2025, 7, 3))


def test_hk_is_trading_day_uses_holiday_calendar() -> None:
    hk = get_market_strategy("HK")
    assert not hk.is_trading_day(date(2025, 1, 29))
    assert not hk.is_trading_day(date(2025, 1, 30))
    assert hk.is_trading_day(date(2025, 1, 28))


def test_unknown_market() -> None:
    with pytest.raises(SymbolError, match="unknown market"):
        get_market_strategy("JP")
