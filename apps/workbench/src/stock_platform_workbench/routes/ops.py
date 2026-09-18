"""Ops health — liveness plus throttle/refresh snapshot (no public net)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from stock_platform_providers.eastmoney import get_default_client
from stock_platform_workbench import __version__
from stock_platform_workbench.brief_ux import ops_data_visibility

router = APIRouter(prefix="/api/ops", tags=["ops"])

ENV_REFRESH_DIR = "STOCK_PLATFORM_REFRESH_DIR"


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


@router.get("/health")
def ops_health(request: Request) -> dict[str, Any]:
    """Deeper than GET /health: prefs + EM circuit + optional last refresh."""
    state = request.app.state.workbench
    prefs = dict(state.preferences)
    default_replay = all(v == "replay" for v in prefs.values()) if prefs else True
    last_refresh = _load_last_refresh()
    em = get_default_client().snapshot()
    status = "ok"
    if em.get("circuitOpen"):
        status = "degraded"
    if last_refresh is not None and last_refresh.get("ok") is False:
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
        "lastRefresh": last_refresh,
    }
