"""T1: ``/api/ops/loop-health`` —— 只读转发 + fail-closed 503 + 趋势面。

把 R3 的裁决从 ``data/health/*`` 接到 Workbench 之后，必须钉住三件事：

1. **无供数 → 503**（供数段落在 ``COVERAGE_HARD_FAIL``），绝不用假数据兜底；
2. **降级不掩盖** —— 供数偏薄/滞后仍然 200，裁决在 ``verdict.status`` 里；
3. **零业务逻辑** —— 响应就是 ``collect_loop_health`` 的 payload（含 ``history``）。
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
ENV_HEALTH_DIR = "STOCK_PLATFORM_LOOP_HEALTH_DIR"


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
    def _build(market_db: Path | None, *, with_history: bool = False) -> TestClient:
        monkeypatch.setenv("STOCK_PLATFORM_PROVIDER_PRESET", "replay")
        monkeypatch.setenv(
            "STOCK_PLATFORM_DB_URL", f"sqlite:///{(tmp_path / 'briefs.db').as_posix()}"
        )
        monkeypatch.setenv("STOCK_PLATFORM_PERFORMANCE_LOG", str(tmp_path / "perf.jsonl"))
        monkeypatch.setenv(ENV_HEALTH_DIR, str(tmp_path / "health"))
        if market_db is None:
            monkeypatch.delenv(ENV_MARKET_DB, raising=False)
        else:
            monkeypatch.setenv(ENV_MARKET_DB, str(market_db))
        if with_history:
            health = tmp_path / "health"
            health.mkdir(parents=True, exist_ok=True)
            (health / "history.jsonl").write_text(
                "\n".join(
                    [
                        '{"asof":"2026-10-12","ts":"2026-10-12T01:00:00+00:00",'
                        '"status":"degraded","warned":["latestBrief"]}',
                        '{"asof":"2026-10-13","ts":"2026-10-13T01:00:00+00:00",'
                        '"status":"degraded","warned":["latestBrief"]}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
        from stock_platform_research import (
            SqliteBriefRepository,
            reset_brief_repository_cache,
            reset_hit_repository_cache,
            reset_symbol_master_cache,
        )

        # 让 latestBrief 段为 ok（asof = 最新交易日）—— 这样裁决差异只来自供数段，
        # 正是本文件要钉住的东西。绩效/命中仍为空（warn），故满窗预期为 degraded。
        SqliteBriefRepository(tmp_path / "briefs.db").save(
            {
                "asof": _expected_days()[-1].isoformat(),
                "provider": "replay",
                "picks": [{"symbol": "600519"}],
                "environment": "SIMULATE",
            }
        )
        reset_brief_repository_cache()
        reset_hit_repository_cache()
        reset_symbol_master_cache()
        return TestClient(create_app(state=build_default_state(FIXTURES)))

    return _build


def test_no_market_db_is_503_fail_closed(client) -> None:
    """未配置 ``STOCK_PLATFORM_ENGINE_MARKET_DB`` → 没有可判的循环 → 503。"""
    r = client(None).get("/api/ops/loop-health")
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["reason"] == "loop_health_no_market_db"
    assert detail["coverageStatus"] == "unavailable"
    assert detail["liveTradingEnabled"] is False


def test_unreadable_db_is_503_fail_closed(client, tmp_path: Path) -> None:
    """库存在但不可读（coverage=error）→ 同样 fail-closed，不是「看起来正常」。"""
    bogus = tmp_path / "market.db"
    bogus.write_text("not a sqlite file", encoding="utf-8")
    r = client(bogus).get("/api/ops/loop-health")
    assert r.status_code == 503
    # 库不可读 → coverage_snapshot 报 error（或直接抛 → unavailable），两档都是硬失败。
    assert r.json()["detail"]["coverageStatus"] in {"error", "unavailable"}


def test_full_window_returns_payload_and_history(client, tmp_path: Path) -> None:
    db = _make_db(
        tmp_path / "market.db", {d.isoformat(): 3000 for d in _expected_days()}
    )
    r = client(db, with_history=True).get("/api/ops/loop-health")
    assert r.status_code == 200
    body = r.json()
    assert body["liveTradingEnabled"] is False
    assert body["environment"] == "SIMULATE"
    assert body["coverage"]["status"] == "ok"
    assert body["coverage"]["lagTradingDays"] == 0
    assert body["verdict"]["status"] in {"ok", "degraded"}
    # 六路信号 + 趋势面都在（零业务逻辑：响应即 collect 的 payload）
    for key in (
        "coverage",
        "latestBrief",
        "hits",
        "performance",
        "symbolMaster",
        "nextSettlement",
        "history",
    ):
        assert key in body
    hist = body["history"]
    assert str(hist["path"]).endswith("history.jsonl")
    assert hist["daysRecorded"] == 2
    assert hist["recent"][0]["asof"] == body["asof"]


def test_thin_day_degrades_but_stays_200(client, tmp_path: Path) -> None:
    """供数偏薄 → 降级，但仍然 200（不用 5xx 掩盖「能跑要打折看」）。"""
    days = _expected_days()
    rows = {d.isoformat(): 3000 for d in days}
    rows[days[-1].isoformat()] = 14
    r = client(_make_db(tmp_path / "market.db", rows)).get("/api/ops/loop-health")
    assert r.status_code == 200
    body = r.json()
    assert body["coverage"]["status"] == "thin"
    assert body["verdict"]["status"] == "degraded"
    assert "coverage" in body["verdict"]["warned"]
