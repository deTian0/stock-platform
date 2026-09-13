"""Workbench API tests (TestClient, offline fixtures)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stock_platform_workbench.app import create_app
from stock_platform_workbench.state import build_default_state

FIXTURES = Path(__file__).parent / "fixtures"


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
    names = {
        c["name"]
        for row in matrix
        for c in row["candidates"]
    }
    assert "tickflow" not in names
    daily = client.get("/api/market/daily", params={"symbols": "600519"}).json()
    assert daily["provider"] in names
