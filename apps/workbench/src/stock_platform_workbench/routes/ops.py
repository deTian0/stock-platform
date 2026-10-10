"""Ops health — liveness plus throttle/refresh snapshot (no public net)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from stock_platform_providers.eastmoney import get_default_client
from stock_platform_providers.engine_sqlite import (
    EngineSqliteProvider,
    resolve_engine_market_db,
)
from stock_platform_workbench import __version__
from stock_platform_workbench.brief_ux import ops_data_visibility
from stock_platform_workbench.openapi_models import OpsHealthResponse, RESP_503, ok200

router = APIRouter(prefix="/api/ops", tags=["ops"])

ENV_REFRESH_DIR = "STOCK_PLATFORM_REFRESH_DIR"

# Coverage verdicts that should degrade ops health (C2 guard, read-only).
_DEGRADED_COVERAGE = {"stale", "thin", "empty", "missing_table", "error"}


def _market_db_snapshot() -> dict[str, Any]:
    """Read-only market.db coverage snapshot (never raises; ADR 0050 keeps it ro)."""
    if resolve_engine_market_db() is None:
        return {
            "configured": False,
            "status": "unconfigured",
            "message": "未配置 STOCK_PLATFORM_ENGINE_MARKET_DB；日线/回测/PIT 将 fail-closed。",
        }
    try:
        snap = EngineSqliteProvider().coverage_snapshot()
    except Exception as exc:  # ops health must never 500 on a bad warehouse
        return {"configured": True, "status": "error", "message": str(exc)[:200]}
    snap["configured"] = True
    return snap


def _load_last_refresh() -> dict[str, Any] | None:
    raw = os.environ.get(ENV_REFRESH_DIR, "").strip()
    if not raw:
        return None
    latest = Path(raw) / "latest.json"
    if not latest.is_file():
        return None
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "error": "latest.json unreadable"}
    if not isinstance(data, dict):
        return {"ok": False, "error": "latest.json not an object"}
    return {
        "ok": bool(data.get("ok")),
        "asof": data.get("asof"),
        "failCount": data.get("failCount"),
        "outDir": data.get("outDir"),
    }


@router.get(
    "/health",
    summary="运维健康快照",
    response_model=OpsHealthResponse,
    responses={**ok200(OpsHealthResponse, "Prefs + EM circuit + optional last refresh"), **RESP_503},
)
def ops_health(request: Request) -> dict[str, Any]:
    """Deeper than GET /health: prefs + EM circuit + optional last refresh."""
    state = request.app.state.workbench
    prefs = dict(state.preferences)
    default_replay = all(v == "replay" for v in prefs.values()) if prefs else True
    last_refresh = _load_last_refresh()
    em = get_default_client().snapshot()
    market_db = _market_db_snapshot()
    status = "ok"
    if em.get("circuitOpen"):
        status = "degraded"
    if last_refresh is not None and last_refresh.get("ok") is False:
        status = "degraded"
    if market_db.get("status") in _DEGRADED_COVERAGE:
        status = "degraded"
    visibility = ops_data_visibility()
    return {
        "status": status,
        "service": "workbench",
        "version": __version__,
        "liveTradingEnabled": False,
        "executionMode": "SIMULATE",
        "defaultReplay": default_replay,
        "providerPreset": visibility["providerPreset"],
        "briefFallback": visibility["briefFallback"],
        "supplementTokenConfigured": visibility["supplementTokenConfigured"],
        "preferences": prefs,
        "eastmoney": em,
        "marketDb": market_db,
        "lastRefresh": last_refresh,
    }
