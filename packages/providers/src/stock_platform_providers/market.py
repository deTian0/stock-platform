"""Market strategy tables — CN / US / HK must not share settle or limit assumptions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from .errors import SymbolError
from .symbol import normalize_symbol

MarketId = Literal["CN", "US", "HK"]
AssetTypeName = Literal["stock", "etf", "index"]


@dataclass(frozen=True)
class SettleRule:
    """How soon a bought lot may be sold for backtest / workbench modelling."""

    name: str
    buy_to_sell_delay_days: int
    note: str | None = None


@dataclass(frozen=True)
class LimitRule:
    """Price-limit behaviour. ``has_limits=False`` means no A-share style board."""

    has_limits: bool
    note: str | None = None


@dataclass(frozen=True)
class SessionSegment:
    start: str  # HH:MM local wall clock
    end: str


@dataclass(frozen=True)
class SymbolRef:
    symbol: str
    market_id: MarketId


@dataclass(frozen=True)
class MarketStrategy:
    """Read-only market rules. Workbench / backtest depend on this, not raw if-market."""

    market_id: MarketId
    timezone: str
    _sessions: tuple[SessionSegment, ...]
    _stock_settle: SettleRule
    _stock_limit: LimitRule | None

    def is_trading_day(self, d: date) -> bool:
        """Weekday-only stub (holiday calendars land with live vendors)."""
        return d.weekday() < 5

    def session_segments(self, d: date) -> list[SessionSegment]:
        if not self.is_trading_day(d):
            return []
        return list(self._sessions)

    def settle_rule(self, asset_type: AssetTypeName = "stock") -> SettleRule:
        if asset_type == "stock":
            return self._stock_settle
        # ETF / index: declare explicitly — do not silently inherit stock T+1.
        if self.market_id == "CN":
            return SettleRule(
                name="product-config",
                buy_to_sell_delay_days=0,
                note="ETF/index settle is product-specific; not stock T+1 by default",
            )
        return SettleRule(
            name="T+0",
            buy_to_sell_delay_days=0,
            note=f"{asset_type} same-session sell allowed under {self.market_id} stub",
        )

    def limit_rules(
        self, symbol: str, asset_type: AssetTypeName = "stock"
    ) -> LimitRule | None:
        _ = (symbol, asset_type)
        return self._stock_limit

    def validate_symbol(self, symbol: str) -> SymbolRef:
        code = normalize_symbol(symbol, market=self.market_id)
        return SymbolRef(symbol=code, market_id=self.market_id)


_CN = MarketStrategy(
    market_id="CN",
    timezone="Asia/Shanghai",
    _sessions=(
        SessionSegment("09:30", "11:30"),
        SessionSegment("13:00", "15:00"),
    ),
    _stock_settle=SettleRule(
        name="T+1",
        buy_to_sell_delay_days=1,
        note="A-share stock: buy today, sell next trading day",
    ),
    _stock_limit=LimitRule(
        has_limits=True,
        note="Board limits exist; percent by board/ST — use raw_* prices",
    ),
)

_US = MarketStrategy(
    market_id="US",
    timezone="America/New_York",
    _sessions=(SessionSegment("09:30", "16:00"),),
    _stock_settle=SettleRule(
        name="T+0-trading",
        buy_to_sell_delay_days=0,
        note="No A-share same-day sell ban; DTC settlement is separate",
    ),
    _stock_limit=LimitRule(has_limits=False, note="No A-share style daily limit board"),
)

_HK = MarketStrategy(
    market_id="HK",
    timezone="Asia/Hong_Kong",
    _sessions=(
        SessionSegment("09:30", "12:00"),
        SessionSegment("13:00", "16:00"),
    ),
    _stock_settle=SettleRule(
        name="T+0-trading",
        buy_to_sell_delay_days=0,
        note="No A-share same-day sell ban; CCASS settlement is separate",
    ),
    _stock_limit=LimitRule(has_limits=False, note="No A-share style daily limit board"),
)

_STRATEGIES: dict[str, MarketStrategy] = {
    "CN": _CN,
    "US": _US,
    "HK": _HK,
}


def get_market_strategy(market_id: str) -> MarketStrategy:
    key = str(market_id).strip().upper()
    try:
        return _STRATEGIES[key]
    except KeyError as exc:
        raise SymbolError(
            f"unknown market_id={market_id!r}; expected one of {sorted(_STRATEGIES)}"
        ) from exc


def list_market_ids() -> tuple[str, ...]:
    return tuple(_STRATEGIES.keys())
