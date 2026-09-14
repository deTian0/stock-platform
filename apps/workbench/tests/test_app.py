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


def test_ui_index_shell(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    body = r.text
    assert 'id="capability"' in body
    assert 'id="daily"' in body
    assert 'id="minute"' in body
    assert 'id="fund-flow"' in body
    assert 'id="lhb"' in body
    assert 'id="unlock"' in body
    assert 'id="paper"' in body
    assert 'id="debate"' in body
    assert "/static/app.js" in body


def test_static_assets(client: TestClient) -> None:
    css = client.get("/static/app.css")
    assert css.status_code == 200
    js = client.get("/static/app.js")
    assert js.status_code == 200
    # M11.2: UI must call existing APIs (fail-closed path included).
    text = js.text
    assert "/api/settings/capability-matrix" in text
    assert "/api/market/daily" in text
    assert "/api/market/fund-flow" in text
    assert "/api/market/lhb" in text
    assert "/api/market/unlock" in text
    assert "/api/paper/status" in text
    assert "/api/debate/report" in text
    assert "fail_closed" in text
    assert "/api/settings/preferences" in text


def test_capability_matrix(client: TestClient) -> None:
    r = client.get("/api/settings/capability-matrix")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 10
    by_id = {row["id"]: row for row in rows}
    assert by_id["daily"]["usable"] is True
    assert by_id["daily"]["effective"] == "replay"
    assert by_id["fund_flow"]["usable"] is True
    assert by_id["fund_flow"]["effective"] == "replay"
    assert by_id["lhb"]["usable"] is True
    assert by_id["lhb"]["effective"] == "replay"
    assert by_id["unlock"]["usable"] is True
    assert by_id["unlock"]["effective"] == "replay"
    assert by_id["minute"]["usable"] is True
    assert by_id["minute"]["effective"] == "replay"
    assert by_id["depth5"]["usable"] is True
    assert by_id["depth5"]["effective"] == "replay"
    assert by_id["financial"]["usable"] is True
    assert by_id["financial"]["effective"] == "replay"
    assert by_id["adj_factor"]["usable"] is False
    assert by_id["full_minute"]["usable"] is False


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


def test_fund_flow_replay(client: TestClient) -> None:
    r = client.get(
        "/api/market/fund-flow",
        params={"symbols": "SH600519", "start": "2026-09-01", "end": "2026-09-02"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["capability"] == "fund_flow"
    assert body["provider"] == "replay"
    assert len(body["rows"]) == 2
    assert body["rows"][0]["main_net"] == 125000000.0


def test_can_prefer_fund_flow_astock_http(client: TestClient) -> None:
    put = client.put(
        "/api/settings/preferences",
        json={"preferences": {"fund_flow": "astock_http"}},
    )
    assert put.status_code == 200
    matrix = client.get("/api/settings/capability-matrix").json()
    by_id = {row["id"]: row for row in matrix}
    assert by_id["fund_flow"]["effective"] == "astock_http"
    assert by_id["fund_flow"]["usable"] is True


def test_lhb_replay(client: TestClient) -> None:
    r = client.get(
        "/api/market/lhb",
        params={"symbols": "SZ002475", "asof_date": "2026-05-17", "look_back_days": 30},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["capability"] == "lhb"
    assert body["provider"] == "replay"
    assert len(body["items"]) == 1
    assert body["items"][0]["symbol"] == "002475"
    assert len(body["items"][0]["records"]) == 2
    assert body["items"][0]["records"][0]["net_buy"] == 85200000.0


def test_lhb_empty_window_replay(client: TestClient) -> None:
    r = client.get(
        "/api/market/lhb",
        params={"symbols": "600519", "asof_date": "2026-05-17"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["items"][0]["records"] == []
    assert body["items"][0]["institution"]["net_amt"] == 0.0


def test_can_prefer_lhb_astock_http(client: TestClient) -> None:
    put = client.put(
        "/api/settings/preferences",
        json={"preferences": {"lhb": "astock_http"}},
    )
    assert put.status_code == 200
    matrix = client.get("/api/settings/capability-matrix").json()
    by_id = {row["id"]: row for row in matrix}
    assert by_id["lhb"]["effective"] == "astock_http"
    assert by_id["lhb"]["usable"] is True


def test_unlock_replay(client: TestClient) -> None:
    r = client.get(
        "/api/market/unlock",
        params={"symbols": "SZ002475", "asof_date": "2026-05-17", "forward_days": 90},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["capability"] == "unlock"
    assert body["provider"] == "replay"
    assert len(body["items"]) == 1
    assert body["items"][0]["symbol"] == "002475"
    assert len(body["items"][0]["history"]) == 2
    assert len(body["items"][0]["upcoming"]) == 1
    assert body["items"][0]["upcoming"][0]["shares"] == 32000.0


def test_unlock_empty_replay(client: TestClient) -> None:
    r = client.get(
        "/api/market/unlock",
        params={"symbols": "600519", "asof_date": "2026-05-17"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["items"][0]["history"] == []
    assert body["items"][0]["upcoming"] == []


def test_can_prefer_unlock_astock_http(client: TestClient) -> None:
    put = client.put(
        "/api/settings/preferences",
        json={"preferences": {"unlock": "astock_http"}},
    )
    assert put.status_code == 200
    matrix = client.get("/api/settings/capability-matrix").json()
    by_id = {row["id"]: row for row in matrix}
    assert by_id["unlock"]["effective"] == "astock_http"
    assert by_id["unlock"]["usable"] is True


def test_minute_replay(client: TestClient) -> None:
    r = client.get(
        "/api/market/minute",
        params={
            "symbols": "SH600519",
            "freq": "1m",
            "start": "2026-09-01",
            "end": "2026-09-02",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["capability"] == "minute"
    assert body["provider"] == "replay"
    assert body["freq"] == "1m"
    assert len(body["rows"]) == 3
    assert body["rows"][0]["datetime"] == "2026-09-01 09:31:00"
    assert body["rows"][0]["freq"] == "1m"


def test_can_prefer_minute_astock_http(client: TestClient) -> None:
    put = client.put(
        "/api/settings/preferences",
        json={"preferences": {"minute": "astock_http"}},
    )
    assert put.status_code == 200
    matrix = client.get("/api/settings/capability-matrix").json()
    by_id = {row["id"]: row for row in matrix}
    assert by_id["minute"]["effective"] == "astock_http"
    assert by_id["minute"]["usable"] is True


def test_depth5_replay(client: TestClient) -> None:
    r = client.get("/api/market/depth5", params={"symbols": "SH600519"})
    assert r.status_code == 200
    body = r.json()
    assert body["capability"] == "depth5"
    assert body["provider"] == "replay"
    assert len(body["rows"]) == 1
    assert body["rows"][0]["symbol"] == "600519"
    assert body["rows"][0]["bid_prices"][0] == 1425.0
    assert body["rows"][0]["ask_volumes"][-1] == 52


def test_can_prefer_depth5_astock_http(client: TestClient) -> None:
    put = client.put(
        "/api/settings/preferences",
        json={"preferences": {"depth5": "astock_http"}},
    )
    assert put.status_code == 200
    matrix = client.get("/api/settings/capability-matrix").json()
    by_id = {row["id"]: row for row in matrix}
    assert by_id["depth5"]["effective"] == "astock_http"
    assert by_id["depth5"]["usable"] is True


def test_financial_replay(client: TestClient) -> None:
    r = client.get("/api/market/financial", params={"symbols": "SH600519", "periods": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["capability"] == "financial"
    assert body["provider"] == "replay"
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["symbol"] == "600519"
    assert item["income"][0]["revenue"] == 39112000000.0
    assert item["balance"][0]["total_assets"] == 310000000000.0


def test_can_prefer_financial_astock_http(client: TestClient) -> None:
    put = client.put(
        "/api/settings/preferences",
        json={"preferences": {"financial": "astock_http"}},
    )
    assert put.status_code == 200
    matrix = client.get("/api/settings/capability-matrix").json()
    by_id = {row["id"]: row for row in matrix}
    assert by_id["financial"]["effective"] == "astock_http"
    assert by_id["financial"]["usable"] is True


def test_adj_factor_fail_closed(client: TestClient) -> None:
    r = client.get("/api/market/financial", params={"symbols": "600519"})
    # financial usable; adj_factor / full_minute remain fail-closed sentinels
    assert r.status_code == 200
    matrix = client.get("/api/settings/capability-matrix").json()
    by_id = {row["id"]: row for row in matrix}
    assert by_id["financial"]["usable"] is True
    assert by_id["adj_factor"]["usable"] is False
    assert by_id["full_minute"]["usable"] is False


def test_prefer_unavailable_capability_still_fail_closed(client: TestClient) -> None:
    r = client.put(
        "/api/settings/preferences",
        json={"preferences": {"adj_factor": "astock_http", "daily": "replay"}},
    )
    assert r.status_code == 200
    assert r.json()["preferences"]["adj_factor"] == "astock_http"
    matrix = client.get("/api/settings/capability-matrix").json()
    by_id = {row["id"]: row for row in matrix}
    assert by_id["adj_factor"]["usable"] is False
    assert by_id["adj_factor"]["candidates"] == []


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


def test_research_and_review_slots(client: TestClient) -> None:
    r = client.get(
        "/api/research/report",
        params={"symbol": "SH600519", "asof": "2026-09-02"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "research"
    assert body["provider"] == "replay"
    assert body["symbol"] == "600519"
    assert any("跳过 realtime" in w or "早于今天" in w for w in body["warnings"])

    rev = client.get(
        "/api/review/report",
        params={"symbol": "600519", "asof": "2026-09-02"},
    )
    assert rev.status_code == 200
    assert rev.json()["kind"] == "review"


def test_debate_slot(client: TestClient) -> None:
    r = client.get(
        "/api/debate/report",
        params={"symbol": "600519", "asof": "2026-09-02"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "debate"
    assert body["verdict"] in {"Buy", "Hold", "Sell"}
    assert any(round_["role"] == "bull" for round_ in body["rounds"])
    assert "非投资建议" in body["disclaimer"]


def test_research_rejects_hk(client: TestClient) -> None:
    r = client.get("/api/research/report", params={"symbol": "00700"})
    assert r.status_code == 400


def test_can_prefer_astock_http_without_calling_network(client: TestClient) -> None:
    put = client.put(
        "/api/settings/preferences",
        json={"preferences": {"daily": "astock_http", "realtime": "astock_http"}},
    )
    assert put.status_code == 200
    assert put.json()["preferences"]["daily"] == "astock_http"
    matrix = client.get("/api/settings/capability-matrix").json()
    by_id = {row["id"]: row for row in matrix}
    assert by_id["daily"]["effective"] == "astock_http"
    assert by_id["daily"]["usable"] is True


def test_can_prefer_global_http_without_calling_network(client: TestClient) -> None:
    put = client.put(
        "/api/settings/preferences",
        json={"preferences": {"daily": "global_http", "realtime": "global_http"}},
    )
    assert put.status_code == 200
    assert put.json()["preferences"]["daily"] == "global_http"
    matrix = client.get("/api/settings/capability-matrix").json()
    by_id = {row["id"]: row for row in matrix}
    assert by_id["daily"]["effective"] == "global_http"
    assert by_id["daily"]["usable"] is True
    assert by_id["realtime"]["effective"] == "global_http"


def test_paper_status_and_activate_flow(client: TestClient) -> None:
    st = client.get("/api/paper/status")
    assert st.status_code == 200
    assert st.json()["liveTradingEnabled"] is False
    assert "SIMULATE" in st.json()["banner"]

    draft = client.post("/api/paper/strategies/draft", json={"strategy_hash": "x", "universe": ["510300"]})
    assert draft.status_code == 200
    h = draft.json()["strategyHash"]

    val = client.post("/api/paper/strategies/validate", json={"strategy_hash": h})
    assert val.status_code == 200

    act = client.post("/api/paper/strategies/activate", json={"strategy_hash": h})
    assert act.status_code == 200
    assert act.json()["stage"] == "active"

    created = client.post(
        "/api/paper/drafts",
        json={
            "signal_trade_date": "2026-09-04",
            "orders": [{"symbol": "510300", "side": "buy", "qty": 100}],
            "now": "2026-09-07T09:40:00+08:00",
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["executionEligible"] is True
    draft_id = body["draftId"]

    exe = client.post(f"/api/paper/drafts/{draft_id}/execute", params={"now": "2026-09-07T09:40:00+08:00"})
    assert exe.status_code == 200
    assert exe.json()["accepted"] is True

    again = client.post(f"/api/paper/drafts/{draft_id}/execute", params={"now": "2026-09-07T09:40:00+08:00"})
    assert again.status_code == 200
    assert again.json().get("idempotentReplay") is True
