"""Settings — capability matrix is the routing authority."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/capability-matrix")
def capability_matrix(request: Request) -> list[dict[str, Any]]:
    state = request.app.state.workbench
    return state.matrix()


class PreferencesUpdate(BaseModel):
    """Partial preference map: capability id → provider name."""

    preferences: dict[str, str] = Field(default_factory=dict)


@router.put("/preferences")
def put_preferences(request: Request, body: PreferencesUpdate) -> dict[str, Any]:
    """Update routing preferences; matrix remains the only authority for usable."""
    state = request.app.state.workbench
    state.preferences.update(body.preferences)
    return {"preferences": state.preferences, "matrix": state.matrix()}
