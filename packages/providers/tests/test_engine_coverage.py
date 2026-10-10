"""C2: read-only ``daily_price`` coverage / freshness guard.

Pins the detection contract for the failure mode that went unnoticed for a month
on the real warehouse: the engine ingest stalls, ``MAX(date)`` still looks
plausible, and the only symptom is a run of days that are *missing* or *thin*
(~14 ETF rows instead of a ~5.2k full-market cross-section).

All tests run against a synthetic SQLite file — CI never opens the 3.14 GB
warehouse, and no test may ever write to it.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from stock_platform_providers.calendar import get_trading_calendar
from stock_platform_providers.engine_sqlite import EngineSqliteProvider

ASOF = date(2026, 9, 8)  # Tuesday, a CN trading day
LOOKBACK = 30
MIN_ROWS = 100


def _expected_days(asof: date, lookback_days: int) -> list[date]:
    """CN trading days in ``[asof-lookback, asof]`` — the calendar is the oracle."""
    cal = get_trading_calendar("CN")
    end = cal.last_trading_day(asof)
    start = end - timedelta(days=lookback_days)
    out: list[date] = []
    cur = start
    while cur <= end:
        if cal.is_trading_day(cur):
            out.append(cur)
        cur += timedelta(days=1)
    return out


def _make_db(path: Path, rows_by_day: dict[str, int]) -> Path:
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
    payload = [
        (f"{day}#{i:05d}", day, 10.0, 0.0, 100.0, 1e4)
        for day, n in rows_by_day.items()
        for i in range(n)
    ]
    conn.executemany("INSERT INTO daily_price VALUES (?,?,?,?,?,?)", payload)
    conn.commit()
    conn.close()
    return path


def _snap(tmp_path: Path, rows_by_day: dict[str, int]) -> dict:
    db = _make_db(tmp_path / "market.db", rows_by_day)
    return EngineSqliteProvider(db_path=db).coverage_snapshot(
        asof=ASOF, lookback_days=LOOKBACK, min_rows=MIN_ROWS
    )


def test_ok_when_window_complete(tmp_path: Path) -> None:
    days = _expected_days(ASOF, LOOKBACK)
    snap = _snap(tmp_path, {d.isoformat(): MIN_ROWS for d in days})
    assert snap["status"] == "ok"
    assert snap["latestTradeDate"] == ASOF.isoformat()
    assert snap["lagTradingDays"] == 0
    assert snap["missingDays"] == []
    assert snap["thinDays"] == []
    assert snap["expectedDays"] == len(days)


def test_thin_when_a_day_falls_below_the_floor(tmp_path: Path) -> None:
    days = _expected_days(ASOF, LOOKBACK)
    rows = {d.isoformat(): MIN_ROWS for d in days}
    rows[days[-1].isoformat()] = 14  # the real incident signature
    snap = _snap(tmp_path, rows)
    assert snap["status"] == "thin"
    assert snap["thinDays"] == [{"date": days[-1].isoformat(), "rows": 14}]
    assert snap["missingDays"] == []
    assert snap["latestRows"] == 14


def test_stale_when_a_day_is_missing(tmp_path: Path) -> None:
    days = _expected_days(ASOF, LOOKBACK)
    rows = {d.isoformat(): MIN_ROWS for d in days[:-1]}  # drop the last trading day
    snap = _snap(tmp_path, rows)
    assert snap["status"] == "stale"
    assert snap["missingDays"] == [days[-1].isoformat()]
    assert snap["lagTradingDays"] == 1


def test_lag_counts_trading_days_not_calendar_days(tmp_path: Path) -> None:
    """A weekend tail must not look like staleness: Fri → Mon is a lag of 1."""
    cal = get_trading_calendar("CN")
    friday = cal.prev_trading_day(ASOF)  # ASOF is a Tuesday; walk back to a Friday
    while friday.weekday() != 4:
        friday = cal.prev_trading_day(friday)
    days = _expected_days(friday, LOOKBACK)
    rows = {d.isoformat(): MIN_ROWS for d in days}
    db = _make_db(tmp_path / "market.db", rows)
    snap = EngineSqliteProvider(db_path=db).coverage_snapshot(
        asof=friday, lookback_days=LOOKBACK, min_rows=MIN_ROWS
    )
    assert snap["status"] == "ok"
    assert snap["lagTradingDays"] == 0
    # Same data, evaluated three trading days later: only *trading* days count.
    later = cal.next_trading_day(cal.next_trading_day(cal.next_trading_day(friday)))
    snap2 = EngineSqliteProvider(db_path=db).coverage_snapshot(
        asof=later, lookback_days=LOOKBACK, min_rows=MIN_ROWS
    )
    assert snap2["lagTradingDays"] == 3  # Mon, Tue, Wed — not the calendar-day count


def test_empty_when_window_has_no_rows(tmp_path: Path) -> None:
    snap = _snap(tmp_path, {"2020-01-02": 5000})  # far outside the window
    assert snap["status"] == "empty"
    assert snap["latestTradeDate"] is None
    assert snap["latestRows"] == 0


def test_missing_table_is_reported_not_raised(tmp_path: Path) -> None:
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()  # valid file, no daily_price
    snap = EngineSqliteProvider(db_path=db).coverage_snapshot(asof=ASOF)
    assert snap["status"] == "missing_table"
    assert "daily_price" in snap["message"]


def test_snapshot_shape_and_readonly(tmp_path: Path) -> None:
    days = _expected_days(ASOF, LOOKBACK)
    db = _make_db(tmp_path / "market.db", {d.isoformat(): MIN_ROWS for d in days})
    before = (db.stat().st_size, db.stat().st_mtime_ns)
    snap = EngineSqliteProvider(db_path=db).coverage_snapshot(
        asof=ASOF, lookback_days=LOOKBACK, min_rows=MIN_ROWS
    )
    for key in (
        "status",
        "dbPath",
        "expectedTradingDay",
        "latestTradeDate",
        "latestRows",
        "lagTradingDays",
        "windowStart",
        "lookbackDays",
        "minRowsPerDay",
        "expectedDays",
        "missingDays",
        "thinDays",
        "message",
    ):
        assert key in snap, key
    assert snap["expectedTradingDay"] == ASOF.isoformat()
    assert snap["minRowsPerDay"] == MIN_ROWS
    assert (db.stat().st_size, db.stat().st_mtime_ns) == before  # read-only in practice
    assert snap["message"]


def test_asof_defaults_to_last_trading_day_of_today(tmp_path: Path) -> None:
    """No asof → today's last trading day; the field is ISO and never in the future."""
    _make_db(tmp_path / "market.db", {})
    snap = EngineSqliteProvider(db_path=tmp_path / "market.db").coverage_snapshot()
    expected = get_trading_calendar("CN").last_trading_day(date.today())
    assert snap["expectedTradingDay"] == expected.isoformat()
    assert snap["status"] == "empty"


@pytest.mark.parametrize("bad", ["not-a-date"])
def test_bad_asof_raises_value_error(tmp_path: Path, bad: str) -> None:
    _make_db(tmp_path / "market.db", {})
    with pytest.raises(ValueError):
        EngineSqliteProvider(db_path=tmp_path / "market.db").coverage_snapshot(asof=bad)
