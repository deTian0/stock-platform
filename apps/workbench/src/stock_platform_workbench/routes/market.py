"""Market data routes — resolve provider only via capability matrix."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/daily")
def get_daily(
    request: Request,
    symbols: str = Query(..., description="Comma-separated tickers"),
    start: date | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    state = request.app.state.workbench
    provider = state.resolve("daily")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    rows = provider.get_daily(syms, start=start, end=end)
    return {
        "capability": "daily",
        "provider": getattr(provider, "name", type(provider).__name__),
        "rows": rows,
    }


@router.get("/realtime")
def get_realtime(
    request: Request,
    symbols: str = Query(..., description="Comma-separated tickers"),
) -> dict[str, Any]:
    state = request.app.state.workbench
    provider = state.resolve("realtime")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    rows = provider.get_realtime(syms)
    return {
        "capability": "realtime",
        "provider": getattr(provider, "name", type(provider).__name__),
        "rows": rows,
    }


@router.get("/minute")
def get_minute(
    request: Request,
    symbols: str = Query(..., description="Comma-separated tickers"),
) -> dict[str, Any]:
    """Intentionally fail-closed until a minute-capable provider is registered."""
    state = request.app.state.workbench
    provider = state.resolve("minute")
    # Unreachable with default wiring; kept for future providers.
    return {
        "capability": "minute",
        "provider": getattr(provider, "name", type(provider).__name__),
        "rows": [],
        "symbols": [s.strip() for s in symbols.split(",") if s.strip()],
    }
