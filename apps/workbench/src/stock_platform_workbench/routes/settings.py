"""Settings — capability matrix is the routing authority."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/capability-matrix")
def capability_matrix(request: Request) -> list[dict[str, Any]]:
    state = request.app.state.workbench
    return state.matrix()
