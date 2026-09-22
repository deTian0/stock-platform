"""OpenAPI contract tests — non-empty schemas for key workbench routes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stock_platform_workbench.app import create_app
from stock_platform_workbench.state import build_default_state

FIXTURES = Path(__file__).parent / "fixtures"

# Paths that must appear in openapi.json (method → path).
REQUIRED_PATHS: dict[str, set[str]] = {
    "get": {
        "/health",
        "/version",
        "/api/ops/health",
        "/api/settings/capability-matrix",
        "/api/settings/preferences",
        "/api/settings/presets",
        "/api/market/daily",
        "/api/market/realtime",
        "/api/market/concept-blocks",
        "/api/market/fund-flow",
        "/api/paper/status",
        "/api/broker/status",
        "/api/research/brief",
        "/api/research/briefs",
        "/api/research/performance",
        "/api/research/defaults",
        "/api/research/report",
        "/api/review/report",
        "/api/debate/report",
    },
    "post": {
        "/api/paper/strategies/ensure-default",
        "/api/paper/drafts",
        "/api/research/brief/to-paper",
        "/api/research/wizard/daily",
        "/api/research/backtest/walk-forward",
        "/api/research/backtest/factor-ic",
        "/api/research/strategy/compare",
        "/api/settings/presets/{preset_id}/apply",
    },
    "put": {
        "/api/settings/preferences",
    },
}

# Stable OpenAPI snapshot fragment (title / paths presence flags).
SNAPSHOT_KEYS = ("openapi", "info", "paths", "components")


def _schema_nonempty(schema: dict | None) -> bool:
    """True if schema has $ref, properties, items, or is a non-empty typed object/array."""
    if not schema or not isinstance(schema, dict):
        return False
    if "$ref" in schema:
        return True
    if schema.get("properties"):
        return True
    if "items" in schema:
        return _schema_nonempty(schema["items"]) if isinstance(schema["items"], dict) else True
    if schema.get("anyOf") or schema.get("oneOf") or schema.get("allOf"):
        return True
    # Bare object with only additionalProperties:true is considered empty for our contract.
    if schema.get("type") == "object":
        props = schema.get("properties") or {}
        add = schema.get("additionalProperties")
        if props:
            return True
        if add is True or add == {}:
            return False
        if isinstance(add, dict) and (_schema_nonempty(add) or add.get("type")):
            # still "empty envelope" if no named properties
            return False
        return bool(schema.get("required"))
    if schema.get("type") in {"string", "integer", "number", "boolean", "array"}:
        return True
    return False


def _resolve_ref(spec: dict, ref: str) -> dict:
    assert ref.startswith("#/")
    node: object = spec
    for part in ref[2:].split("/"):
        assert isinstance(node, dict)
        node = node[part]
    assert isinstance(node, dict)
    return node


def _response_schema(spec: dict, path: str, method: str, status: str = "200") -> dict | None:
    op = spec["paths"][path][method]
    resp = op.get("responses", {}).get(status) or op.get("responses", {}).get(int(status))
    if not resp:
        return None
    content = resp.get("content") or {}
    app_json = content.get("application/json") or {}
    schema = app_json.get("schema")
    if not schema:
        return None
    if "$ref" in schema:
        return _resolve_ref(spec, schema["$ref"])
    return schema


@pytest.fixture()
def openapi_spec(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict:
    monkeypatch.setenv("STOCK_PLATFORM_PROVIDER_PRESET", "replay")
    monkeypatch.setenv("STOCK_PLATFORM_DB_URL", f"sqlite:///{(tmp_path / 'oa.db').as_posix()}")
    from stock_platform_research import reset_brief_repository_cache

    reset_brief_repository_cache()
    app = create_app(state=build_default_state(FIXTURES))
    return app.openapi()


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("STOCK_PLATFORM_PROVIDER_PRESET", "replay")
    monkeypatch.setenv("STOCK_PLATFORM_DB_URL", f"sqlite:///{(tmp_path / 'oa.db').as_posix()}")
    from stock_platform_research import reset_brief_repository_cache

    reset_brief_repository_cache()
    return TestClient(create_app(state=build_default_state(FIXTURES)))


@pytest.mark.unit
def test_openapi_json_endpoint(client: TestClient) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    body = r.json()
    assert body["info"]["title"] == "stock-platform workbench"
    assert "paths" in body
    docs = client.get("/docs")
    assert docs.status_code == 200
    redoc = client.get("/redoc")
    assert redoc.status_code == 200


@pytest.mark.unit
def test_openapi_required_paths(openapi_spec: dict) -> None:
    paths = openapi_spec["paths"]
    missing: list[str] = []
    for method, path_set in REQUIRED_PATHS.items():
        for path in path_set:
            if path not in paths or method not in paths[path]:
                missing.append(f"{method.upper()} {path}")
    assert not missing, f"missing OpenAPI paths: {missing}"


@pytest.mark.unit
def test_openapi_get_post_200_schemas_nonempty(openapi_spec: dict) -> None:
    """GET/POST 200 responses must not be bare empty objects."""
    weak: list[str] = []
    for method, path_set in REQUIRED_PATHS.items():
        if method not in {"get", "post", "put"}:
            continue
        for path in path_set:
            schema = _response_schema(openapi_spec, path, method, "200")
            if not _schema_nonempty(schema):
                weak.append(f"{method.upper()} {path}")
    assert not weak, f"empty/weak 200 schemas: {weak}"


@pytest.mark.unit
def test_openapi_error_responses_declared(openapi_spec: dict) -> None:
    """Key routes declare common error status codes used by handlers."""
    daily = openapi_spec["paths"]["/api/market/daily"]["get"]["responses"]
    assert "409" in daily or 409 in daily
    brief = openapi_spec["paths"]["/api/research/brief"]["get"]["responses"]
    assert "400" in brief or 400 in brief
    walk = openapi_spec["paths"]["/api/research/backtest/walk-forward"]["post"]["responses"]
    assert "400" in walk or 400 in walk


@pytest.mark.unit
def test_openapi_snapshot_fragment(openapi_spec: dict) -> None:
    for key in SNAPSHOT_KEYS:
        assert key in openapi_spec
    assert openapi_spec["info"]["title"] == "stock-platform workbench"
    assert "SIMULATE" in (openapi_spec["info"].get("description") or "")
    # components.schemas should include documented envelopes
    schemas = openapi_spec.get("components", {}).get("schemas", {})
    for name in ("HealthResponse", "OpsHealthResponse", "MarketRowsResponse", "BriefResponse"):
        assert name in schemas, f"missing schema {name}"
        assert _schema_nonempty(schemas[name])
