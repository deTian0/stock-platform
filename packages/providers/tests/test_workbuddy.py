"""Tests for the WorkBuddy MCP JSON-cache provider (offline, zero network)."""

from __future__ import annotations

from datetime import date

import pytest

from stock_platform_providers.workbuddy import (
    ENV_WORKBUDDY_CACHE_DIR,
    WorkbuddyProvider,
    resolve_workbuddy_cache_dir,
    write_daily_cache,
    write_realtime_cache,
)


def test_resolve_workbuddy_cache_dir_missing() -> None:
    assert resolve_workbuddy_cache_dir(env={}) is None


def test_provider_requires_cache_dir(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        WorkbuddyProvider(cache_dir=tmp_path / "nope")


def _make_cache(tmp_path):
    write_daily_cache(
        "600519",
        [
            {"date": "2026-01-02", "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 10000, "amount": 1_000_000},
            {"date": "2026-01-03", "open": 101.0, "high": 103.0, "low": 100.0, "close": 102.0, "volume": 12000, "amount": 1_200_000},
        ],
        tmp_path,
    )
    write_realtime_cache(
        "600519",
        {"price": 105.0, "prev_close": 102.0, "change_pct": 0.029, "asof_ts": 1_700_000_000_000},
        tmp_path,
    )
    return tmp_path


def test_get_daily_reads_cache(tmp_path) -> None:
    cache = _make_cache(tmp_path)
    provider = WorkbuddyProvider(cache_dir=cache)
    rows = provider.get_daily(["600519"])
    assert len(rows) == 2
    assert rows[0]["symbol"] == "600519"
    assert rows[0]["date"] == "2026-01-02"
    assert rows[0]["close"] == 101.0
    assert rows[0]["source"] == "workbuddy"


def test_get_daily_date_filter(tmp_path) -> None:
    provider = WorkbuddyProvider(cache_dir=_make_cache(tmp_path))
    rows = provider.get_daily(["600519"], start=date(2026, 1, 3))
    assert [r["date"] for r in rows] == ["2026-01-03"]


def test_get_realtime_reads_cache(tmp_path) -> None:
    provider = WorkbuddyProvider(cache_dir=_make_cache(tmp_path))
    rows = provider.get_realtime(["600519"])
    assert len(rows) == 1
    assert rows[0]["symbol"] == "600519"
    assert rows[0]["price"] == 105.0


def test_missing_symbol_returns_empty(tmp_path) -> None:
    provider = WorkbuddyProvider(cache_dir=_make_cache(tmp_path))
    assert provider.get_daily(["000001"]) == []
    assert provider.get_realtime(["000001"]) == []


def test_resolve_workbuddy_cache_dir_env(tmp_path) -> None:
    assert resolve_workbuddy_cache_dir(env={ENV_WORKBUDDY_CACHE_DIR: str(tmp_path)}) == tmp_path.resolve()
