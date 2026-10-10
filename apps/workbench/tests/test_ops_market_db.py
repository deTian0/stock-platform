"""C2: ``/api/ops/health`` surfaces read-only ``market.db`` coverage.

The guard exists because the real warehouse rotted for a month without any
signal: ``MAX(date)`` looked plausible while 17 trading days were simply absent
and 3 more carried only the 14 ETFs the engine's daily refresh writes. These
tests pin that the endpoint reports the verdict (and degrades) without ever
returning 5xx or touching the warehouse for writes.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stock_platform_providers.calendar import get_trading_calendar
from stock_platform_workbench.app import create_app
from stock_platform_workbench.state import build_default_state

FIXTURES = Path(__file__).parent / "fixtures"
ENV_MARKET_DB = "STOCK_PLATFORM_ENGINE_MARKET_DB"


def _expected_days(lookback_days: int = 30) -> list[date]:
    cal = get_trading_calendar("CN")
    end = cal.last_trading_day(date.today())
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
        "CREATE TABLE daily_price (code TEXT NOT NULL, date TEXT NOT NULL, "
        "close REAL, pct_chg REAL, vol REAL, amount REAL, PRIMARY KEY (code, date))"
    )
    conn.executemany(
        "INSERT INTO daily_price VALUES (?,?,?,?,?,?)",
        [
            (f"{day}#{i:05d}", day, 10.0, 0.0, 100.0, 1e4)
            for day, n in rows_by_day.items()
            for i in range(n)
        ],
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    def _build(market_db: Path | None) -> TestClient:
        monkeypatch.setenv("STOCK_PLATFORM_PROVIDER_PRESET", "replay")
        monkeypatch.setenv(
            "STOCK_PLATFORM_DB_URL", f"sqlite:///{(tmp_path / 'briefs.db').as_posix()}"
        )
        monkeypatch.setenv("STOCK_PLATFORM_PERFORMANCE_LOG", str(tmp_path / "perf.jsonl"))
        if market_db is None:
            monkeypatch.delenv(ENV_MARKET_DB, raising=False)
        else:
            monkeypatch.setenv(ENV_MARKET_DB, str(market_db))
        from stock_platform_research import (
            SqliteBriefRepository,
            reset_brief_repository_cache,
        )

        reset_brief_repository_cache()
        state = build_default_state(FIXTURES)
        state.brief_repo = SqliteBriefRepository(tmp_path / "briefs.db")
        return TestClient(create_app(state=state))

    return _build


def test_unconfigured_market_db_keeps_health_ok(client) -> None:
    body = client(None).get("/api/ops/health").json()
    assert body["status"] == "ok"
    assert body["marketDb"]["configured"] is False
    assert body["marketDb"]["status"] == "unconfigured"
    assert "STOCK_PLATFORM_ENGINE_MARKET_DB" in body["marketDb"]["message"]


def test_full_window_reports_ok(client, tmp_path: Path) -> None:
    db = _make_db(
        tmp_path / "market.db", {d.isoformat(): 3000 for d in _expected_days()}
    )
    body = client(db).get("/api/ops/health").json()
    assert body["marketDb"]["configured"] is True
    assert body["marketDb"]["status"] == "ok"
    assert body["marketDb"]["lagTradingDays"] == 0
    assert body["status"] == "ok"


def test_thin_day_degrades_health(client, tmp_path: Path) -> None:
    """The exact incident signature: full history, latest day only 14 ETF rows."""
    days = _expected_days()
    rows = {d.isoformat(): 3000 for d in days}
    rows[days[-1].isoformat()] = 14
    body = client(_make_db(tmp_path / "market.db", rows)).get("/api/ops/health").json()
    assert body["marketDb"]["status"] == "thin"
    assert body["marketDb"]["thinDays"] == [
        {"date": days[-1].isoformat(), "rows": 14}
    ]
    assert body["status"] == "degraded"


def test_missing_days_degrade_health(client, tmp_path: Path) -> None:
    days = _expected_days()
    rows = {d.isoformat(): 3000 for d in days[:-3]}
    body = client(_make_db(tmp_path / "market.db", rows)).get("/api/ops/health").json()
    assert body["marketDb"]["status"] == "stale"
    assert body["marketDb"]["lagTradingDays"] == 3
    assert len(body["marketDb"]["missingDays"]) == 3
    assert body["status"] == "degraded"


def test_unreadable_db_reports_error_without_5xx(client, tmp_path: Path) -> None:
    bogus = tmp_path / "market.db"
    bogus.write_text("not a sqlite file", encoding="utf-8")
    r = client(bogus).get("/api/ops/health")
    assert r.status_code == 200
    body = r.json()
    assert body["marketDb"]["status"] == "error"
    assert body["marketDb"]["message"]
    assert body["status"] == "degraded"
