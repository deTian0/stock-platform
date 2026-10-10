"""X3: hit-tracking API over the workbench (offline replay fixtures)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stock_platform_workbench.app import create_app
from stock_platform_workbench.state import build_default_state

FIXTURES = Path(__file__).parent / "fixtures"

BRIEF_PARAMS = {
    "asof": "2026-09-02",
    "symbols": "600519,000001",
    "topN": 5,
    "adjust_kind": "none",
}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("STOCK_PLATFORM_PROVIDER_PRESET", "replay")
    db_path = tmp_path / "test_hits.db"
    monkeypatch.setenv("STOCK_PLATFORM_DB_URL", f"sqlite:///{db_path.as_posix()}")
    from stock_platform_research import (
        SqliteBriefRepository,
        SqliteHitTrackingRepository,
        reset_brief_repository_cache,
        reset_hit_repository_cache,
    )

    reset_brief_repository_cache()
    reset_hit_repository_cache()
    state = build_default_state(FIXTURES)
    state.brief_repo = SqliteBriefRepository(db_path)
    state.hit_repo = SqliteHitTrackingRepository(db_path)
    return TestClient(create_app(state=state))


def test_empty_repo_is_zeroed_with_message(client: TestClient) -> None:
    body = client.get("/api/research/hit-tracking").json()
    assert body["environment"] == "SIMULATE"
    assert body["liveTradingEnabled"] is False
    for key in ("pre_market", "post_market", "pre_market_in_cycle"):
        assert body[key]["codeCount"] == 0
    assert body["emptyMessage"]
    assert body["cycleCalendarDays"] == 14


def test_track_from_store_then_idempotent(client: TestClient) -> None:
    # Generate + persist a brief for 2026-09-02 first.
    brief = client.get("/api/research/brief", params=dict(BRIEF_PARAMS)).json()
    assert brief["persisted"] is True

    first = client.post(
        "/api/research/hit-tracking/track",
        json={"asof": "2026-09-02", "session": "pre_market", "boards": "quality"},
    ).json()
    assert first["tracked"]["recorded"] >= 1
    assert first["pre_market"]["cumulativeHits"] >= 1

    # Same day + session → dedup, nothing new.
    second = client.post(
        "/api/research/hit-tracking/track",
        json={"asof": "2026-09-02", "session": "pre_market", "boards": "quality"},
    ).json()
    assert second["tracked"]["recorded"] == 0

    view = client.get(
        "/api/research/hit-tracking", params={"session": "pre_market"}
    ).json()
    assert view["pre_market"]["cumulativeHits"] >= 1
    assert view["details"]


def test_track_missing_brief_is_404(client: TestClient) -> None:
    resp = client.post(
        "/api/research/hit-tracking/track",
        json={"asof": "2026-08-01", "session": "pre_market", "fromStore": True},
    )
    assert resp.status_code == 404
    assert "未找到" in resp.json()["detail"]


def test_invalid_session_is_400(client: TestClient) -> None:
    resp = client.get("/api/research/hit-tracking", params={"session": "midday"})
    assert resp.status_code == 400


def test_ui_has_the_hits_panel(client: TestClient) -> None:
    html = client.get("/").text
    assert 'id="hits"' in html
    assert 'id="hits-table"' in html
    js = client.get("/static/app.js").text
    assert "loadHits" in js
    assert "renderHitsTable" in js
