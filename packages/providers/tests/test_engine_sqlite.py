"""engine_sqlite adapter — read-only daily from a-stock-engine market.db shape."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from stock_platform_providers.engine_sqlite import (
    ENV_ENGINE_MARKET_DB,
    EngineSqliteProvider,
    resolve_engine_market_db,
)


def _make_market_db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE daily_price (
            code TEXT NOT NULL,
            date TEXT NOT NULL,
            close REAL,
            pct_chg REAL,
            vol REAL,
            amount REAL,
            PRIMARY KEY (code, date)
        )
        """
    )
    conn.executemany(
        "INSERT INTO daily_price VALUES (?,?,?,?,?,?)",
        [
            ("600519.SH", "2026-09-01", 100.0, 0.0, 1000.0, 1e6),
            ("600519.SH", "2026-09-02", 103.0, 3.0, 1100.0, 1.1e6),
            ("000001.SZ", "2026-09-01", 10.0, 0.0, 2000.0, 2e5),
        ],
    )
    conn.commit()
    conn.close()
    return path


def test_resolve_engine_market_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_ENGINE_MARKET_DB, raising=False)
    assert resolve_engine_market_db() is None
    db = _make_market_db(tmp_path / "market.db")
    monkeypatch.setenv(ENV_ENGINE_MARKET_DB, str(db))
    assert resolve_engine_market_db() == db


def test_engine_sqlite_get_daily(tmp_path: Path) -> None:
    db = _make_market_db(tmp_path / "market.db")
    provider = EngineSqliteProvider(db)
    rows = provider.get_daily(
        ["600519"],
        start=date(2026, 9, 1),
        end=date(2026, 9, 2),
    )
    assert len(rows) == 2
    assert rows[0]["symbol"] == "600519"
    assert rows[0]["source"] == "engine_sqlite"
    assert rows[0]["close"] == pytest.approx(100.0)
    assert rows[1]["close"] == pytest.approx(103.0)


def test_engine_sqlite_realtime_not_implemented(tmp_path: Path) -> None:
    db = _make_market_db(tmp_path / "market.db")
    provider = EngineSqliteProvider(db)
    with pytest.raises(NotImplementedError):
        provider.get_realtime(["600519"])
