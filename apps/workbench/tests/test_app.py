"""Workbench API tests (TestClient, offline fixtures)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stock_platform_providers import ReplayProvider, ReplayTransport
from stock_platform_workbench.app import create_app
from stock_platform_workbench.state import build_default_state

FIXTURES = Path(__file__).parent / "fixtures"
ROUTES_DIR = Path(__file__).resolve().parents[1] / "src" / "stock_platform_workbench" / "routes"

# Brands that must not appear as hard-coded defaults in generic route modules.
FORBIDDEN_BRAND_TOKENS = ("tickflow", "tushare", "akshare", "eastmoney.com")


@pytest.fixture()
def client() -> TestClient:
    state = build_default_state(FIXTURES)
    app = create_app(state=state)
    return TestClient(app)


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_capability_matrix(client: TestClient) -> None:
    r = client.get("/api/settings/capability-matrix")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 7
    by_id = {row["id"]: row for row in rows}
    assert by_id["daily"]["usable"] is True
    assert by_id["daily"]["effective"] == "replay"
    assert by_id["minute"]["usable"] is False


def test_daily_and_realtime(client: TestClient) -> None:
    d = client.get("/api/market/daily", params={"symbols": "SH600519"})
    assert d.status_code == 200
    body = d.json()
    assert body["capability"] == "daily"
    assert body["provider"] == "replay"
    assert body["rows"][0]["symbol"] == "600519"

    rt = client.get("/api/market/realtime", params={"symbols": "600519"})
    assert rt.status_code == 200
    assert rt.json()["rows"][0]["change_pct"] == pytest.approx(0.010638)


def test_minute_fail_closed(client: TestClient) -> None:
    r = client.get("/api/market/minute", params={"symbols": "600519"})
    assert r.status_code == 409
    detail = r.json()
    assert detail["capability"] == "minute"
    assert detail["usable"] is False
    assert detail["reason"] == "capability_not_usable"


def test_routes_do_not_hardcode_tickflow(client: TestClient) -> None:
    """Smoke: responses never claim a brand source that is not in matrix."""
    matrix = client.get("/api/settings/capability-matrix").json()
    names = {c["name"] for row in matrix for c in row["candidates"]}
    assert "tickflow" not in names
    daily = client.get("/api/market/daily", params={"symbols": "600519"}).json()
    assert daily["provider"] in names


def test_route_modules_forbid_brand_literals() -> None:
    for path in ROUTES_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_BRAND_TOKENS:
            assert token not in text, f"{path.name} contains forbidden token {token!r}"


def test_prefer_unavailable_minute_still_fail_closed(client: TestClient) -> None:
    r = client.put(
        "/api/settings/preferences",
        json={"preferences": {"minute": "astock_http", "daily": "replay"}},
    )
    assert r.status_code == 200
    assert r.json()["preferences"]["minute"] == "astock_http"
    minute = client.get("/api/market/minute", params={"symbols": "600519"})
    assert minute.status_code == 409
    assert minute.json()["usable"] is False


def test_api_matches_direct_replay_same_symbol_day(client: TestClient) -> None:
    """M2.3: workbench daily rows match batch ReplayProvider for same symbol/day."""
    direct = ReplayProvider(ReplayTransport(FIXTURES)).get_daily(
        ["600519"], start=date(2026, 9, 1), end=date(2026, 9, 2)
    )
    api = client.get(
        "/api/market/daily",
        params={"symbols": "600519", "start": "2026-09-01", "end": "2026-09-02"},
    )
    assert api.status_code == 200
    rows = api.json()["rows"]
    assert len(rows) == len(direct) == 2
    for a, b in zip(rows, direct, strict=True):
        assert a["symbol"] == b["symbol"] == "600519"
        assert a["date"] == b["date"]
        assert a["close"] == b["close"]
        assert a["volume"] == b["volume"]
        assert a["amount"] == b["amount"]
        assert a["change_pct"] == b["change_pct"]
