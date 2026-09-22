"""Health / version."""

from __future__ import annotations

from fastapi import APIRouter

from stock_platform_workbench import __version__
from stock_platform_workbench.openapi_models import HealthResponse, VersionResponse

router = APIRouter(tags=["meta"])


@router.get(
    "/health",
    summary="存活探针",
    response_model=HealthResponse,
    responses={200: {"description": "Process is up"}},
)
def health() -> dict:
    """Liveness probe — does not check providers or Eastmoney circuit."""
    return {"status": "ok", "service": "workbench", "version": __version__}


@router.get(
    "/version",
    summary="版本号",
    response_model=VersionResponse,
)
def version() -> dict:
    """Workbench package version (aligned with root VERSION)."""
    return {"version": __version__}
