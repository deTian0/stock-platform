"""engine_sqlite PIT helpers (ADR 0050) — temp DB only, no network."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from stock_platform_providers.engine_sqlite import (
    MSG_ASOF_REQUIRED,
    MSG_DB_MISSING,
    MSG_TABLE_MISSING,
    EngineSqliteProvider,
)


def _make_pit_db(path: Path) -> Path:
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
    conn.execute(
        """
        CREATE TABLE fundamentals_pit (
            code TEXT NOT NULL,
            end_date TEXT NOT NULL,
            ann_date TEXT,
            roe REAL,
            roa REAL,
            gross_margin REAL,
            debt_ratio REAL,
            revenue_growth REAL,
            profit_growth REAL,
            eps REAL,
            eps_ttm REAL,
            bps REAL,
            report_type TEXT,
            PRIMARY KEY (code, end_date)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE daily_basic_pit (
            code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            pe REAL,
            pe_ttm REAL,
            pb REAL,
            ps REAL,
            ps_ttm REAL,
            dv_ratio REAL,
            total_mv REAL,
            circ_mv REAL,
            PRIMARY KEY (code, trade_date)
        )
        """
    )
    conn.executemany(
        "INSERT INTO fundamentals_pit VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            # Visible before 2026-06-30
            ("600519.SH", "2025-12-31", "2026-03-30", 0.3, 0.2, 0.9, 0.2, 0.1, 0.1, 40.0, 42.0, 100.0, "年报"),
            # Future announcement — must be invisible on 2026-06-01
            ("600519.SH", "2026-06-30", "2026-08-30", 0.35, 0.22, 0.91, 0.19, 0.12, 0.11, 45.0, 46.0, 105.0, "中报"),
            # Missing ann_date — dropped
            ("600519.SH", "2024-12-31", None, 0.25, 0.15, 0.88, 0.21, 0.05, 0.04, 35.0, 36.0, 90.0, "年报"),
        ],
    )
    conn.execute(
        "INSERT INTO daily_basic_pit VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("600519.SH", "2026-06-01", 20.0, 21.0, 8.0, 7.0, 7.5, 1.0, 2e6, 1.5e6),
    )
    conn.commit()
    conn.close()
    return path


def test_fundamentals_pit_asof_gate(tmp_path: Path) -> None:
    db = _make_pit_db(tmp_path / "market.db")
    provider = EngineSqliteProvider(db)
    rows = provider.get_fundamentals_pit(["600519"], asof=date(2026, 6, 1))
    assert len(rows) == 1
    assert rows[0]["ann_date"] == "2026-03-30"
    assert rows[0]["end_date"] == "2025-12-31"
    assert rows[0]["roe"] == pytest.approx(0.3)
    assert rows[0]["dataNote"] == "offline_pit"

    # After mid-report announcement, newer period appears
    later = provider.get_fundamentals_pit(["600519"], asof="2026-09-01")
    assert later[0]["end_date"] == "2026-06-30"
    assert later[0]["ann_date"] == "2026-08-30"


def test_daily_basic_pit_exact_day(tmp_path: Path) -> None:
    db = _make_pit_db(tmp_path / "market.db")
    provider = EngineSqliteProvider(db)
    rows = provider.get_daily_basic_pit(["600519"], asof=date(2026, 6, 1))
    assert len(rows) == 1
    assert rows[0]["pe"] == pytest.approx(20.0)
    empty = provider.get_daily_basic_pit(["600519"], asof=date(2026, 6, 2))
    assert empty == []


def test_pit_requires_asof(tmp_path: Path) -> None:
    db = _make_pit_db(tmp_path / "market.db")
    provider = EngineSqliteProvider(db)
    with pytest.raises(ValueError, match="asof"):
        provider.get_fundamentals_pit(["600519"], asof="")  # type: ignore[arg-type]


def test_pit_missing_table_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE daily_price (code TEXT, date TEXT, close REAL, pct_chg REAL, vol REAL, amount REAL)"
    )
    conn.commit()
    conn.close()
    provider = EngineSqliteProvider(path)
    with pytest.raises(LookupError, match="fundamentals_pit"):
        provider.get_fundamentals_pit(["600519"], asof=date(2026, 6, 1))


def test_engine_missing_path_message() -> None:
    with pytest.raises(FileNotFoundError, match="STOCK_PLATFORM_ENGINE_MARKET_DB"):
        EngineSqliteProvider(None)
    assert "market.db" in MSG_DB_MISSING
    assert "asof" in MSG_ASOF_REQUIRED
    assert "fundamentals_pit" in MSG_TABLE_MISSING.format(table="fundamentals_pit")
