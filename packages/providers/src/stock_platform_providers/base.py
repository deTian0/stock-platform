"""Provider protocol and shared types."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Protocol

AssetType = Literal["stock", "etf", "index"]


class MarketDataProvider(Protocol):
    """Minimal CN provider surface for M1.2 (daily + realtime).

    Optional extensions when declared on the capability matrix:

    - M18+ ``get_minute`` → ``minute`` (CN intraday bars; Beijing naive datetime)
    - M19+ ``get_depth5`` → ``depth5`` (CN five-level order book; volumes in 手)
    - M20+ ``get_financial`` → ``financial`` (CN income/balance/cashflow; amounts in 元)
    - M21+ ``get_adj_factor`` → ``adj_factor`` (CN ex-rights factors; column ``ex_factor``)
    - M15+ ``get_fund_flow`` → ``fund_flow``
    - M16+ ``get_lhb`` → ``lhb`` (dragon-tiger board)
    - M17+ ``get_unlock`` → ``unlock`` (lockup expiry / 限售解禁)
    """

    name: str

    def get_daily(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        """Return rows matching DAILY_COLUMNS (extra keys allowed then stripped)."""

    def get_realtime(
        self,
        symbols: list[str],
        *,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        """Return rows matching REALTIME_COLUMNS."""
