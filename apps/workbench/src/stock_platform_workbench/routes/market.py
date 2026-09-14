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


@router.get("/fund-flow")
def get_fund_flow(
    request: Request,
    symbols: str = Query(..., description="Comma-separated tickers"),
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(120, ge=1, le=1000),
) -> dict[str, Any]:
    state = request.app.state.workbench
    provider = state.resolve("fund_flow")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    getter = getattr(provider, "get_fund_flow", None)
    if getter is None:
        return {
            "capability": "fund_flow",
            "provider": getattr(provider, "name", type(provider).__name__),
            "rows": [],
            "reason": "provider_missing_get_fund_flow",
        }
    rows = getter(syms, start=start, end=end, limit=limit)
    return {
        "capability": "fund_flow",
        "provider": getattr(provider, "name", type(provider).__name__),
        "rows": rows,
    }


@router.get("/lhb")
def get_lhb(
    request: Request,
    symbols: str = Query(..., description="Comma-separated tickers"),
    asof_date: date = Query(..., description="Look-back end date YYYY-MM-DD"),
    look_back_days: int = Query(30, ge=1, le=365),
) -> dict[str, Any]:
    state = request.app.state.workbench
    provider = state.resolve("lhb")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    getter = getattr(provider, "get_lhb", None)
    if getter is None:
        return {
            "capability": "lhb",
            "provider": getattr(provider, "name", type(provider).__name__),
            "items": [],
            "reason": "provider_missing_get_lhb",
        }
    items = getter(syms, asof_date=asof_date, look_back_days=look_back_days)
    return {
        "capability": "lhb",
        "provider": getattr(provider, "name", type(provider).__name__),
        "items": items,
    }
