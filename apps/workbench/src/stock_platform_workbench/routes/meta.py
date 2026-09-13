"""Health / version."""

from __future__ import annotations

from fastapi import APIRouter

from stock_platform_workbench import __version__

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "workbench", "version": __version__}


@router.get("/version")
def version() -> dict:
    return {"version": __version__}
