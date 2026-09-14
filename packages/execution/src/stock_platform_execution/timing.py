"""CN paper timing helpers — injectable clocks; no broker I/O."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from stock_platform_providers import get_trading_calendar

CHINA_TZ = timezone(timedelta(hours=8))
DAILY_BAR_FINAL_AT = time(15, 5)
DEFAULT_TRADE_WINDOW = "09:35-10:00"


def china_now(now: datetime | None = None) -> datetime:
    value = now or datetime.now(CHINA_TZ)
    if value.tzinfo is None:
        return value.replace(tzinfo=CHINA_TZ)
    return value.astimezone(CHINA_TZ)


def completed_bar_cutoff(now: datetime | None = None) -> date:
    """Latest trade date whose official daily bar is considered completed."""
    local = china_now(now)
    candidate = local.date() if local.time() >= DAILY_BAR_FINAL_AT else local.date() - timedelta(days=1)
    cal = get_trading_calendar("CN")
    while not cal.is_trading_day(candidate):
        candidate -= timedelta(days=1)
    return candidate


def next_weekday(trade_date: date) -> date:
    """Next CN trading day after ``trade_date`` (alias kept for callers)."""
    return get_trading_calendar("CN").next_trading_day(trade_date)


def planned_execution_date(signal_date: str, observed_raw_dates: list[str] | None = None) -> str:
    signal = date.fromisoformat(signal_date)
    later = sorted(
        raw for raw in (observed_raw_dates or []) if raw and date.fromisoformat(raw) > signal
    )
    if later:
        return later[0]
    return next_weekday(signal).isoformat()


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
) -> str:
    """Return before_date | before_window | open | after_window | stale | invalid."""
    local = china_now(now)
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


def signal_bar_is_completed(signal_date: str, generated_at: datetime | None = None) -> bool:
    try:
        signal = date.fromisoformat(str(signal_date))
    except ValueError:
        return False
    return signal <= completed_bar_cutoff(generated_at)


def assert_signal_before_execution(signal_trade_date: str, planned_date: str) -> None:
    """Signal day must be strictly before planned execution day."""
    sig = date.fromisoformat(signal_trade_date)
    plan = date.fromisoformat(planned_date)
    if sig >= plan:
        raise ValueError(
            f"signalTradeDate {signal_trade_date} must be before plannedExecutionDate {planned_date}"
        )
