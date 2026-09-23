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
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    # CI / unit tests stay offline — force replay regardless of production default.
    monkeypatch.setenv("STOCK_PLATFORM_PROVIDER_PRESET", "replay")
    db_path = tmp_path / "test_briefs.db"
    monkeypatch.setenv("STOCK_PLATFORM_DB_URL", f"sqlite:///{db_path.as_posix()}")
    perf_log = tmp_path / "recommend_decisions.jsonl"
    monkeypatch.setenv("STOCK_PLATFORM_PERFORMANCE_LOG", str(perf_log))
    from stock_platform_research import reset_brief_repository_cache

    reset_brief_repository_cache()
    state = build_default_state(FIXTURES)
    from stock_platform_research import SqliteBriefRepository

    state.brief_repo = SqliteBriefRepository(db_path)
    app = create_app(state=state)
    return TestClient(app)


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ops_health_default_replay(client: TestClient) -> None:
    r = client.get("/api/ops/health")
    assert r.status_code == 200
    body = r.json()
    assert body["liveTradingEnabled"] is False
    assert body["executionMode"] == "SIMULATE"
    assert body["defaultReplay"] is True
    assert body["providerPreset"] == "replay"
    assert body["briefFallback"] is None or isinstance(body["briefFallback"], str)
    assert "supplementTokenConfigured" in body
    assert isinstance(body["supplementTokenConfigured"], bool)
    assert body["eastmoney"]["minInterval"] >= 0
    assert "circuitOpen" in body["eastmoney"]
    assert body["lastRefresh"] is None


def test_ui_index_shell(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    body = r.text
    assert 'id="capability"' in body
    assert 'id="daily"' in body
    assert 'id="realtime"' in body
    assert 'id="minute"' in body
    assert 'id="realtime-cards"' in body
    assert 'id="news-list"' in body
    assert "主力净流入" in body
    assert "现价" in body
    assert "涨跌幅" in body
    assert 'id="fund-flow"' in body
    assert 'id="sector-fund-flow"' in body
    assert 'id="news"' in body
    assert 'id="lhb"' in body
    assert 'id="unlock"' in body
    assert 'id="concept-blocks"' in body
    assert 'id="pit-fundamentals"' in body
    assert 'id="concept-blocks-form"' in body
    assert 'id="pit-fundamentals-form"' in body
    assert "loadConceptBlocks" in client.get("/static/app.js").text
    assert "loadPitFundamentals" in client.get("/static/app.js").text
    assert 'id="adj-factor"' in body
    assert 'id="daily-adjusted"' in body
    assert 'id="full-minute"' in body
    assert 'id="paper"' in body
    assert 'id="broker"' in body
    assert 'id="debate"' in body
    assert 'id="recommend"' in body
    assert 'id="wizard"' in body
    assert 'id="ops"' in body
    assert 'id="recommend-cards"' in body
    assert 'id="wizard-view"' in body
    assert 'id="ops-kv"' in body
    assert 'id="paper-kv"' in body
    assert 'id="market-tools"' in body
    assert 'id="lab"' in body
    assert "原始 JSON" in body
    assert "日用向导" in body
    assert "无实盘" in body or "SIMULATE" in body
    assert 'id="performance"' in body
    assert 'id="backtest"' in body
    assert 'id="backtest-form"' in body
    assert 'id="walkforward-form"' in body
    assert 'id="strategy-compare"' in body
    assert 'id="tsp-subset"' in body
    assert 'id="tsp-accuracy-spark"' in body
    assert 'id="intel-report"' in body
    assert 'id="intel-report-table"' in body
    assert 'id="btn-intel-prefill"' in body
    assert 'id="intel-crosswalk"' in body
    assert "情报报告" in body
    assert "/static/report-templates/a-share-preopen.html" in body
    _js = client.get("/static/app.js").text
    assert "/api/research/intel-report/prefill" in _js
    assert "/api/research/intel-report/crosswalk" in _js
    assert "runIntelPrefill" in _js
    assert 'id="recommend-strategy-ab"' in body
    assert 'id="recommend-tier"' in body
    assert 'id="recommend-perf-strip"' in body
    assert "recentDays" in client.get("/static/app.js").text
    assert "renderAccuracySparkline" in client.get("/static/app.js").text
    assert "runWalkForwardSummary" in client.get("/static/app.js").text
    assert "strategyAb" in client.get("/static/app.js").text
    assert "tsp-spark" in client.get("/static/app.css").text
    assert 'id="pref-preset"' in body
    assert 'id="recommend-review-block"' in body
    assert 'id="recommend-review-table"' in body
    assert 'id="btn-performance-log-stored"' in body
    assert 'id="btn-performance-settle"' in body
    assert 'id="strategy-require-engine"' in body
    assert "复盘" in body
    assert "/static/app.js" in body
    assert "/static/app.css" in body


def test_static_assets(client: TestClient) -> None:
    css = client.get("/static/app.css")
    assert css.status_code == 200
    assert "rec-card" in css.text
    assert "rec-quick" in css.text
    assert "group-summary" in css.text
    assert ".kv" in css.text
    assert ".steps" in css.text
    assert ".snap-card" in css.text
    assert ".news-item" in css.text
    assert ".pos" in css.text
    assert ".neg" in css.text
    for name in (
        "a-share-preopen.html",
        "a-share-intraday.html",
        "us-preopen.html",
    ):
        tpl = client.get(f"/static/report-templates/{name}")
        assert tpl.status_code == 200, name
        assert "{{" in tpl.text or "html" in tpl.text.lower()
    js = client.get("/static/app.js")
    assert js.status_code == 200
    # M11.2: UI must call existing APIs (fail-closed path included).
    text = js.text
    assert "renderRecommendCards" in text
    assert "renderKv" in text
    assert "renderSteps" in text
    assert "formatPrice" in text
    assert "formatPct" in text
    assert "formatMoney" in text
    assert "formatVolume" in text
    assert "emptyTable" in text
    assert "renderRealtimeCards" in text
    assert "renderNewsList" in text
    assert "/api/settings/capability-matrix" in text
    assert "/api/market/daily" in text
    assert "/api/market/realtime" in text
    assert "/api/market/fund-flow" in text
    assert "/api/market/sector-fund-flow" in text
    assert "/api/market/news" in text
    assert "/api/research/backtest/walk-forward" in text
    assert "/api/market/lhb" in text
    assert "/api/market/unlock" in text
    assert "/api/market/adj-factor" in text
    assert "/api/market/daily-adjusted" in text
    assert "/api/market/full-minute" in text
    assert "/api/paper/status" in text
    assert "/api/broker/status" in text
    assert "/api/debate/report" in text
    assert "/api/research/brief" in text
    assert "/api/research/briefs" in text
    assert "/api/research/brief/to-paper" in text
    assert "/api/research/brief/to-broker" in text
    assert "/api/research/brief/debate" in text
    assert "/api/research/performance" in text
    assert "/api/research/strategy/compare" in text
    assert "/api/research/backtest/rolling-review" in text
    assert "openBacktestDay" in text
    assert "loadRecommendPerfStrip" in text
    assert "fail_closed" in text
    assert "/api/settings/preferences" in text
    assert "/api/settings/presets/" in text


def test_research_performance(client: TestClient) -> None:
    r = client.get("/api/research/performance")
    assert r.status_code == 200
    body = r.json()
    assert body["liveTradingEnabled"] is False
    assert body["environment"] == "SIMULATE"
    assert body["settledCount"] >= 1
    assert "direction_accuracy" in body["metrics"]
    assert "direction_accuracy" in body["metricDefinitions"]


def test_strategy_compare_api(client: TestClient) -> None:
    listed = client.get("/api/research/strategy/configs")
    assert listed.status_code == 200
    assert listed.json()["liveTradingEnabled"] is False
    assert len(listed.json()["configs"]) >= 2
    r = client.post(
        "/api/research/strategy/compare",
        json={"configA": "lvrev-default-v1", "configB": "lvrev-rev-heavy-v1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["liveTradingEnabled"] is False
    assert "deltaFinalEquity" in body
    assert body["a"]["tradeCount"] >= 1
    # No engine in default CI client → fixture fallback, never silent about source
    assert body.get("panelSource") == "fixture"
    assert "panelNote" in body


def test_strategy_ab_default_off_on_brief(client: TestClient) -> None:
    st = client.get("/api/research/strategy/ab-status")
    assert st.status_code == 200
    assert st.json()["enabled"] is False
    assert st.json()["defaultOnDailyPath"] is False
    r = client.get(
        "/api/research/brief",
        params={
            "asof": "2026-09-02",
            "symbols": "600519,000001",
            "topN": 3,
            "adjust_kind": "none",
            "persist": "false",
        },
    )
    assert r.status_code == 200
    body = r.json()
    ab = body.get("strategyAb") or {}
    assert ab.get("enabled") is False
    assert ab.get("replacesPicks") is False


def test_strategy_ab_opt_in_query(client: TestClient) -> None:
    r = client.get(
        "/api/research/brief",
        params={
            "asof": "2026-09-02",
            "symbols": "600519,000001",
            "topN": 3,
            "adjust_kind": "none",
            "persist": "false",
            "strategyAb": "true",
        },
    )
    assert r.status_code == 200
    body = r.json()
    ab = body["strategyAb"]
    assert ab.get("enabled") is True
    assert ab.get("replacesPicks") is False
    assert ab.get("ok") is True
    assert "picks" in body


def test_factor_ic_api(client: TestClient) -> None:
    r = client.post(
        "/api/research/backtest/factor-ic",
        json={
            "rows": [
                {"asof": "2026-01-02", "factor": 1, "forward_return": 0.01},
                {"asof": "2026-01-02", "factor": 2, "forward_return": 0.02},
                {"asof": "2026-01-02", "factor": 3, "forward_return": 0.03},
                {"asof": "2026-01-03", "factor": 3, "forward_return": -0.01},
                {"asof": "2026-01-03", "factor": 2, "forward_return": 0.0},
                {"asof": "2026-01-03", "factor": 1, "forward_return": 0.02},
            ]
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["n_dates"] == 2
    assert body["icir"] is not None
    assert body["liveTradingEnabled"] is False


def test_deep_graph_status_default_off(client: TestClient) -> None:
    r = client.get("/api/debate/deep-graph/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["defaultEngine"] == "deterministic"


def test_strategy_compare_require_engine_fail_closed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stock_platform_workbench.routes.research as research_routes

    monkeypatch.setattr(
        research_routes,
        "_settle_get_daily",
        lambda request: (None, None),
    )
    r = client.post(
        "/api/research/strategy/compare",
        json={
            "configA": "lvrev-default-v1",
            "configB": "lvrev-rev-heavy-v1",
            "requireEngine": True,
        },
    )
    assert r.status_code == 503
    assert "ENGINE_MARKET_DB" in (r.json().get("detail") or "")


def test_strategy_compare_with_engine_sqlite(client: TestClient, tmp_path: Path) -> None:
    import sqlite3
    from datetime import date, timedelta

    from stock_platform_providers.engine_sqlite import EngineSqliteProvider

    db = tmp_path / "market.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE daily_price (code TEXT, date TEXT, close REAL, pct_chg REAL, vol REAL, amount REAL, PRIMARY KEY(code,date))"
    )
    start = date(2026, 1, 5)
    symbols = [("600519.SH", "600519"), ("000001.SZ", "000001")]
    for i in range(100):
        d = start + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        for code, _bare in symbols:
            close = 100.0 + i * 0.15
            conn.execute(
                "INSERT INTO daily_price VALUES (?,?,?,?,?,?)",
                (code, d.isoformat(), close, 0.1, 1.0, 1.0),
            )
    conn.commit()
    conn.close()

    state = client.app.state.workbench
    state.providers["engine_sqlite"] = EngineSqliteProvider(db)
    r = client.post(
        "/api/research/strategy/compare",
        json={
            "configA": "lvrev-default-v1",
            "configB": "lvrev-rev-heavy-v1",
            "lastN": 5,
            "universeTier": "core",
            "symbols": "600519,000001",
            "requireEngine": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["panelSource"] == "engine_sqlite"
    assert body["panelRows"] >= 2
    assert body["liveTradingEnabled"] is False


def test_rolling_backtest_fail_closed_without_engine(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """No daily source → 503 Chinese fail-closed (not silent fixtures)."""
    import stock_platform_workbench.routes.research as research_routes

    monkeypatch.setattr(
        research_routes,
        "_settle_get_daily",
        lambda request: (None, None),
    )
    r = client.post(
        "/api/research/backtest/rolling-review",
        json={"lastN": 3, "universeTier": "core", "topN": 2, "holding": "1d"},
    )
    assert r.status_code == 503
    assert "日线" in (r.json().get("detail") or "")
    assert "ENGINE_MARKET_DB" in (r.json().get("detail") or "")

def test_rolling_backtest_with_engine_sqlite(client: TestClient, tmp_path: Path) -> None:
    import sqlite3
    from datetime import date, timedelta

    from stock_platform_providers.engine_sqlite import EngineSqliteProvider

    db = tmp_path / "market.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE daily_price (code TEXT, date TEXT, close REAL, pct_chg REAL, vol REAL, amount REAL, PRIMARY KEY(code,date))"
    )
    start = date(2026, 1, 5)
    symbols = [("600519.SH", "600519"), ("000001.SZ", "000001"), ("000858.SZ", "000858")]
    for i in range(90):
        d = start + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        for code, _bare in symbols:
            close = 100.0 + i * 0.1
            conn.execute(
                "INSERT INTO daily_price VALUES (?,?,?,?,?,?)",
                (code, d.isoformat(), close, 0.1, 1.0, 1.0),
            )
    conn.commit()
    conn.close()

    state = client.app.state.workbench
    state.providers["engine_sqlite"] = EngineSqliteProvider(db)
    r = client.post(
        "/api/research/backtest/rolling-review",
        json={
            "lastN": 3,
            "universeTier": "core",
            "symbols": "600519,000001,000858",
            "topN": 2,
            "holding": "1d",
            "softGates": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["dailySource"] == "engine_sqlite"
    assert body["liveTradingEnabled"] is False
    assert body["environment"] == "SIMULATE"
    assert body["asofCount"] == 3
    assert "direction_accuracy" in body
    assert body["settledCount"] >= 0


def test_defaults_universe_tier(client: TestClient) -> None:
    watch = client.get("/api/research/defaults", params={"universeTier": "watch"})
    assert watch.status_code == 200
    w = watch.json()
    assert w["universeTier"] == "watch"
    assert w["symbolCount"] >= 5
    assert "universeTiers" in w
    full = client.get("/api/research/defaults", params={"universeTier": "full"})
    assert full.status_code == 200
    f = full.json()
    assert f["universeTier"] == "full"
    assert f["symbolCount"] >= w["symbolCount"]


def test_capability_matrix(client: TestClient) -> None:
    r = client.get("/api/settings/capability-matrix")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 13
    by_id = {row["id"]: row for row in rows}
    assert by_id["daily"]["usable"] is True
    assert by_id["daily"]["effective"] == "replay"
    assert by_id["fund_flow"]["usable"] is True
    assert by_id["fund_flow"]["effective"] == "replay"
    assert by_id["sector_fund_flow"]["usable"] is True
    assert by_id["sector_fund_flow"]["effective"] == "replay"
    assert by_id["news"]["usable"] is True
    assert by_id["news"]["effective"] == "replay"
    assert by_id["concept_blocks"]["usable"] is True
    assert by_id["concept_blocks"]["effective"] == "replay"
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
    assert by_id["adj_factor"]["usable"] is True
    assert by_id["adj_factor"]["effective"] == "replay"
    assert by_id["full_minute"]["usable"] is True
    assert by_id["full_minute"]["effective"] == "replay"


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


def test_sector_fund_flow_replay(client: TestClient) -> None:
    r = client.get(
        "/api/market/sector-fund-flow",
        params={"sectors": "BK0477", "start": "2026-09-01", "end": "2026-09-02"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["capability"] == "sector_fund_flow"
    assert body["provider"] == "replay"
    assert len(body["rows"]) == 2
    assert body["rows"][0]["sector_code"] == "BK0477"
    assert body["rows"][0]["main_net"] == 350000000.0


def test_news_replay(client: TestClient) -> None:
    r = client.get(
        "/api/market/news",
        params={"symbols": "SH600519", "start": "2026-09-01", "end": "2026-09-02"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["capability"] == "news"
    assert body["provider"] == "replay"
    assert len(body["rows"]) == 2
    assert body["rows"][0]["symbol"] == "600519"
    assert body["rows"][0]["title"].startswith("贵州茅台")


def test_concept_blocks_replay(client: TestClient) -> None:
    r = client.get("/api/market/concept-blocks", params={"symbols": "SH600519"})
    assert r.status_code == 200
    body = r.json()
    assert body["capability"] == "concept_blocks"
    assert body["provider"] == "replay"
    assert body["items"][0]["symbol"] == "600519"
    assert body["items"][0]["total"] == 3
    assert "食品饮料" in body["items"][0]["concept_tags"]


def test_walk_forward_summary_api(client: TestClient) -> None:
    r = client.post(
        "/api/research/backtest/walk-forward",
        json={
            "start": "2020-01-01",
            "end": "2020-12-31",
            "trainDays": 60,
            "testDays": 20,
            "stepDays": 20,
            "foldRecords": [
                {
                    "index": 0,
                    "test_end": "2020-05-01",
                    "is_score": 0.1,
                    "oos_objective": 0.05,
                    "oos_stats": {"total_return": 0.05},
                }
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["n_valid_folds"] == 1
    assert body["summary"]["compounded_oos_return"] == pytest.approx(0.05)
    assert body["liveTradingEnabled"] is False


def test_pit_fundamentals_fail_closed_without_db(client: TestClient) -> None:
    r = client.get(
        "/api/research/pit/fundamentals",
        params={"symbols": "600519", "asof": "2026-06-01"},
    )
    assert r.status_code == 503
    assert "market.db" in str(r.json()["detail"])


def test_can_prefer_sector_fund_flow_and_news_astock_http(client: TestClient) -> None:
    put = client.put(
        "/api/settings/preferences",
        json={
            "preferences": {
                "sector_fund_flow": "astock_http",
                "news": "astock_http",
            }
        },
    )
    assert put.status_code == 200
    matrix = client.get("/api/settings/capability-matrix").json()
    by_id = {row["id"]: row for row in matrix}
    assert by_id["sector_fund_flow"]["effective"] == "astock_http"
    assert by_id["news"]["effective"] == "astock_http"
    assert by_id["sector_fund_flow"]["usable"] is True
    assert by_id["news"]["usable"] is True


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


def test_adj_factor_replay(client: TestClient) -> None:
    r = client.get("/api/market/adj-factor", params={"symbols": "SH600519", "kind": "qfq"})
    assert r.status_code == 200
    body = r.json()
    assert body["capability"] == "adj_factor"
    assert body["provider"] == "replay"
    assert body["kind"] == "qfq"
    assert len(body["rows"]) >= 3
    assert body["rows"][0]["symbol"] == "600519"
    assert body["rows"][0]["trade_date"] == "2026-06-26"
    assert body["rows"][0]["ex_factor"] == 1.0


def test_daily_adjusted_replay(client: TestClient) -> None:
    r = client.get(
        "/api/market/daily-adjusted",
        params={"symbols": "SH600519", "kind": "qfq", "start": "2026-09-01", "end": "2026-09-02"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["capabilities"] == ["daily", "adj_factor"]
    assert body["providers"]["daily"] == "replay"
    assert body["providers"]["adj_factor"] == "replay"
    assert body["kind"] == "qfq"
    assert len(body["rows"]) == 2
    assert body["rows"][0]["symbol"] == "600519"
    assert body["rows"][0]["ex_factor"] == 1.0
    assert body["rows"][0]["adjust_kind"] == "qfq"
    assert body["rows"][0]["close"] == 1410.0


def test_daily_adjusted_missing_factors_400(client: TestClient) -> None:
    # 510300 has daily for sample universe but no adj_factor → 400.
    r = client.get("/api/market/daily-adjusted", params={"symbols": "510300", "kind": "qfq"})
    assert r.status_code == 400


def test_can_prefer_adj_factor_astock_http(client: TestClient) -> None:
    put = client.put(
        "/api/settings/preferences",
        json={"preferences": {"adj_factor": "astock_http"}},
    )
    assert put.status_code == 200
    matrix = client.get("/api/settings/capability-matrix").json()
    by_id = {row["id"]: row for row in matrix}
    assert by_id["adj_factor"]["effective"] == "astock_http"
    assert by_id["adj_factor"]["usable"] is True


def test_full_minute_replay(client: TestClient) -> None:
    r = client.get(
        "/api/market/full-minute",
        params={"symbols": "600519,000001", "trade_date": "2026-09-01", "count": 300},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["capability"] == "full_minute"
    assert body["provider"] == "replay"
    assert body["trade_date"] == "2026-09-01"
    assert len(body["rows"]) == 5
    assert all(row["freq"] == "1m" for row in body["rows"])
    assert {row["symbol"] for row in body["rows"]} == {"600519", "000001"}


def test_can_prefer_full_minute_astock_http(client: TestClient) -> None:
    put = client.put(
        "/api/settings/preferences",
        json={"preferences": {"full_minute": "astock_http"}},
    )
    assert put.status_code == 200
    matrix = client.get("/api/settings/capability-matrix").json()
    by_id = {row["id"]: row for row in matrix}
    assert by_id["full_minute"]["effective"] == "astock_http"
    assert by_id["full_minute"]["usable"] is True


def test_prefer_unknown_provider_falls_back(client: TestClient) -> None:
    """Preferring a non-candidate name still leaves full_minute usable via fallback."""
    r = client.put(
        "/api/settings/preferences",
        json={"preferences": {"full_minute": "tickflow", "daily": "replay"}},
    )
    assert r.status_code == 200
    matrix = client.get("/api/settings/capability-matrix").json()
    by_id = {row["id"]: row for row in matrix}
    assert by_id["full_minute"]["usable"] is True
    assert by_id["full_minute"]["effective"] == "replay"
    assert by_id["full_minute"]["candidates"]


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


def test_debate_llm_fail_closed_without_env(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    st = client.get("/api/debate/status")
    assert st.status_code == 200
    assert st.json()["defaultEngine"] == "deterministic"
    # Default M44 fallback is deterministic (soft degrade).
    soft = client.get(
        "/api/debate/report",
        params={"symbol": "600519", "asof": "2026-09-02", "engine": "llm"},
    )
    assert soft.status_code == 200
    assert soft.json()["kind"] == "debate"
    # Explicit fail-closed still returns 400.
    monkeypatch.setenv("STOCK_PLATFORM_LLM_FALLBACK", "fail-closed")
    r = client.get(
        "/api/debate/report",
        params={"symbol": "600519", "asof": "2026-09-02", "engine": "llm"},
    )
    assert r.status_code == 400
    assert "fail-closed" in r.json()["detail"]


def test_brief_debate_deterministic(client: TestClient) -> None:
    r = client.post(
        "/api/research/brief/debate",
        json={
            "asof": "2026-09-02",
            "symbols": "600519,000001",
            "topN": 2,
            "adjust_kind": "none",
            "engine": "deterministic",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["engine"] == "deterministic"
    assert body["liveTradingEnabled"] is False
    assert "brief" in body
    assert isinstance(body["debates"], list)
    # Fixture panel may gate to zero picks; unit tests cover non-empty debate_brief_picks.
    for item in body["debates"]:
        assert item["debate"]["kind"] == "debate"

    llm = client.post(
        "/api/research/brief/debate",
        json={
            "asof": "2026-09-02",
            "symbols": "600519",
            "topN": 1,
            "adjust_kind": "none",
            "engine": "llm",
        },
    )
    # M44: default STOCK_PLATFORM_LLM_FALLBACK=deterministic → soft degrade (200).
    assert llm.status_code == 200
    assert llm.json()["liveTradingEnabled"] is False


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


def test_apply_live_preset_does_not_enable_trading(client: TestClient) -> None:
    listed = client.get("/api/settings/presets")
    assert listed.status_code == 200
    assert listed.json()["default"] == "cn_astock_http"
    ids = {p["id"] for p in listed.json()["presets"]}
    assert "cn_tushare_http" in ids
    assert "cn_engine_sqlite" in ids
    r = client.post("/api/settings/presets/cn_astock_http/apply")
    assert r.status_code == 200
    body = r.json()
    assert body["applied"] == "cn_astock_http"
    assert body["isDefault"] is True
    assert body["preferences"]["daily"] == "astock_http"
    assert body["preferences"]["full_minute"] == "astock_http"
    assert body["liveTradingEnabled"] is False
    health = client.get("/api/ops/health").json()
    assert health["liveTradingEnabled"] is False
    assert health["defaultReplay"] is False
    ts = client.post("/api/settings/presets/cn_tushare_http/apply")
    assert ts.status_code == 200
    assert ts.json()["applied"] == "cn_tushare_http"
    assert ts.json()["preferences"]["daily"] == "tushare_http"
    assert ts.json()["preferences"]["fund_flow"] == "astock_http"
    assert ts.json()["liveTradingEnabled"] is False
    unknown = client.post("/api/settings/presets/tickflow/apply")
    assert unknown.status_code == 404
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


def test_production_default_state_is_cn_live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STOCK_PLATFORM_PROVIDER_PRESET", raising=False)
    state = build_default_state(tmp_path)
    assert state.preferences["daily"] == "astock_http"
    assert state.preferences["fund_flow"] == "astock_http"
    assert state.preferences["news"] == "astock_http"
    assert all(v == "astock_http" for v in state.preferences.values())


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


@pytest.mark.integration
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


@pytest.mark.integration
def test_research_brief_api(client: TestClient) -> None:
    r = client.get(
        "/api/research/brief",
        params={
            "asof": "2026-09-02",
            "symbols": "600519,000001",
            "topN": 5,
            "adjust_kind": "none",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["asof"] == "2026-09-02"
    assert body["market"] == "CN"
    assert body["environment"] == "SIMULATE"
    assert body["provider"] == "replay"
    assert "picks" in body
    assert isinstance(body["picks"], list)
    assert body.get("persistOk") is True
    assert body.get("persisted") is True
    assert body.get("perfLogOk") is True
    assert body.get("perfLogAppended", 0) >= 1

    # Idempotent: regenerating same asof should not duplicate performance rows
    again = client.get(
        "/api/research/brief",
        params={
            "asof": "2026-09-02",
            "symbols": "600519,000001",
            "topN": 3,
            "adjust_kind": "none",
        },
    )
    assert again.status_code == 200
    assert again.json().get("perfLogOk") is True
    assert again.json().get("perfLogAppended") == 0

    perf = client.get("/api/research/performance")
    assert perf.status_code == 200
    assert perf.json()["pendingCount"] >= 1
    assert perf.json()["totalEntries"] >= 1


def test_log_brief_from_store(client: TestClient) -> None:
    client.get(
        "/api/research/brief",
        params={"asof": "2026-09-02", "symbols": "600519", "topN": 1, "adjust_kind": "none"},
    )
    r = client.post(
        "/api/research/performance/log-brief",
        json={"asof": "2026-09-02", "fromStore": True, "holding": "5d"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["fromStore"] is True
    assert body["appended"] == 0  # already logged on generate
    assert body["liveTradingEnabled"] is False


def test_performance_auto_settle_keeps_pending_without_enough_bars(
    client: TestClient,
) -> None:
    """Replay fixtures lack T+5 after 2026-09-02 → pending stays; API still 200."""
    client.get(
        "/api/research/brief",
        params={"asof": "2026-09-02", "symbols": "600519", "topN": 1, "adjust_kind": "none"},
    )
    r = client.get("/api/research/performance", params={"autoSettle": True})
    assert r.status_code == 200
    body = r.json()
    assert body["pendingCount"] >= 1
    assert body.get("settledNewly", 0) == 0
    assert "direction_accuracy" in body["metrics"] or body["settledCount"] == 0


def test_performance_settle_endpoint_with_injected_engine(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sqlite3

    from stock_platform_providers import EngineSqliteProvider

    db = tmp_path / "market.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE daily_price (code TEXT, date TEXT, close REAL, pct_chg REAL, vol REAL, amount REAL, PRIMARY KEY(code,date))"
    )
    # Enough sessions after 2026-09-02 for holding=5d
    dates = [
        "2026-09-02",
        "2026-09-03",
        "2026-09-04",
        "2026-09-05",
        "2026-09-08",
        "2026-09-09",
        "2026-09-10",
    ]
    for i, d in enumerate(dates):
        conn.execute(
            "INSERT INTO daily_price VALUES (?,?,?,?,?,?)",
            ("600519.SH", d, 100.0 + i, 0.0, 1.0, 1.0),
        )
    conn.commit()
    conn.close()

    # Log pending with 1d holding via brief then rewrite holding — use direct log
    from stock_platform_research.performance import append_jsonl, default_performance_log_path

    path = default_performance_log_path()
    append_jsonl(
        path,
        {
            "date": "2026-09-02",
            "symbol": "600519",
            "rating": "Buy",
            "raw": None,
            "holding": "1d",
            "pending": True,
            "source": "test",
        },
    )
    state = client.app.state.workbench
    state.providers["engine_sqlite"] = EngineSqliteProvider(db)
    r = client.post("/api/research/performance/settle")
    assert r.status_code == 200
    body = r.json()
    assert body["settleSource"] == "engine_sqlite"
    assert body["settledNewly"] >= 1
    assert body["pendingCount"] == 0
    assert body["metrics"]["direction_accuracy"] == pytest.approx(1.0)


@pytest.mark.integration
def test_research_briefs_persist_list_and_get(client: TestClient) -> None:
    r = client.get(
        "/api/research/brief",
        params={
            "asof": "2026-09-02",
            "symbols": "600519,000001",
            "topN": 3,
            "adjust_kind": "none",
        },
    )
    assert r.status_code == 200
    brief = r.json()
    assert brief["persistOk"] is True

    listed = client.get("/api/research/briefs", params={"limit": 10})
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert any(i["asof"] == "2026-09-02" for i in items)

    got = client.get("/api/research/briefs/2026-09-02")
    assert got.status_code == 200
    stored = got.json()
    assert stored["asof"] == "2026-09-02"
    assert stored["environment"] == "SIMULATE"
    assert isinstance(stored.get("picks"), list)

    missing = client.get("/api/research/briefs/2099-01-01")
    assert missing.status_code == 404
    assert "未找到" in str(missing.json()["detail"])


@pytest.mark.integration
def test_research_brief_review_skeleton(client: TestClient) -> None:
    client.get(
        "/api/research/brief",
        params={"asof": "2026-09-02", "symbols": "600519", "topN": 1, "adjust_kind": "none"},
    )
    rev = client.get("/api/research/briefs/2026-09-02/review", params={"holding": "1d"})
    assert rev.status_code == 200
    body = rev.json()
    assert body["asof"] == "2026-09-02"
    assert body["environment"] == "SIMULATE"
    assert "rows" in body
    assert body["liveTradingEnabled"] is False
    assert "direction_accuracy" in body
    assert "directionAccuracy" in body
    assert "todo" not in body

    # Daily path: no prior activate — auto-ensures default SIMULATE strategy
    ok = client.post(
        "/api/research/brief/to-paper",
        json={
            "asof": "2026-09-02",
            "symbols": "600519",
            "topN": 1,
            "adjust_kind": "none",
            "decision_only": True,
            "now": "2026-09-07T09:40:00+08:00",
            "market": "CN",
        },
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["liveTradingEnabled"] is False
    assert body["environment"] == "SIMULATE"
    assert body["strategyAutoActivated"] is True
    assert body["strategyStatus"] == "已自动激活默认纸面策略"
    assert body["draft"]["signalTradeDate"] == "2026-09-02"
    assert body["draft"]["decisionOnly"] is True

    # Idempotent: second call keeps existing active strategy
    again = client.post(
        "/api/research/brief/to-paper",
        json={
            "asof": "2026-09-02",
            "symbols": "600519",
            "topN": 1,
            "adjust_kind": "none",
            "decision_only": True,
            "now": "2026-09-07T09:40:00+08:00",
            "market": "CN",
        },
    )
    assert again.status_code == 200
    assert again.json()["strategyAutoActivated"] is False
    assert again.json()["strategyStatus"] is None


@pytest.mark.integration
def test_paper_ensure_default_and_draft_auto_activate(client: TestClient) -> None:
    ensured = client.post("/api/paper/strategies/ensure-default")
    assert ensured.status_code == 200
    body = ensured.json()
    assert body["liveTradingEnabled"] is False
    assert body["strategyAutoActivated"] is True
    assert body["strategyStatus"] == "已自动激活默认纸面策略"

    # Fresh client state already has active from same process — use drafts without prior activate
    # on a path that previously would 400
    created = client.post(
        "/api/paper/drafts",
        json={
            "signal_trade_date": "2026-09-04",
            "orders": [{"symbol": "510300", "side": "buy", "qty": 100}],
            "decision_only": True,
            "now": "2026-09-07T09:40:00+08:00",
        },
    )
    assert created.status_code == 200
    assert created.json()["strategyAutoActivated"] is False  # already active
    assert created.json()["liveTradingEnabled"] is False


def test_broker_status_readonly(client: TestClient) -> None:
    r = client.get("/api/broker/status")
    assert r.status_code == 200
    body = r.json()
    assert body["liveTradingEnabled"] is False
    assert body["environment"] == "SIMULATE"
    assert body["broker"] == "paper"
    assert "hint" in body


@pytest.mark.integration
def test_brief_to_broker_alias(client: TestClient) -> None:
    draft = client.post("/api/paper/strategies/draft", json={"strategy_hash": "x", "universe": ["600519"]})
    h = draft.json()["strategyHash"]
    client.post("/api/paper/strategies/validate", json={"strategy_hash": h})
    client.post("/api/paper/strategies/activate", json={"strategy_hash": h})
    ok = client.post(
        "/api/research/brief/to-broker",
        json={
            "asof": "2026-09-02",
            "symbols": "600519",
            "topN": 1,
            "adjust_kind": "none",
            "decision_only": True,
            "now": "2026-09-07T09:40:00+08:00",
        },
    )
    assert ok.status_code == 200
    assert ok.json()["liveTradingEnabled"] is False


def test_ops_health_last_refresh_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCK_PLATFORM_REFRESH_DIR", str(tmp_path))
    (tmp_path / "latest.json").write_text(
        '{"ok": false, "asof": "2026-09-02", "failCount": 2, "outDir": "x"}',
        encoding="utf-8",
    )
    state = build_default_state(FIXTURES)
    client = TestClient(create_app(state=state))
    body = client.get("/api/ops/health").json()
    assert body["status"] == "degraded"
    assert body["lastRefresh"]["ok"] is False
    assert body["lastRefresh"]["asof"] == "2026-09-02"
    assert body["liveTradingEnabled"] is False


@pytest.mark.integration
def test_wizard_daily_replay_to_paper(client: TestClient) -> None:
    # No manual draft/validate/activate — wizard auto-ensures default SIMULATE strategy
    r = client.post(
        "/api/research/wizard/daily",
        json={
            "asof": "2026-09-02",
            "symbols": "600519",
            "topN": 1,
            "adjust_kind": "none",
            "skipRefresh": True,
            "toPaper": True,
            "decision_only": True,
            "now": "2026-09-07T09:40:00+08:00",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["liveTradingEnabled"] is False
    assert body["environment"] == "SIMULATE"
    assert body["strategyAutoActivated"] is True
    assert body["strategyStatus"] == "已自动激活默认纸面策略"
    steps = {s["step"]: s for s in body["steps"]}
    assert steps["refresh"]["skipped"] is True
    assert steps["brief"]["ok"] is True
    assert steps["to_paper"]["ok"] is True
    assert steps["to_paper"]["strategyAutoActivated"] is True
    assert "/api/research/wizard/daily" in client.get("/static/app.js").text
    assert "已自动激活默认纸面策略" in client.get("/static/app.js").text
    assert "/api/paper/strategies/ensure-default" in client.get("/static/app.js").text


@pytest.mark.integration
def test_wizard_brief_connection_abort_returns_503_zh(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Live-style ConnectionError after retries → 503 Chinese tip (no silent replay)."""
    from http.client import RemoteDisconnected

    import requests
    from stock_platform_workbench.paper_ux import UPSTREAM_LIVE_TIP_ZH

    def boom(*_a, **_k):
        raise requests.exceptions.ConnectionError(
            "Connection aborted.",
            RemoteDisconnected("Remote end closed connection without response"),
        )

    monkeypatch.setattr(
        "stock_platform_workbench.brief_ux.build_premarket_brief",
        boom,
    )
    r = client.post(
        "/api/research/wizard/daily",
        json={
            "asof": "2026-09-02",
            "symbols": "600519",
            "topN": 1,
            "adjust_kind": "none",
            "skipRefresh": True,
            "toPaper": False,
        },
    )
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["ok"] is False
    assert detail["liveTradingEnabled"] is False
    assert UPSTREAM_LIVE_TIP_ZH in str(detail.get("error") or "")
    assert detail["steps"][1]["step"] == "brief"
    assert detail["steps"][1]["ok"] is False


def test_brief_fallback_to_replay_when_live_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Live daily transport failure + STOCK_PLATFORM_BRIEF_FALLBACK=replay → fixtures."""
    from http.client import RemoteDisconnected

    import requests

    monkeypatch.setenv("STOCK_PLATFORM_BRIEF_FALLBACK", "replay")
    state = client.app.state.workbench
    state.preferences["daily"] = "astock_http"
    live = state.providers["astock_http"]

    def boom_daily(*_a, **_k):
        raise requests.exceptions.ConnectionError(
            "Connection aborted.",
            RemoteDisconnected("Remote end closed connection without response"),
        )

    monkeypatch.setattr(live, "get_daily", boom_daily)
    r = client.get(
        "/api/research/brief",
        params={
            "asof": "2026-09-02",
            "symbols": "600519,000001",
            "topN": 5,
            "adjust_kind": "none",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["picks"]) >= 1
    assert body.get("providerFallback") is True
    assert "已回退" in (body.get("dataNote") or "")
    assert body["provider"] == "replay"


def test_brief_fallback_to_supplementary_with_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Live fail + token set → supplementary HTTP daily (mocked POST)."""
    from http.client import RemoteDisconnected

    import requests

    monkeypatch.delenv("STOCK_PLATFORM_BRIEF_FALLBACK", raising=False)
    monkeypatch.setenv("STOCK_PLATFORM_TUSHARE_TOKEN", "test-token-not-real")
    state = client.app.state.workbench
    state.preferences["daily"] = "astock_http"
    live = state.providers["astock_http"]
    monkeypatch.setattr(
        live,
        "get_daily",
        lambda *_a, **_k: (_ for _ in ()).throw(
            requests.exceptions.ConnectionError(
                "Connection aborted.",
                RemoteDisconnected("Remote end closed connection without response"),
            )
        ),
    )

    # Point supplementary provider at replay transport via get_daily delegate
    replay = state.providers["replay"]

    def ts_daily(symbols, start=None, end=None, **_k):
        return replay.get_daily(symbols, start=start, end=end)

    monkeypatch.setattr(state.providers["tushare_http"], "get_daily", ts_daily)
    r = client.get(
        "/api/research/brief",
        params={
            "asof": "2026-09-02",
            "symbols": "600519,000001",
            "topN": 5,
            "adjust_kind": "none",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["picks"]) >= 1
    assert body.get("providerFallback") is True
    assert "已回退 Tushare" in (body.get("dataNote") or "")
    assert body["provider"] == "tushare_http"


def test_brief_empty_panel_falls_back_to_replay_with_asof_align(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Primary daily returns empty for recent asof + BRIEF_FALLBACK=replay → fixture day."""
    monkeypatch.setenv("STOCK_PLATFORM_BRIEF_FALLBACK", "replay")
    state = client.app.state.workbench
    state.preferences["daily"] = "tushare_http"

    def empty_daily(*_a, **_k):
        return []

    monkeypatch.setattr(state.providers["tushare_http"], "get_daily", empty_daily)
    r = client.get(
        "/api/research/brief",
        params={
            "asof": "2026-09-15",
            "symbols": "600519,000001,510300",
            "topN": 5,
            "adjust_kind": "none",
            "softGates": "true",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["picks"]) >= 1
    assert body["asof"] == "2026-09-02"
    assert body.get("providerFallback") is True
    assert body["provider"] == "replay"
    assert "样例日" in (body.get("dataNote") or "")


def test_brief_empty_picks_message_when_panel_empty(client: TestClient) -> None:
    r = client.get(
        "/api/research/brief",
        params={
            "asof": "2026-09-15",
            "symbols": "600519",
            "topN": 5,
            "adjust_kind": "none",
            "softGates": "true",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["picks"] == []
    assert body["panelSize"] == 0
    assert "emptyPicksMessage" in body
    assert "截面为空" in body["emptyPicksMessage"]
    assert "emptyPicksTip" in body


def test_research_defaults_and_brief_without_asof(client: TestClient) -> None:
    defaults = client.get("/api/research/defaults")
    assert defaults.status_code == 200
    body = defaults.json()
    assert body["asof"] == "2026-09-02"  # replay fixture horizon
    assert "600519" in body["symbols"]
    assert body["liveTradingEnabled"] is False
    assert body.get("universeTier") == "watch"
    assert int(body.get("topN") or 0) >= 5
    assert int(body.get("symbolCount") or 0) >= 3
    assert body.get("asofMode") in {"replay_fixture", "last_completed_cn_session"}
    assert body.get("generatedAt")
    assert body.get("loadingHint")
    assert body.get("hint")

    r = client.get(
        "/api/research/brief",
        params={"symbols": "600519,000001,510300", "topN": 5, "adjust_kind": "none"},
    )
    assert r.status_code == 200
    brief = r.json()
    assert brief["asof"] == "2026-09-02"
    assert len(brief["picks"]) >= 1
    assert brief.get("generatedAt")
    assert "生成今日推荐" in client.get("/").text
    assert "/api/research/defaults" in client.get("/static/app.js").text


def test_ui_shows_generate_cta(client: TestClient) -> None:
    body = client.get("/").text
    assert "生成今日推荐" in body
    assert "今日选股结果" in body
    assert 'id="recommend-kv"' in body
    assert 'id="recommend-loading"' in body
    assert "写入纸面（SIMULATE）" in body
    assert "关键理由" in body
    assert 'value="600519,000001,510300"' not in body
    js = client.get("/static/app.js").text
    assert "applyBriefToRecommendPanel" in js
    assert "loadRecommendDefaults" in js
    assert "setRecommendBusy" in js
    assert "formatBriefError" in js
    assert "generatedAt" in js
    assert "gatesRelaxed" in js
    css = client.get("/static/app.css").text
    assert "is-loading" in css
    assert "button:disabled" in css
