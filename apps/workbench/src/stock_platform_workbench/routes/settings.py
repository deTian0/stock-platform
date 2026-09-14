"""Settings — capability matrix is the routing authority."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from stock_platform_providers import (
    DEFAULT_STARTUP_PRESET,
    get_preference_preset,
    list_preference_presets,
    resolve_startup_preset_id,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/capability-matrix")
def capability_matrix(request: Request) -> list[dict[str, Any]]:
    state = request.app.state.workbench
    return state.matrix()


class PreferencesUpdate(BaseModel):
    """Partial preference map: capability id → provider name."""

    preferences: dict[str, str] = Field(default_factory=dict)


@router.get("/preferences")
def get_preferences(request: Request) -> dict[str, Any]:
    state = request.app.state.workbench
    return {"preferences": state.preferences}


@router.put("/preferences")
def put_preferences(request: Request, body: PreferencesUpdate) -> dict[str, Any]:
    """Update routing preferences; matrix remains the only authority for usable."""
    state = request.app.state.workbench
    state.preferences.update(body.preferences)
    return {"preferences": state.preferences, "matrix": state.matrix()}


@router.get("/presets")
def get_presets() -> dict[str, Any]:
    """Documented preference templates. Startup default is CN live (env can force replay)."""
    try:
        startup = resolve_startup_preset_id()
    except KeyError:
        startup = DEFAULT_STARTUP_PRESET
    return {
        "default": DEFAULT_STARTUP_PRESET,
        "startup": startup,
        "presets": list_preference_presets(),
    }


@router.post("/presets/{preset_id}/apply")
def apply_preset(request: Request, preset_id: str) -> dict[str, Any]:
    try:
        preset = get_preference_preset(preset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"reason": str(exc)}) from exc
    state = request.app.state.workbench
    state.preferences.update(dict(preset["preferences"]))
    return {
        "applied": preset["id"],
        "isDefault": bool(preset.get("is_default")),
        "preferences": state.preferences,
        "matrix": state.matrix(),
        "note": (
            f"Process preferences updated. Production startup default is "
            f"{DEFAULT_STARTUP_PRESET}; set STOCK_PLATFORM_PROVIDER_PRESET=replay for CI."
        ),
        "liveTradingEnabled": False,
    }
