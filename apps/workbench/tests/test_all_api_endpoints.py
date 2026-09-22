"""Smoke + catalog coverage for every Workbench OpenAPI path+method.

Parameterizes over `app.openapi()["paths"]` so new routes fail the coverage
gate until registered in `ENDPOINT_HITS`. Uses replay preset (zero public net).

Fail-closed paths (4xx/5xx) are intentional hits, never silent skips.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from stock_platform_workbench.app import create_app
from stock_platform_workbench.state import build_default_state

FIXTURES = Path(__file__).parent / "fixtures"

# FastAPI docs endpoints are outside the OpenAPI path table; hit once for completeness.
# HTML `/` is covered in test_app.py.
EXTRA_META_PATHS: list[tuple[str, str]] = [
    ("GET", "/docs"),
    ("GET", "/redoc"),
    ("GET", "/openapi.json"),
]

AssertFn = Callable[[Any, int], None]


@dataclass(frozen=True)
class EndpointHit:
    """One intentional request against an OpenAPI operation."""

    method: str
    path: str
    params: Mapping[str, Any] | None = None
    json: Mapping[str, Any] | None = None
    path_params: Mapping[str, str] = field(default_factory=dict)
    expect_status: frozenset[int] = field(default_factory=lambda: frozenset({200}))
    assert_body: AssertFn | None = None
    needs_brief: bool = False
    needs_paper_draft: bool = False


def _ok_live_off(body: Any, status: int) -> None:
    if status != 200 or not isinstance(body, dict):
        return
    if "liveTradingEnabled" in body:
        assert body["liveTradingEnabled"] is False


def _ok_health(body: Any, status: int) -> None:
    assert status == 200
    assert body["status"] == "ok"


def _ok_version(body: Any, status: int) -> None:
    assert status == 200
    assert isinstance(body.get("version"), str) and body["version"]


def _ok_ops_health(body: Any, status: int) -> None:
    assert status == 200
    assert body["liveTradingEnabled"] is False
    assert body["executionMode"] == "SIMULATE"
    assert body["providerPreset"] == "replay"


def _ok_matrix(body: Any, status: int) -> None:
    assert status == 200
    assert isinstance(body, list) and len(body) >= 1


def _ok_preferences(body: Any, status: int) -> None:
    assert status == 200
    assert "preferences" in body


def _ok_preferences_put(body: Any, status: int) -> None:
    assert status == 200
    assert body["preferences"]["daily"] == "replay"
    assert body.get("liveTradingEnabled", False) is False


def _ok_presets_list(body: Any, status: int) -> None:
    assert status == 200
    assert "presets" in body


def _ok_preset_apply(body: Any, status: int) -> None:
    assert status == 200
    assert body["applied"] == "cn_astock_http"
    assert body["liveTradingEnabled"] is False


def _ok_capability_rows(body: Any, status: int) -> None:
    assert status == 200
    assert body.get("capability") or body.get("capabilities")
    if "provider" in body:
        assert body["provider"] == "replay"
    if "providers" in body and isinstance(body["providers"], dict):
        assert all(v == "replay" for v in body["providers"].values())


def _ok_kind(kind: str) -> AssertFn:
    def _check(body: Any, status: int) -> None:
        assert status == 200
        assert body["kind"] == kind

    return _check


def _ok_debate_status(body: Any, status: int) -> None:
    assert status == 200
    assert "defaultEngine" in body


def _ok_deep_graph_status(body: Any, status: int) -> None:
    assert status == 200
    assert body.get("enabled") is False


def _ok_deep_graph(body: Any, status: int) -> None:
    assert (status == 200 and isinstance(body, dict)) or (status == 400 and "detail" in body)


def _ok_paper_status(body: Any, status: int) -> None:
    assert status == 200
    assert body["liveTradingEnabled"] is False


def _ok_strategy_hash(body: Any, status: int) -> None:
    assert status == 200
    assert "strategyHash" in body


def _ok_ensure_default(body: Any, status: int) -> None:
    assert status == 200
    assert body["liveTradingEnabled"] is False
    assert body["environment"] == "SIMULATE"


def _ok_paper_draft(body: Any, status: int) -> None:
    assert status == 200
    assert body["liveTradingEnabled"] is False


def _ok_broker(body: Any, status: int) -> None:
    assert status == 200
    assert body["liveTradingEnabled"] is False
    assert body["environment"] == "SIMULATE"


def _ok_defaults(body: Any, status: int) -> None:
    assert status == 200
    assert body["liveTradingEnabled"] is False


def _ok_brief(body: Any, status: int) -> None:
    assert status == 200
    assert "picks" in body
    assert body["environment"] == "SIMULATE"


def _ok_briefs_list(body: Any, status: int) -> None:
    assert status == 200
    assert "items" in body


def _ok_brief_save(body: Any, status: int) -> None:
    assert status == 200
    assert body["ok"] is True
    assert body["liveTradingEnabled"] is False


def _ok_brief_get(body: Any, status: int) -> None:
    assert (status == 200 and body.get("asof") == "2026-09-02") or status == 404


def _ok_wizard(body: Any, status: int) -> None:
    assert status == 200
    assert body["ok"] is True
    assert body["liveTradingEnabled"] is False


def _ok_performance(body: Any, status: int) -> None:
    assert status == 200
    assert body["liveTradingEnabled"] is False
    assert "metrics" in body


def _ok_log_brief(body: Any, status: int) -> None:
    assert status == 200
    assert body["liveTradingEnabled"] is False


def _ok_strategy_configs(body: Any, status: int) -> None:
    assert status == 200
    assert "configs" in body


def _ok_ab_status(body: Any, status: int) -> None:
    assert status == 200
    assert body.get("enabled") is False


def _ok_compare(body: Any, status: int) -> None:
    assert status == 200
    assert body["liveTradingEnabled"] is False


def _ok_rolling(body: Any, status: int) -> None:
    assert (status == 200 and body.get("ok") is True) or (status == 503 and "detail" in body)


def _ok_walk_forward(body: Any, status: int) -> None:
    assert status == 200
    assert body["ok"] is True


def _ok_factor_ic(body: Any, status: int) -> None:
    assert status == 200
    assert body["ok"] is True


def _ok_pit(body: Any, status: int) -> None:
    assert (status == 200 and isinstance(body, dict)) or (status == 503 and "detail" in body)


ENDPOINT_HITS: dict[tuple[str, str], EndpointHit] = {}


def _reg(hit: EndpointHit) -> None:
    key = (hit.method.upper(), hit.path)
    assert key not in ENDPOINT_HITS, f"duplicate catalog entry {key}"
    ENDPOINT_HITS[key] = hit


_SYM = {"symbols": "600519"}

# meta / ops
_reg(EndpointHit("GET", "/health", assert_body=_ok_health))
_reg(EndpointHit("GET", "/version", assert_body=_ok_version))
_reg(EndpointHit("GET", "/api/ops/health", assert_body=_ok_ops_health))

# settings
_reg(EndpointHit("GET", "/api/settings/capability-matrix", assert_body=_ok_matrix))
_reg(EndpointHit("GET", "/api/settings/preferences", assert_body=_ok_preferences))
_reg(
    EndpointHit(
        "PUT",
        "/api/settings/preferences",
        json={"preferences": {"daily": "replay"}},
        assert_body=_ok_preferences_put,
    )
)
_reg(EndpointHit("GET", "/api/settings/presets", assert_body=_ok_presets_list))
_reg(
    EndpointHit(
        "POST",
        "/api/settings/presets/{preset_id}/apply",
        path_params={"preset_id": "cn_astock_http"},
        assert_body=_ok_preset_apply,
    )
)

# market
_reg(
    EndpointHit(
        "GET",
        "/api/market/daily",
        params={**_SYM, "start": "2026-09-01", "end": "2026-09-02"},
        assert_body=_ok_capability_rows,
    )
)
_reg(EndpointHit("GET", "/api/market/realtime", params=_SYM, assert_body=_ok_capability_rows))
_reg(
    EndpointHit(
        "GET",
        "/api/market/minute",
        params={**_SYM, "freq": "1m", "start": "2026-09-01", "end": "2026-09-02"},
        assert_body=_ok_capability_rows,
    )
)
_reg(
    EndpointHit(
        "GET",
        "/api/market/fund-flow",
        params={**_SYM, "start": "2026-09-01", "end": "2026-09-02"},
        assert_body=_ok_capability_rows,
    )
)
_reg(
    EndpointHit(
        "GET",
        "/api/market/sector-fund-flow",
        params={"sectors": "BK0477", "start": "2026-09-01", "end": "2026-09-02"},
        assert_body=_ok_capability_rows,
    )
)
_reg(
    EndpointHit(
        "GET",
        "/api/market/news",
        params={**_SYM, "start": "2026-09-01", "end": "2026-09-02"},
        assert_body=_ok_capability_rows,
    )
)
_reg(EndpointHit("GET", "/api/market/concept-blocks", params=_SYM, assert_body=_ok_capability_rows))
_reg(
    EndpointHit(
        "GET",
        "/api/market/lhb",
        params={**_SYM, "asof_date": "2026-05-17"},
        assert_body=_ok_capability_rows,
    )
)
_reg(
    EndpointHit(
        "GET",
        "/api/market/unlock",
        params={**_SYM, "asof_date": "2026-05-17"},
        assert_body=_ok_capability_rows,
    )
)
_reg(EndpointHit("GET", "/api/market/depth5", params=_SYM, assert_body=_ok_capability_rows))
_reg(
    EndpointHit(
        "GET",
        "/api/market/financial",
        params={**_SYM, "periods": 2},
        assert_body=_ok_capability_rows,
    )
)
_reg(
    EndpointHit(
        "GET",
        "/api/market/adj-factor",
        params={**_SYM, "kind": "qfq"},
        assert_body=_ok_capability_rows,
    )
)
_reg(
    EndpointHit(
        "GET",
        "/api/market/full-minute",
        params={**_SYM, "trade_date": "2026-09-01"},
        assert_body=_ok_capability_rows,
    )
)
_reg(
    EndpointHit(
        "GET",
        "/api/market/daily-adjusted",
        params={**_SYM, "kind": "qfq", "start": "2026-09-01", "end": "2026-09-02"},
        assert_body=_ok_capability_rows,
    )
)

# agents
_reg(
    EndpointHit(
        "GET",
        "/api/research/report",
        params={"symbol": "600519", "asof": "2026-09-02"},
        assert_body=_ok_kind("research"),
    )
)
_reg(
    EndpointHit(
        "GET",
        "/api/review/report",
        params={"symbol": "600519", "asof": "2026-09-02"},
        assert_body=_ok_kind("review"),
    )
)
_reg(EndpointHit("GET", "/api/debate/status", assert_body=_ok_debate_status))
_reg(
    EndpointHit(
        "GET",
        "/api/debate/report",
        params={"symbol": "600519", "asof": "2026-09-02"},
        assert_body=_ok_kind("debate"),
    )
)
_reg(EndpointHit("GET", "/api/debate/deep-graph/status", assert_body=_ok_deep_graph_status))
_reg(
    EndpointHit(
        "POST",
        "/api/debate/deep-graph",
        json={"symbol": "600519", "asof": "2026-09-02"},
        expect_status=frozenset({200, 400}),
        assert_body=_ok_deep_graph,
    )
)

# paper / broker
_reg(EndpointHit("GET", "/api/paper/status", assert_body=_ok_paper_status))
_reg(
    EndpointHit(
        "POST",
        "/api/paper/strategies/draft",
        json={"strategy_hash": "x", "universe": ["510300"]},
        assert_body=_ok_strategy_hash,
    )
)
_reg(
    EndpointHit(
        "POST",
        "/api/paper/strategies/validate",
        json={"strategy_hash": "missing-hash-for-smoke"},
        expect_status=frozenset({200, 400}),
        assert_body=_ok_live_off,
    )
)
_reg(
    EndpointHit(
        "POST",
        "/api/paper/strategies/activate",
        json={"strategy_hash": "missing-hash-for-smoke"},
        expect_status=frozenset({200, 400}),
        assert_body=_ok_live_off,
    )
)
_reg(EndpointHit("POST", "/api/paper/strategies/ensure-default", assert_body=_ok_ensure_default))
_reg(
    EndpointHit(
        "POST",
        "/api/paper/drafts",
        json={
            "signal_trade_date": "2026-09-04",
            "orders": [{"symbol": "510300", "side": "buy", "qty": 100}],
            "decision_only": True,
            "now": "2026-09-07T09:40:00+08:00",
        },
        assert_body=_ok_paper_draft,
    )
)
_reg(
    EndpointHit(
        "POST",
        "/api/paper/drafts/{draft_id}/execute",
        path_params={"draft_id": "nonexistent-draft"},
        params={"now": "2026-09-07T09:40:00+08:00"},
        expect_status=frozenset({200, 400, 404}),
        needs_paper_draft=True,
    )
)
_reg(EndpointHit("GET", "/api/broker/status", assert_body=_ok_broker))

# research
_reg(EndpointHit("GET", "/api/research/defaults", assert_body=_ok_defaults))
_reg(
    EndpointHit(
        "GET",
        "/api/research/brief",
        params={
            "asof": "2026-09-02",
            "symbols": "600519,000001",
            "topN": 3,
            "adjust_kind": "none",
            "persist": "false",
        },
        assert_body=_ok_brief,
    )
)
_reg(EndpointHit("GET", "/api/research/briefs", params={"limit": 10}, assert_body=_ok_briefs_list))
_reg(
    EndpointHit(
        "POST",
        "/api/research/briefs",
        json={
            "asof": "2026-09-02",
            "picks": [{"symbol": "600519", "rating": "Hold"}],
            "environment": "SIMULATE",
            "symbols": "600519",
        },
        assert_body=_ok_brief_save,
    )
)
_reg(
    EndpointHit(
        "GET",
        "/api/research/briefs/{asof}",
        path_params={"asof": "2026-09-02"},
        expect_status=frozenset({200, 404}),
        needs_brief=True,
        assert_body=_ok_brief_get,
    )
)
_reg(
    EndpointHit(
        "GET",
        "/api/research/briefs/{asof}/review",
        path_params={"asof": "2026-09-02"},
        params={"holding": "1d"},
        expect_status=frozenset({200, 404}),
        needs_brief=True,
        assert_body=_ok_live_off,
    )
)
_reg(
    EndpointHit(
        "POST",
        "/api/research/brief/to-paper",
        json={
            "asof": "2026-09-02",
            "symbols": "600519",
            "topN": 1,
            "adjust_kind": "none",
            "decision_only": True,
            "now": "2026-09-07T09:40:00+08:00",
        },
        assert_body=_ok_paper_draft,
    )
)
_reg(
    EndpointHit(
        "POST",
        "/api/research/brief/to-broker",
        json={
            "asof": "2026-09-02",
            "symbols": "600519",
            "topN": 1,
            "adjust_kind": "none",
            "decision_only": True,
            "now": "2026-09-07T09:40:00+08:00",
        },
        assert_body=_ok_paper_draft,
    )
)
_reg(
    EndpointHit(
        "POST",
        "/api/research/wizard/daily",
        json={
            "asof": "2026-09-02",
            "symbols": "600519",
            "topN": 1,
            "adjust_kind": "none",
            "skipRefresh": True,
            "toPaper": False,
        },
        assert_body=_ok_wizard,
    )
)
_reg(EndpointHit("GET", "/api/research/performance", assert_body=_ok_performance))
_reg(
    EndpointHit(
        "POST",
        "/api/research/performance/settle",
        expect_status=frozenset({200, 404, 503}),
        assert_body=_ok_live_off,
    )
)
_reg(
    EndpointHit(
        "POST",
        "/api/research/performance/log-brief",
        json={
            "asof": "2026-09-02",
            "symbols": "600519",
            "topN": 1,
            "adjust_kind": "none",
            "holding": "5d",
        },
        assert_body=_ok_log_brief,
    )
)
_reg(
    EndpointHit(
        "POST",
        "/api/research/brief/debate",
        json={
            "asof": "2026-09-02",
            "symbols": "600519",
            "topN": 1,
            "adjust_kind": "none",
            "engine": "deterministic",
        },
        assert_body=_ok_log_brief,
    )
)
_reg(EndpointHit("GET", "/api/research/strategy/configs", assert_body=_ok_strategy_configs))
_reg(EndpointHit("GET", "/api/research/strategy/ab-status", assert_body=_ok_ab_status))
_reg(
    EndpointHit(
        "POST",
        "/api/research/strategy/compare",
        json={"configA": "lvrev-default-v1", "configB": "lvrev-rev-heavy-v1"},
        assert_body=_ok_compare,
    )
)
_reg(
    EndpointHit(
        "POST",
        "/api/research/backtest/rolling-review",
        # Explicit symbols stay within replay fixtures (broad tiers may 500 on missing files).
        json={
            "lastN": 3,
            "universeTier": "core",
            "symbols": "600519,000001",
            "topN": 2,
            "holding": "1d",
        },
        expect_status=frozenset({200, 503}),
        assert_body=_ok_rolling,
    )
)
_reg(
    EndpointHit(
        "POST",
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
        assert_body=_ok_walk_forward,
    )
)
_reg(
    EndpointHit(
        "POST",
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
        assert_body=_ok_factor_ic,
    )
)
_reg(
    EndpointHit(
        "GET",
        "/api/research/pit/fundamentals",
        params={"symbols": "600519", "asof": "2026-06-01"},
        expect_status=frozenset({200, 503}),
        assert_body=_ok_pit,
    )
)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("STOCK_PLATFORM_PROVIDER_PRESET", "replay")
    db_path = tmp_path / "all_api.db"
    monkeypatch.setenv("STOCK_PLATFORM_DB_URL", f"sqlite:///{db_path.as_posix()}")
    perf_log = tmp_path / "recommend_decisions.jsonl"
    monkeypatch.setenv("STOCK_PLATFORM_PERFORMANCE_LOG", str(perf_log))
    from stock_platform_research import SqliteBriefRepository, reset_brief_repository_cache

    reset_brief_repository_cache()
    state = build_default_state(FIXTURES)
    state.brief_repo = SqliteBriefRepository(db_path)
    return TestClient(create_app(state=state))


@pytest.fixture()
def openapi_ops(client: TestClient) -> list[tuple[str, str]]:
    spec = client.app.openapi()
    ops: list[tuple[str, str]] = []
    for path, item in spec["paths"].items():
        for method in item:
            if method in {"get", "post", "put", "patch", "delete"}:
                ops.append((method.upper(), path))
    return sorted(ops)


def _format_path(template: str, path_params: Mapping[str, str]) -> str:
    out = template
    for key, value in path_params.items():
        out = out.replace("{" + key + "}", value)
    assert "{" not in out, f"unresolved path params in {out!r}"
    return out


def _prep(client: TestClient, hit: EndpointHit) -> dict[str, str]:
    overrides: dict[str, str] = dict(hit.path_params)
    if hit.needs_brief:
        r = client.get(
            "/api/research/brief",
            params={
                "asof": "2026-09-02",
                "symbols": "600519",
                "topN": 1,
                "adjust_kind": "none",
            },
        )
        assert r.status_code == 200, r.text
    if hit.needs_paper_draft:
        ensured = client.post("/api/paper/strategies/ensure-default")
        assert ensured.status_code == 200, ensured.text
        created = client.post(
            "/api/paper/drafts",
            json={
                "signal_trade_date": "2026-09-04",
                "orders": [{"symbol": "510300", "side": "buy", "qty": 100}],
                "decision_only": True,
                "now": "2026-09-07T09:40:00+08:00",
            },
        )
        assert created.status_code == 200, created.text
        draft_id = created.json().get("draftId")
        if draft_id:
            overrides["draft_id"] = str(draft_id)
    return overrides


@pytest.mark.unit
def test_openapi_catalog_covers_every_operation(openapi_ops: list[tuple[str, str]]) -> None:
    """Coverage gate: catalog keys == OpenAPI operations (no silent gaps)."""
    catalog = set(ENDPOINT_HITS)
    openapi = set(openapi_ops)
    missing = sorted(openapi - catalog)
    extra = sorted(catalog - openapi)
    assert not missing, f"OpenAPI ops without EndpointHit: {missing}"
    assert not extra, f"EndpointHit for unknown OpenAPI ops: {extra}"
    assert len(openapi_ops) == len(ENDPOINT_HITS) == 56


@pytest.mark.unit
@pytest.mark.parametrize(
    "method,path",
    sorted(ENDPOINT_HITS.keys()),
    ids=[f"{m} {p}" for m, p in sorted(ENDPOINT_HITS.keys())],
)
def test_each_openapi_endpoint_hit(client: TestClient, method: str, path: str) -> None:
    hit = ENDPOINT_HITS[(method, path)]
    path_params = _prep(client, hit)
    url = _format_path(hit.path, path_params)
    kwargs: dict[str, Any] = {}
    if hit.params is not None:
        kwargs["params"] = dict(hit.params)
    if hit.json is not None:
        kwargs["json"] = dict(hit.json)
    response = client.request(method, url, **kwargs)
    assert response.status_code in hit.expect_status, (
        f"{method} {url} -> {response.status_code}, body={response.text[:500]}"
    )
    try:
        body: Any = response.json()
    except Exception:
        body = response.text
    if hit.assert_body is not None:
        hit.assert_body(body, response.status_code)


@pytest.mark.unit
@pytest.mark.parametrize("method,path", EXTRA_META_PATHS, ids=[f"{m} {p}" for m, p in EXTRA_META_PATHS])
def test_docs_and_openapi_json(client: TestClient, method: str, path: str) -> None:
    r = client.request(method, path)
    assert r.status_code == 200
    if path == "/openapi.json":
        body = r.json()
        assert "paths" in body
        assert body["info"]["title"] == "stock-platform workbench"


@pytest.mark.unit
def test_coverage_report_counts(openapi_ops: list[tuple[str, str]]) -> None:
    """Human-readable coverage numbers for CI logs / release notes."""
    n_ops = len(openapi_ops)
    n_hits = len(ENDPOINT_HITS)
    n_extra = len(EXTRA_META_PATHS)
    assert n_ops == n_hits
    assert n_ops + n_extra == 59
