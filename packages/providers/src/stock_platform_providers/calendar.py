"""Trading calendars — CN static closed weekdays; US/HK weekday stub."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from importlib import resources
from typing import Literal

from .errors import SymbolError

MarketId = Literal["CN", "US", "HK"]


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


def _load_cn_closed_weekdays() -> frozenset[date]:
    text = (
        resources.files("stock_platform_providers")
        .joinpath("data/cn_closed_days.txt")
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
    if key == "CN":
        return TradingCalendar(market_id="CN", closed_weekdays=_load_cn_closed_weekdays())
    if key in {"US", "HK"}:
        # Weekday-only stub (no exchange holiday table in M10).
        return TradingCalendar(market_id=key, closed_weekdays=frozenset())  # type: ignore[arg-type]
    raise SymbolError(f"unknown market_id={market_id!r}; expected CN, US, or HK")
