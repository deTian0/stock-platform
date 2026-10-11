"""``MarketDbBulkProvider`` tests — real market.db if present, else skip.

The provider is the P0-1 offline path: one SQL pass for the whole universe.
These tests use the real engine warehouse read-only when it is available
(``STOCK_PLATFORM_ENGINE_MARKET_DB`` / the standard path) and skip otherwise, so
CI without the 3.14 GB file stays green.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from stock_platform_providers import MarketDbBulkProvider
from stock_platform_providers.market_db_bulk import (
    SUPPORTED_DATASETS,
    UNSUPPORTED_DATASETS,
    _bare_codes,
    _engine_code_map,
)

ENGINE_ENV = "STOCK_PLATFORM_ENGINE_MARKET_DB"
DEFAULT_DB = Path("D:/workspace/stock_trading/a-stock-engine/data_cache/market.db")


def _resolve_db() -> Path | None:
    raw = (os.environ.get(ENGINE_ENV) or "").strip()
    candidate = Path(raw) if raw else DEFAULT_DB
    return candidate if candidate.is_file() else None


DB = _resolve_db()
needs_db = pytest.mark.skipif(DB is None, reason="engine market.db not available")


# --- pure helpers (no DB) --------------------------------------------------


def test_bare_codes_dedupes_and_normalises() -> None:
    # An unusable code raises in the shared normaliser rather than being dropped.
    from stock_platform_providers.errors import SymbolError

    out = _bare_codes(["600519", "600519.SH", "sh600519", "000001"])
    assert out == ["600519", "000001"]
    with pytest.raises(SymbolError):
        _bare_codes(["not-a-code"])


def test_engine_code_map_covers_all_spellings() -> None:
    mapping = _engine_code_map(["600519"])
    assert mapping["600519"] == "600519"
    assert mapping["600519.SH"] == "600519"
    assert mapping["sh600519"] == "600519"
    assert mapping["600519.SZ"] == "600519"  # suffix variants fold together


def test_capability_sets_are_disjoint_and_complete() -> None:
    assert set(SUPPORTED_DATASETS).isdisjoint(UNSUPPORTED_DATASETS)
    assert set(SUPPORTED_DATASETS) | set(UNSUPPORTED_DATASETS) == {
        "daily",
        "adj_factor",
        "fund_flow",
        "full_minute",
    }


# --- DB-backed -------------------------------------------------------------


@needs_db
def test_provider_reads_readonly_and_reports_coverage() -> None:
    provider = MarketDbBulkProvider(DB)
    assert provider.supports("daily") is True
    assert provider.supports("adj_factor") is False
    snap = provider.coverage_snapshot()
    assert "status" in snap


@needs_db
def test_bulk_daily_serves_every_symbol_in_one_call() -> None:
    provider = MarketDbBulkProvider(DB)
    latest = provider.latest_trade_date()
    assert latest is not None
    asof = date.fromisoformat(latest)
    symbols = provider.list_symbols(asof=asof, lookback_days=120, min_bars=60, limit=50)
    assert symbols, "expected a non-empty universe from the real warehouse"

    out = provider.bulk_daily(symbols, start=date(asof.year - 1, asof.month, 1), end=asof)

    assert set(out) == set(symbols)
    non_empty = [s for s, rows in out.items() if rows]
    assert len(non_empty) == len(symbols)
    # Rows carry the platform field shape the refresh envelope expects.
    sample = out[non_empty[0]][0]
    assert {"symbol", "date", "close"} <= set(sample)


@needs_db
def test_bulk_daily_missing_symbol_maps_to_empty_list() -> None:
    provider = MarketDbBulkProvider(DB)
    latest = provider.latest_trade_date()
    asof = date.fromisoformat(latest)
    out = provider.bulk_daily(["600519", "999999"], start=date(2000, 1, 1), end=asof)
    assert "999999" in out
    assert out["999999"] == []


@needs_db
def test_bulk_daily_respects_window() -> None:
    provider = MarketDbBulkProvider(DB)
    latest = provider.latest_trade_date()
    asof = date.fromisoformat(latest)
    # A one-day window can only return the asof bar.
    out = provider.bulk_daily(["600519"], start=asof, end=asof)
    rows = out["600519"]
    assert len(rows) <= 1
    if rows:
        assert rows[0]["date"] == asof.isoformat()


@needs_db
def test_bulk_daily_rejects_writes() -> None:
    """Sanity: the provider opens the warehouse read-only (ADR 0050)."""
    provider = MarketDbBulkProvider(DB)
    con = provider._engine._connect()  # noqa: SLF001 — assert the mode explicitly
    with pytest.raises(sqlite3.OperationalError):
        con.execute("CREATE TABLE _should_not_exist (x INTEGER)")
    con.close()
