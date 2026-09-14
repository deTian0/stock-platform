"""Provider protocol and shared types."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Protocol

AssetType = Literal["stock", "etf", "index"]


class MarketDataProvider(Protocol):
    """Minimal CN provider surface for M1.2 (daily + realtime).

    Optional M15+: ``get_fund_flow`` when the provider declares the
    ``fund_flow`` capability.
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
