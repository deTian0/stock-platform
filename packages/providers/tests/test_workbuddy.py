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


# --- bridge round-trip (v4.1.8) ---------------------------------------------
# The cache must be consumable by the provider straight after the bridge writes
# it; this locks the writer/reader schema against drifting apart.


def test_bridge_written_cache_is_readable_by_provider(tmp_path) -> None:
    """`write_daily_cache` output feeds `get_daily` with no reshaping."""
    write_daily_cache(
        "sh600519",
        [
            {
                "date": "2026-10-09",
                "open": 1255.42,
                "high": 1282.0,
                "low": 1255.42,
                "close": 1263.0,
                "volume": 35111,
                "amount": 4_453_220_000,
                "change_pct": 0.5741405808,
                "pct_unit": "percent",
            }
        ],
        tmp_path,
    )
    provider = WorkbuddyProvider(cache_dir=tmp_path)
    rows = provider.get_daily(["600519"])
    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "600519"
    assert row["date"] == "2026-10-09"
    assert row["close"] == 1263.0
    assert row["source"] == "workbuddy"
    # percent -> decimal conversion is applied by the normalizer
    assert row["change_pct"] == pytest.approx(0.005741405808)


def test_bridge_written_realtime_cache_is_readable(tmp_path) -> None:
    write_realtime_cache(
        "sh600519",
        {
            "name": "贵州茅台",
            "price": 1263.0,
            "prev_close": 1255.79,
            "change_pct": 0.57,
            "pct_unit": "percent",
            "time": "2026-10-09",
        },
        tmp_path,
    )
    rows = WorkbuddyProvider(cache_dir=tmp_path).get_realtime(["600519"])
    assert len(rows) == 1
    assert rows[0]["price"] == 1263.0
    assert rows[0]["change_pct"] == pytest.approx(0.0057)


def test_bridge_uses_bare_code_file_names(tmp_path) -> None:
    """`sh600519` must land as `daily_600519.json`, not `daily_sh600519.json`."""
    path = write_daily_cache("sh600519", [{"date": "2026-10-09", "close": 1.0}], tmp_path)
    assert path.name == "daily_600519.json"
