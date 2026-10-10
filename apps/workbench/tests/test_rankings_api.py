"""X2: ranking boards over the brief API (offline replay fixtures)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stock_platform_workbench.app import create_app
from stock_platform_workbench.state import build_default_state

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("STOCK_PLATFORM_PROVIDER_PRESET", "replay")
    db_path = tmp_path / "test_briefs.db"
    monkeypatch.setenv("STOCK_PLATFORM_DB_URL", f"sqlite:///{db_path.as_posix()}")
    from stock_platform_research import SqliteBriefRepository, reset_brief_repository_cache

    reset_brief_repository_cache()
    state = build_default_state(FIXTURES)
    state.brief_repo = SqliteBriefRepository(db_path)
    return TestClient(create_app(state=state))


# Replay fixtures only cover 2026-09-02 for these two codes.
BRIEF_PARAMS = {
    "asof": "2026-09-02",
    "symbols": "600519,000001",
    "topN": 5,
    "adjust_kind": "none",
}


def _book(tmp_path: Path) -> str:
    path = tmp_path / "book.json"
    path.write_text(
        json.dumps({"holdings": [{"code": "600519", "entry_price": 100.0}]}),
        encoding="utf-8",
    )
    return str(path)


def test_brief_exposes_the_five_boards(client: TestClient) -> None:
    body = client.get("/api/research/brief", params=dict(BRIEF_PARAMS)).json()
    boards = body["rankings"]["boards"]
    assert set(boards) == {"quality", "short_term", "holdings", "actions", "watchlist"}
    for board in boards.values():
        assert "key" in board and "items" in board
    assert body["rankingsCounts"] == body["rankings"]["counts"]


def test_holdings_path_fills_the_book_boards(client: TestClient, tmp_path: Path) -> None:
    body = client.get(
        "/api/research/brief",
        params={**BRIEF_PARAMS, "holdingsPath": _book(tmp_path)},
    ).json()
    assert body["holdingsLoaded"] == 1
    holdings = body["rankings"]["boards"]["holdings"]["items"]
    assert [i["symbol"] for i in holdings] == ["600519"]


def test_missing_holdings_file_is_fail_closed(client: TestClient, tmp_path: Path) -> None:
    body = client.get(
        "/api/research/brief",
        params={**BRIEF_PARAMS, "holdingsPath": str(tmp_path / "nope.json")},
    ).json()
    assert body["holdingsLoaded"] == 0
    assert "持仓文件" in (body.get("holdingsNote") or "")
    assert body["rankings"]["boards"]["holdings"]["items"] == []
    assert body["rankings"]["boards"]["actions"]["items"] == []


def test_ui_has_the_board_block(client: TestClient) -> None:
    html = client.get("/").text
    assert 'id="recommend-rankings"' in html
    js = client.get("/static/app.js").text
    assert "renderRankings" in js
