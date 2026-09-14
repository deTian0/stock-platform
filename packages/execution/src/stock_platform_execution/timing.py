"""Multi-market paper timing helpers — injectable clocks; no broker I/O."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from stock_platform_providers import get_market_strategy, get_trading_calendar

DEFAULT_TRADE_WINDOW = "09:35-10:00"


def daily_bar_final_at(market: str = "CN") -> time:
    """Official daily bar completion clock = last session end + 5 minutes (local)."""
    strategy = get_market_strategy(market)
    hh, mm = (int(x) for x in strategy._sessions[-1].end.split(":"))
    total = hh * 60 + mm + 5
    return time(total // 60, total % 60)


# CN aliases kept for existing callers / tests.
DAILY_BAR_FINAL_AT = daily_bar_final_at("CN")
CHINA_TZ = ZoneInfo(get_market_strategy("CN").timezone)


def market_now(market: str = "CN", now: datetime | None = None) -> datetime:
    tz = ZoneInfo(get_market_strategy(market).timezone)
    value = now or datetime.now(tz)
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)


def china_now(now: datetime | None = None) -> datetime:
    """CN wall clock — alias of ``market_now("CN", ...)``."""
    return market_now("CN", now)


def completed_bar_cutoff(now: datetime | None = None, market: str = "CN") -> date:
    """Latest trade date whose official daily bar is considered completed."""
    local = market_now(market, now)
    cutoff = daily_bar_final_at(market)
    candidate = local.date() if local.time() >= cutoff else local.date() - timedelta(days=1)
    cal = get_trading_calendar(market)
    while not cal.is_trading_day(candidate):
        candidate -= timedelta(days=1)
    return candidate


def next_weekday(trade_date: date, market: str = "CN") -> date:
    """Next trading day after ``trade_date`` for ``market`` (name kept for callers)."""
    return get_trading_calendar(market).next_trading_day(trade_date)


def planned_execution_date(
    signal_date: str,
    observed_raw_dates: list[str] | None = None,
    market: str = "CN",
) -> str:
    get_market_strategy(market)  # validate early
    signal = date.fromisoformat(signal_date)
    later = sorted(
        raw for raw in (observed_raw_dates or []) if raw and date.fromisoformat(raw) > signal
    )
    if later:
        return later[0]
    return next_weekday(signal, market).isoformat()


def parse_trade_window(value: Any) -> tuple[time, time]:
    raw = str(value or DEFAULT_TRADE_WINDOW)
    match = re.search(r"(\d{1,2}):(\d{2})\s*[-—至]\s*(\d{1,2}):(\d{2})", raw)
    if not match:
        return time(9, 35), time(10, 0)
    return (
        time(int(match.group(1)), int(match.group(2))),
        time(int(match.group(3)), int(match.group(4))),
    )


def execution_window_status(
    planned_date: str,
    trade_window: Any = DEFAULT_TRADE_WINDOW,
    now: datetime | None = None,
    market: str = "CN",
) -> str:
    """Return before_date | before_window | open | after_window | stale | invalid."""
    local = market_now(market, now)
    try:
        planned = date.fromisoformat(str(planned_date))
    except ValueError:
        return "invalid"
    if local.date() < planned:
        return "before_date"
    if local.date() > planned:
        return "stale"
    start, end = parse_trade_window(trade_window)
    # Match by clock time including non-zero seconds (V2 scheduler reliability).
    t = local.time().replace(microsecond=0)
    if t < start:
        return "before_window"
    if t > end:
        return "after_window"
    return "open"


def signal_bar_is_completed(
    signal_date: str,
    generated_at: datetime | None = None,
    market: str = "CN",
) -> bool:
    try:
        signal = date.fromisoformat(str(signal_date))
    except ValueError:
        return False
    return signal <= completed_bar_cutoff(generated_at, market=market)


def assert_signal_before_execution(signal_trade_date: str, planned_date: str) -> None:
    """Signal day must be strictly before planned execution day."""
    sig = date.fromisoformat(signal_trade_date)
    plan = date.fromisoformat(planned_date)
    if sig >= plan:
        raise ValueError(
            f"signalTradeDate {signal_trade_date} must be before plannedExecutionDate {planned_date}"
        )
