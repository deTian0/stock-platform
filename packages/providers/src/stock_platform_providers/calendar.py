"""Trading calendars — CN / US / HK static closed weekdays (weekends always closed)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from importlib import resources
from typing import Literal

from .errors import SymbolError

MarketId = Literal["CN", "US", "HK"]

_FILE_BY_MARKET: dict[str, str] = {
    "CN": "cn_closed_days.txt",
    "US": "us_closed_days.txt",
    "HK": "hk_closed_days.txt",
}


@dataclass(frozen=True)
class TradingCalendar:
    """Market trading-day rules. ``next`` / ``prev`` never return the input day."""

    market_id: MarketId
    closed_weekdays: frozenset[date]

    def is_trading_day(self, d: date) -> bool:
        if d.weekday() >= 5:
            return False
        return d not in self.closed_weekdays

    def next_trading_day(self, d: date) -> date:
        candidate = d + timedelta(days=1)
        while not self.is_trading_day(candidate):
            candidate += timedelta(days=1)
        return candidate

    def prev_trading_day(self, d: date) -> date:
        candidate = d - timedelta(days=1)
        while not self.is_trading_day(candidate):
            candidate -= timedelta(days=1)
        return candidate


def _load_closed_weekdays(filename: str) -> frozenset[date]:
    text = (
        resources.files("stock_platform_providers")
        .joinpath(f"data/{filename}")
        .read_text(encoding="utf-8")
    )
    days: set[date] = set()
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        days.add(date.fromisoformat(raw))
    return frozenset(days)


@lru_cache(maxsize=8)
def get_trading_calendar(market_id: str) -> TradingCalendar:
    key = str(market_id).strip().upper()
    filename = _FILE_BY_MARKET.get(key)
    if filename is None:
        raise SymbolError(f"unknown market_id={market_id!r}; expected CN, US, or HK")
    return TradingCalendar(market_id=key, closed_weekdays=_load_closed_weekdays(filename))  # type: ignore[arg-type]
