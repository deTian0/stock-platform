"""Replay transport + fixture-backed A-share provider (offline tests / demos)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from .base import AssetType
from .errors import SymbolError
from .normalize import (
    normalize_adj_factor_row,
    normalize_daily_row,
    normalize_depth5_row,
    normalize_financial_payload,
    normalize_fund_flow_row,
    normalize_lhb_payload,
    normalize_minute_row,
    normalize_realtime_row,
    normalize_unlock_payload,
    validate_adj_factor_kind,
)
from .symbol import normalize_symbol


class ReplayTransport:
    """Load recorded vendor payloads from a fixtures directory.

    Expected files::

        daily_{symbol}.json       # list[dict] or {"bars": [...]}
        realtime_{symbol}.json    # dict or {"quote": {...}}
        minute_{symbol}.json      # list[dict] or {"bars": [...]}
        fund_flow_{symbol}.json   # list[dict] or {"bars": [...]} / {"flows": [...]}
        lhb_{symbol}.json         # dict aggregate {records, seats, institution}
        unlock_{symbol}.json      # dict aggregate {history, upcoming}
        depth5_{symbol}.json      # dict or {"quote": {...}} five-level book
        financial_{symbol}.json   # dict aggregate {income, balance, cashflow}
        adj_factor_{symbol}.json  # list[dict] or {"bars": [...]} / {"factors": [...]}
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

    def load_minute(self, symbol: str) -> list[dict[str, Any]]:
        path = self.fixtures_dir / f"minute_{symbol}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            bars = data.get("bars") or data.get("data") or []
            return list(bars)
        if isinstance(data, list):
            return data
        raise ValueError(f"unexpected minute fixture shape in {path}")

    def load_fund_flow(self, symbol: str) -> list[dict[str, Any]]:
        path = self.fixtures_dir / f"fund_flow_{symbol}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            bars = data.get("bars") or data.get("flows") or data.get("data") or []
            return list(bars)
        if isinstance(data, list):
            return data
        raise ValueError(f"unexpected fund_flow fixture shape in {path}")

    def load_lhb(self, symbol: str) -> dict[str, Any]:
        path = self.fixtures_dir / f"lhb_{symbol}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        raise ValueError(f"unexpected lhb fixture shape in {path}")

    def load_unlock(self, symbol: str) -> dict[str, Any]:
        path = self.fixtures_dir / f"unlock_{symbol}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        raise ValueError(f"unexpected unlock fixture shape in {path}")

    def load_depth5(self, symbol: str) -> dict[str, Any]:
        path = self.fixtures_dir / f"depth5_{symbol}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and (
            "bid_prices" in data or "bid1" in data or "ask_prices" in data
        ):
            return data
        if isinstance(data, dict):
            quote = data.get("quote") or data.get("data")
            if isinstance(quote, dict):
                return quote
        raise ValueError(f"unexpected depth5 fixture shape in {path}")

    def load_financial(self, symbol: str) -> dict[str, Any]:
        path = self.fixtures_dir / f"financial_{symbol}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        raise ValueError(f"unexpected financial fixture shape in {path}")

    def load_adj_factor(self, symbol: str) -> list[dict[str, Any]]:
        path = self.fixtures_dir / f"adj_factor_{symbol}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            bars = data.get("bars") or data.get("factors") or data.get("data") or []
            return list(bars)
        if isinstance(data, list):
            return data
        raise ValueError(f"unexpected adj_factor fixture shape in {path}")


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

    def get_minute(
        self,
        symbols: list[str],
        *,
        freq: str = "1m",
        start: date | None = None,
        end: date | None = None,
        asset_type: AssetType = "stock",
        limit: int = 0,
    ) -> list[dict[str, Any]]:
        """Return minute bars for ``freq`` (1m/5m/15m/30m/60m). Missing fixture → []."""
        want = str(freq).strip().lower()
        if want.isdigit():
            want = f"{want}m"
        rows: list[dict[str, Any]] = []
        for raw_sym in symbols:
            symbol = normalize_symbol(raw_sym)
            try:
                bars = self._transport.load_minute(symbol)
            except FileNotFoundError:
                continue
            sym_rows: list[dict[str, Any]] = []
            for bar in bars:
                row = normalize_minute_row(
                    bar,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=symbol,
                    default_freq=want,
                )
                if row["freq"] != want:
                    continue
                bar_day = date.fromisoformat(row["datetime"][:10])
                if start and bar_day < start:
                    continue
                if end and bar_day > end:
                    continue
                sym_rows.append(row)
            if limit > 0:
                sym_rows = sym_rows[-limit:]
            rows.extend(sym_rows)
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

    def get_lhb(
        self,
        symbols: list[str],
        *,
        asof_date: date,
        look_back_days: int = 30,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for raw_sym in symbols:
            symbol = normalize_symbol(raw_sym)
            try:
                raw = self._transport.load_lhb(symbol)
            except FileNotFoundError as exc:
                raise SymbolError(f"no lhb fixture for {symbol}") from exc
            items.append(
                normalize_lhb_payload(
                    raw,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=symbol,
                    asof_date=asof_date,
                    look_back_days=look_back_days,
                )
            )
        return items

    def get_unlock(
        self,
        symbols: list[str],
        *,
        asof_date: date,
        forward_days: int = 90,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for raw_sym in symbols:
            symbol = normalize_symbol(raw_sym)
            try:
                raw = self._transport.load_unlock(symbol)
            except FileNotFoundError as exc:
                raise SymbolError(f"no unlock fixture for {symbol}") from exc
            items.append(
                normalize_unlock_payload(
                    raw,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=symbol,
                    asof_date=asof_date,
                    forward_days=forward_days,
                )
            )
        return items

    def get_depth5(
        self,
        symbols: list[str],
        *,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        """Five-level order book. Missing fixture → skip (empty contribution)."""
        rows: list[dict[str, Any]] = []
        for raw_sym in symbols:
            symbol = normalize_symbol(raw_sym)
            try:
                quote = self._transport.load_depth5(symbol)
            except FileNotFoundError:
                continue
            rows.append(
                normalize_depth5_row(
                    quote,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=symbol,
                )
            )
        return rows

    def get_financial(
        self,
        symbols: list[str],
        *,
        periods: int = 8,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        """Three-statement financial aggregate. Missing fixture → skip."""
        items: list[dict[str, Any]] = []
        for raw_sym in symbols:
            symbol = normalize_symbol(raw_sym)
            try:
                raw = self._transport.load_financial(symbol)
            except FileNotFoundError:
                continue
            items.append(
                normalize_financial_payload(
                    raw,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=symbol,
                    periods=periods if "periods" not in raw else None,
                )
            )
        return items

    def get_adj_factor(
        self,
        symbols: list[str],
        *,
        kind: str = "qfq",
        start: date | None = None,
        end: date | None = None,
        asset_type: AssetType = "stock",
        limit: int = 0,
    ) -> list[dict[str, Any]]:
        """Adjustment factor series. Missing fixture → skip (empty contribution)."""
        validate_adj_factor_kind(kind)
        rows: list[dict[str, Any]] = []
        for raw_sym in symbols:
            symbol = normalize_symbol(raw_sym)
            try:
                bars = self._transport.load_adj_factor(symbol)
            except FileNotFoundError:
                continue
            sym_rows: list[dict[str, Any]] = []
            for bar in bars:
                row = normalize_adj_factor_row(
                    bar,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=symbol,
                )
                d = date.fromisoformat(row["trade_date"])
                if start and d < start:
                    continue
                if end and d > end:
                    continue
                sym_rows.append(row)
            # Contract / Sina order: newest first (trade_date desc)
            sym_rows.sort(key=lambda r: r["trade_date"], reverse=True)
            if limit > 0:
                sym_rows = sym_rows[:limit]
            rows.extend(sym_rows)
        return rows
