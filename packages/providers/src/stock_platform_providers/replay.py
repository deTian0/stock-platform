"""Replay transport + fixture-backed A-share provider (offline tests / demos)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from .base import AssetType
from .errors import SymbolError
from .normalize import normalize_daily_row, normalize_fund_flow_row, normalize_realtime_row
from .symbol import normalize_symbol


class ReplayTransport:
    """Load recorded vendor payloads from a fixtures directory.

    Expected files::

        daily_{symbol}.json       # list[dict] or {"bars": [...]}
        realtime_{symbol}.json    # dict or {"quote": {...}}
        fund_flow_{symbol}.json   # list[dict] or {"bars": [...]} / {"flows": [...]}
    """

    def __init__(self, fixtures_dir: str | Path) -> None:
        self.fixtures_dir = Path(fixtures_dir)
        if not self.fixtures_dir.is_dir():
            raise FileNotFoundError(f"fixtures dir not found: {self.fixtures_dir}")

    def load_daily(self, symbol: str) -> list[dict[str, Any]]:
        path = self.fixtures_dir / f"daily_{symbol}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            bars = data.get("bars") or data.get("data") or []
            return list(bars)
        if isinstance(data, list):
            return data
        raise ValueError(f"unexpected daily fixture shape in {path}")

    def load_realtime(self, symbol: str) -> dict[str, Any]:
        path = self.fixtures_dir / f"realtime_{symbol}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and ("price" in data or "close" in data or "last" in data):
            return data
        if isinstance(data, dict):
            quote = data.get("quote") or data.get("data")
            if isinstance(quote, dict):
                return quote
        raise ValueError(f"unexpected realtime fixture shape in {path}")

    def load_fund_flow(self, symbol: str) -> list[dict[str, Any]]:
        path = self.fixtures_dir / f"fund_flow_{symbol}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            bars = data.get("bars") or data.get("flows") or data.get("data") or []
            return list(bars)
        if isinstance(data, list):
            return data
        raise ValueError(f"unexpected fund_flow fixture shape in {path}")


class ReplayProvider:
    """MarketDataProvider backed only by recorded fixtures (no network)."""

    name = "replay"

    def __init__(self, transport: ReplayTransport) -> None:
        self._transport = transport

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
            symbol = normalize_symbol(raw_sym)
            for bar in self._transport.load_daily(symbol):
                row = normalize_daily_row(
                    bar,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=symbol,
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
            symbol = normalize_symbol(raw_sym)
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
                )
            )
        return rows

    def get_fund_flow(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        asset_type: AssetType = "stock",
        limit: int = 120,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw_sym in symbols:
            symbol = normalize_symbol(raw_sym)
            try:
                bars = self._transport.load_fund_flow(symbol)
            except FileNotFoundError as exc:
                raise SymbolError(f"no fund_flow fixture for {symbol}") from exc
            sym_rows: list[dict[str, Any]] = []
            for bar in bars:
                row = normalize_fund_flow_row(
                    bar,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=symbol,
                )
                d = date.fromisoformat(row["date"])
                if start and d < start:
                    continue
                if end and d > end:
                    continue
                sym_rows.append(row)
            if limit > 0:
                sym_rows = sym_rows[-limit:]
            rows.extend(sym_rows)
        return rows
