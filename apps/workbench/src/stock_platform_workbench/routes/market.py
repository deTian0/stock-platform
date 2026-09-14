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
    freq: str = Query("1m", description="1m/5m/15m/30m/60m"),
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(0, ge=0, le=100000),
) -> dict[str, Any]:
    state = request.app.state.workbench
    provider = state.resolve("minute")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    getter = getattr(provider, "get_minute", None)
    if getter is None:
        return {
            "capability": "minute",
            "provider": getattr(provider, "name", type(provider).__name__),
            "rows": [],
            "reason": "provider_missing_get_minute",
        }
    rows = getter(syms, freq=freq, start=start, end=end, limit=limit)
    return {
        "capability": "minute",
        "provider": getattr(provider, "name", type(provider).__name__),
        "freq": freq,
        "rows": rows,
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


@router.get("/unlock")
def get_unlock(
    request: Request,
    symbols: str = Query(..., description="Comma-separated tickers"),
    asof_date: date = Query(..., description="Forward window start date YYYY-MM-DD"),
    forward_days: int = Query(90, ge=1, le=365),
) -> dict[str, Any]:
    state = request.app.state.workbench
    provider = state.resolve("unlock")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    getter = getattr(provider, "get_unlock", None)
    if getter is None:
        return {
            "capability": "unlock",
            "provider": getattr(provider, "name", type(provider).__name__),
            "items": [],
            "reason": "provider_missing_get_unlock",
        }
    items = getter(syms, asof_date=asof_date, forward_days=forward_days)
    return {
        "capability": "unlock",
        "provider": getattr(provider, "name", type(provider).__name__),
        "items": items,
    }


@router.get("/depth5")
def get_depth5(
    request: Request,
    symbols: str = Query(..., description="Comma-separated tickers"),
) -> dict[str, Any]:
    state = request.app.state.workbench
    provider = state.resolve("depth5")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    getter = getattr(provider, "get_depth5", None)
    if getter is None:
        return {
            "capability": "depth5",
            "provider": getattr(provider, "name", type(provider).__name__),
            "rows": [],
            "reason": "provider_missing_get_depth5",
        }
    rows = getter(syms)
    return {
        "capability": "depth5",
        "provider": getattr(provider, "name", type(provider).__name__),
        "rows": rows,
    }


@router.get("/financial")
def get_financial(
    request: Request,
    symbols: str = Query(..., description="Comma-separated tickers"),
    periods: int = Query(8, ge=1, le=40, description="Number of report periods"),
) -> dict[str, Any]:
    state = request.app.state.workbench
    provider = state.resolve("financial")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    getter = getattr(provider, "get_financial", None)
    if getter is None:
        return {
            "capability": "financial",
            "provider": getattr(provider, "name", type(provider).__name__),
            "items": [],
            "reason": "provider_missing_get_financial",
        }
    items = getter(syms, periods=periods)
    return {
        "capability": "financial",
        "provider": getattr(provider, "name", type(provider).__name__),
        "items": items,
    }


@router.get("/adj-factor")
def get_adj_factor(
    request: Request,
    symbols: str = Query(..., description="Comma-separated tickers"),
    kind: str = Query("qfq", description="qfq (forward) or hfq (backward)"),
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(0, ge=0, le=10000),
) -> dict[str, Any]:
    state = request.app.state.workbench
    provider = state.resolve("adj_factor")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    getter = getattr(provider, "get_adj_factor", None)
    if getter is None:
        return {
            "capability": "adj_factor",
            "provider": getattr(provider, "name", type(provider).__name__),
            "rows": [],
            "reason": "provider_missing_get_adj_factor",
        }
    rows = getter(syms, kind=kind, start=start, end=end, limit=limit)
    return {
        "capability": "adj_factor",
        "provider": getattr(provider, "name", type(provider).__name__),
        "kind": kind,
        "rows": rows,
    }


@router.get("/full-minute")
def get_full_minute(
    request: Request,
    symbols: str = Query(..., description="Comma-separated tickers"),
    trade_date: date | None = Query(
        None, description="Session day YYYY-MM-DD; default provider today (CN)"
    ),
    count: int = Query(300, ge=0, le=1000, description="Max 1m bars per symbol"),
) -> dict[str, Any]:
    """Same-day 1m batch (full_minute) — distinct from multi-freq /minute."""
    state = request.app.state.workbench
    provider = state.resolve("full_minute")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    getter = getattr(provider, "get_full_minute", None)
    if getter is None:
        return {
            "capability": "full_minute",
            "provider": getattr(provider, "name", type(provider).__name__),
            "rows": [],
            "reason": "provider_missing_get_full_minute",
        }
    rows = getter(syms, trade_date=trade_date, count=count)
    return {
        "capability": "full_minute",
        "provider": getattr(provider, "name", type(provider).__name__),
        "trade_date": trade_date.isoformat() if trade_date else None,
        "count": count,
        "rows": rows,
    }
