"""MR-3/MR-5: intel-report crosswalk + platform prefill (no brief SQLite writes)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stock_platform_workbench.app import create_app
from stock_platform_workbench.intel_report_ux import prefill_intel_report
from stock_platform_workbench.state import build_default_state

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("STOCK_PLATFORM_PROVIDER_PRESET", "replay")
    db_path = tmp_path / "test_briefs.db"
    monkeypatch.setenv("STOCK_PLATFORM_DB_URL", f"sqlite:///{db_path.as_posix()}")
    from stock_platform_research import SqliteBriefRepository, reset_brief_repository_cache

    reset_brief_repository_cache()
    state = build_default_state(fixtures_dir=FIXTURES)
    state.brief_repo = SqliteBriefRepository(db_path)
    return TestClient(create_app(fixtures_dir=FIXTURES, state=state))


def test_intel_report_ui_hooks(client: TestClient) -> None:
    body = client.get("/").text
    assert 'id="intel-report"' in body
    assert 'id="btn-intel-prefill"' in body
    assert 'id="intel-crosswalk"' in body
    assert 'id="intel-prefill-form"' in body
    assert "#intel-report" in body
    js = client.get("/static/app.js").text
    assert "/api/research/intel-report/prefill" in js
    assert "/api/research/intel-report/crosswalk" in js
    assert "runIntelPrefill" in js
    assert "loadIntelCrosswalk" in js


def test_intel_crosswalk_empty_brief(client: TestClient) -> None:
    r = client.get(
        "/api/research/intel-report/crosswalk",
        params={"asof": "2026-09-02"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["asof"] == "2026-09-02"
    assert body["briefPresent"] is False
    assert body["pickCount"] == 0
    assert body["writesBriefSqlite"] is False
    assert body["liveTradingEnabled"] is False
    assert "kinds" in body and len(body["kinds"]) == 3
    note = body.get("note") or ""
    assert ("禁止" in note) or ("非替换" in note)


def test_intel_prefill_partial_no_fake_indices(client: TestClient) -> None:
    r = client.get(
        "/api/research/intel-report/prefill",
        params={"kind": "a-share-preopen", "asof": "2026-09-02", "format": "json"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "a-share-preopen"
    assert body["writesBriefSqlite"] is False
    assert body["liveTradingEnabled"] is False
    assert body["remainingCount"] > 0
    assert "{{收盘点位}}" in body["html"] or any(
        "指数" in (m.get("field") or "") for m in body["missing"]
    )
    assert "platform-crosswalk" in body["html"]
    assert ("9月2日" in body["html"]) or ("2026-09-02" in body["html"])
    assert any("指数" in (m.get("field") or "") for m in body["missing"])


def test_intel_prefill_html_format(client: TestClient) -> None:
    r = client.get(
        "/api/research/intel-report/prefill",
        params={"kind": "us-preopen", "asof": "2026-09-02", "format": "html"},
    )
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "platform-crosswalk" in r.text
    assert "{{" in r.text


def test_intel_prefill_with_stored_brief(client: TestClient) -> None:
    saved = client.post(
        "/api/research/briefs",
        json={
            "asof": "2026-09-02",
            "universeTier": "watch",
            "universeSize": 2,
            "provider": "replay",
            "picks": [
                {
                    "rank": 1,
                    "symbol": "600519",
                    "composite_score": 0.91,
                    "reasonSummary": "测试理由",
                }
            ],
            "environment": "SIMULATE",
        },
    )
    assert saved.status_code == 200

    before = client.get("/api/research/briefs/2026-09-02").json()
    r = client.get(
        "/api/research/intel-report/prefill",
        params={"kind": "a-share-preopen", "asof": "2026-09-02"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["crossWalk"]["briefPresent"] is True
    assert body["crossWalk"]["pickCount"] == 1
    assert "600519" in body["html"]
    assert body["writesBriefSqlite"] is False

    after = client.get("/api/research/briefs/2026-09-02").json()
    assert after.get("picks") == before.get("picks")


def test_intel_prefill_bad_kind(client: TestClient) -> None:
    r = client.get(
        "/api/research/intel-report/prefill",
        params={"kind": "not-a-template", "asof": "2026-09-02"},
    )
    assert r.status_code == 400


def test_prefill_unit_calendar_only() -> None:
    out = prefill_intel_report(
        kind="a-share-preopen",
        asof=date(2026, 9, 2),
        brief=None,
        ops_health={"status": "ok", "providerPreset": "replay", "version": "test"},
        concept_items=None,
    )
    assert out["writesBriefSqlite"] is False
    assert out["remainingCount"] > 10
    assert any(
        ("picks" in (m.get("field") or "")) or ("brief" in (m.get("reason") or ""))
        for m in out["missing"]
    )
