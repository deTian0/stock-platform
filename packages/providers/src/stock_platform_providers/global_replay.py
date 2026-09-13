"""Global (US/HK) replay provider — fixtures only, no live HTTP."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Literal

from .base import AssetType
from .errors import SymbolError
from .normalize import normalize_daily_row, normalize_realtime_row
from .symbol import normalize_symbol

MarketId = Literal["US", "HK"]


class GlobalReplayTransport:
    """Load US/HK recorded fixtures.

    Expected files (normalized symbol)::

        daily_{SYMBOL}.json
        realtime_{SYMBOL}.json
    """

    def __init__(self, fixtures_dir: str | Path) -> None:
        self.fixtures_dir = Path(fixtures_dir)
        if not self.fixtures_dir.is_dir():
            raise FileNotFoundError(f"fixtures dir not found: {self.fixtures_dir}")

    def load_daily(self, symbol: str) -> list[dict[str, Any]]:
        path = self.fixtures_dir / f"daily_{symbol}.json"
        if not path.is_file():
            raise FileNotFoundError(str(path))
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return list(data.get("bars") or data.get("data") or [])
        if isinstance(data, list):
            return data
        raise ValueError(f"unexpected daily fixture shape in {path}")

    def load_realtime(self, symbol: str) -> dict[str, Any]:
        path = self.fixtures_dir / f"realtime_{symbol}.json"
        if not path.is_file():
            raise FileNotFoundError(str(path))
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and ("price" in data or "close" in data or "last" in data):
            return data
        if isinstance(data, dict):
            quote = data.get("quote") or data.get("data")
            if isinstance(quote, dict):
                return quote
        raise ValueError(f"unexpected realtime fixture shape in {path}")


class GlobalReplayProvider:
    """MarketDataProvider for US/HK offline fixtures (never uses CN normalize)."""

    name = "global_replay"

    def __init__(self, transport: GlobalReplayTransport, *, market: MarketId) -> None:
        if market not in ("US", "HK"):
            raise SymbolError(f"GlobalReplayProvider market must be US or HK, got {market!r}")
        self._transport = transport
        self.market = market

    def get_daily(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw_sym in symbols:
            symbol = normalize_symbol(raw_sym, market=self.market)
            for bar in self._transport.load_daily(symbol):
                row = normalize_daily_row(
                    bar,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=symbol,
                    market=self.market,
                )
                d = date.fromisoformat(row["date"])
                if start and d < start:
                    continue
                if end and d > end:
                    continue
                rows.append(row)
        return rows

    def get_realtime(
        self,
        symbols: list[str],
        *,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw_sym in symbols:
            symbol = normalize_symbol(raw_sym, market=self.market)
            try:
                quote = self._transport.load_realtime(symbol)
            except FileNotFoundError as exc:
                raise SymbolError(f"no realtime fixture for {symbol}") from exc
            rows.append(
                normalize_realtime_row(
                    quote,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=symbol,
                    market=self.market,
                )
            )
        return rows
