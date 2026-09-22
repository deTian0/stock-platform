"""Market data routes — resolve provider only via capability matrix."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from stock_platform_providers import apply_adjust

from stock_platform_workbench.openapi_models import (
    RESP_PROVIDER,
    MarketAdjFactorResponse,
    MarketDailyAdjustedResponse,
    MarketFullMinuteResponse,
    MarketItemsResponse,
    MarketMinuteResponse,
    MarketRowsResponse,
    ok200,
)

router = APIRouter(prefix="/api/market", tags=["market"])

_Q_SYMBOLS = Query(..., description="逗号分隔标的代码，如 600519,000001")
_Q_START = Query(None, description="起始日期 YYYY-MM-DD（含）")
_Q_END = Query(None, description="结束日期 YYYY-MM-DD（含）")


def _require_getter(provider: Any, method: str, capability: str) -> Any:
    """Fail-closed when the effective provider lacks the dataset method (no fake empty)."""
    getter = getattr(provider, method, None)
    if getter is None:
        raise HTTPException(
            status_code=501,
            detail={
                "reason": f"provider_missing_{method}",
                "capability": capability,
                "provider": getattr(provider, "name", type(provider).__name__),
                "liveTradingEnabled": False,
            },
        )
    return getter


@router.get(
    "/daily",
    summary="日 K（未复权）",
    responses={**ok200(MarketRowsResponse), **RESP_PROVIDER},
)
def get_daily(
    request: Request,
    symbols: str = _Q_SYMBOLS,
    start: date | None = _Q_START,
    end: date | None = _Q_END,
) -> dict[str, Any]:
    """经矩阵 resolve(`daily`) 取 OHLCV；缺能力 409。"""
    state = request.app.state.workbench
    provider = state.resolve("daily")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    rows = provider.get_daily(syms, start=start, end=end)
    return {
        "capability": "daily",
        "provider": getattr(provider, "name", type(provider).__name__),
        "rows": rows,
    }


@router.get(
    "/realtime",
    summary="实时行情快照",
    responses={**ok200(MarketRowsResponse), **RESP_PROVIDER},
)
def get_realtime(
    request: Request,
    symbols: str = _Q_SYMBOLS,
) -> dict[str, Any]:
    """经矩阵 resolve(`realtime`)。"""
    state = request.app.state.workbench
    provider = state.resolve("realtime")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    rows = provider.get_realtime(syms)
    return {
        "capability": "realtime",
        "provider": getattr(provider, "name", type(provider).__name__),
        "rows": rows,
    }


@router.get(
    "/minute",
    summary="分钟 K",
    responses={**ok200(MarketMinuteResponse), **RESP_PROVIDER},
)
def get_minute(
    request: Request,
    symbols: str = _Q_SYMBOLS,
    freq: str = Query("1m", description="1m/5m/15m/30m/60m"),
    start: date | None = _Q_START,
    end: date | None = _Q_END,
    limit: int = Query(0, ge=0, le=100000, description="最大返回条数；0 表示不截断"),
) -> dict[str, Any]:
    """经矩阵 resolve(`minute`)；无候选仍 409。"""
    state = request.app.state.workbench
    provider = state.resolve("minute")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    getter = _require_getter(provider, "get_minute", "minute")
    rows = getter(syms, freq=freq, start=start, end=end, limit=limit)
    return {
        "capability": "minute",
        "provider": getattr(provider, "name", type(provider).__name__),
        "freq": freq,
        "rows": rows,
    }


@router.get(
    "/fund-flow",
    summary="个股资金流",
    responses={**ok200(MarketRowsResponse), **RESP_PROVIDER},
)
def get_fund_flow(
    request: Request,
    symbols: str = _Q_SYMBOLS,
    start: date | None = _Q_START,
    end: date | None = _Q_END,
    limit: int = Query(120, ge=1, le=1000, description="最大返回条数"),
) -> dict[str, Any]:
    """经矩阵 resolve(`fund_flow`)。"""
    state = request.app.state.workbench
    provider = state.resolve("fund_flow")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    getter = _require_getter(provider, "get_fund_flow", "fund_flow")
    rows = getter(syms, start=start, end=end, limit=limit)
    return {
        "capability": "fund_flow",
        "provider": getattr(provider, "name", type(provider).__name__),
        "rows": rows,
    }


@router.get(
    "/sector-fund-flow",
    summary="板块资金流",
    responses={**ok200(MarketRowsResponse), **RESP_PROVIDER},
)
def get_sector_fund_flow(
    request: Request,
    sectors: str = Query(..., description="逗号分隔板块代码，如 BK0477"),
    start: date | None = _Q_START,
    end: date | None = _Q_END,
    limit: int = Query(60, ge=1, le=1000, description="最大返回条数"),
) -> dict[str, Any]:
    """经矩阵 resolve(`sector_fund_flow`)。"""
    state = request.app.state.workbench
    provider = state.resolve("sector_fund_flow")
    codes = [s.strip() for s in sectors.split(",") if s.strip()]
    getter = _require_getter(provider, "get_sector_fund_flow", "sector_fund_flow")
    rows = getter(codes, start=start, end=end, limit=limit)
    return {
        "capability": "sector_fund_flow",
        "provider": getattr(provider, "name", type(provider).__name__),
        "rows": rows,
    }


@router.get(
    "/news",
    summary="个股/板块新闻",
    responses={**ok200(MarketRowsResponse), **RESP_PROVIDER},
)
def get_news(
    request: Request,
    symbols: str = _Q_SYMBOLS,
    start: date | None = _Q_START,
    end: date | None = _Q_END,
    limit: int = Query(20, ge=1, le=100, description="最大返回条数"),
) -> dict[str, Any]:
    """经矩阵 resolve(`news`)。"""
    state = request.app.state.workbench
    provider = state.resolve("news")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    getter = _require_getter(provider, "get_news", "news")
    rows = getter(syms, start=start, end=end, limit=limit)
    return {
        "capability": "news",
        "provider": getattr(provider, "name", type(provider).__name__),
        "rows": rows,
    }


@router.get(
    "/concept-blocks",
    summary="概念板块归属",
    responses={**ok200(MarketItemsResponse), **RESP_PROVIDER},
)
def get_concept_blocks(
    request: Request,
    symbols: str = _Q_SYMBOLS,
) -> dict[str, Any]:
    """经矩阵 resolve(`concept_blocks`)。"""
    state = request.app.state.workbench
    provider = state.resolve("concept_blocks")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    getter = _require_getter(provider, "get_concept_blocks", "concept_blocks")
    items = getter(syms)
    return {
        "capability": "concept_blocks",
        "provider": getattr(provider, "name", type(provider).__name__),
        "items": items,
    }


@router.get(
    "/lhb",
    summary="龙虎榜",
    responses={**ok200(MarketItemsResponse), **RESP_PROVIDER},
)
def get_lhb(
    request: Request,
    symbols: str = _Q_SYMBOLS,
    asof_date: date = Query(..., description="回看截止日 YYYY-MM-DD"),
    look_back_days: int = Query(30, ge=1, le=365, description="回看自然日天数"),
) -> dict[str, Any]:
    """经矩阵 resolve(`lhb`)。"""
    state = request.app.state.workbench
    provider = state.resolve("lhb")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    getter = _require_getter(provider, "get_lhb", "lhb")
    items = getter(syms, asof_date=asof_date, look_back_days=look_back_days)
    return {
        "capability": "lhb",
        "provider": getattr(provider, "name", type(provider).__name__),
        "items": items,
    }


@router.get(
    "/unlock",
    summary="限售解禁",
    responses={**ok200(MarketItemsResponse), **RESP_PROVIDER},
)
def get_unlock(
    request: Request,
    symbols: str = _Q_SYMBOLS,
    asof_date: date = Query(..., description="前瞻窗口起始日 YYYY-MM-DD"),
    forward_days: int = Query(90, ge=1, le=365, description="前瞻自然日天数"),
) -> dict[str, Any]:
    """经矩阵 resolve(`unlock`)。"""
    state = request.app.state.workbench
    provider = state.resolve("unlock")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    getter = _require_getter(provider, "get_unlock", "unlock")
    items = getter(syms, asof_date=asof_date, forward_days=forward_days)
    return {
        "capability": "unlock",
        "provider": getattr(provider, "name", type(provider).__name__),
        "items": items,
    }


@router.get(
    "/depth5",
    summary="五档盘口",
    responses={**ok200(MarketRowsResponse), **RESP_PROVIDER},
)
def get_depth5(
    request: Request,
    symbols: str = _Q_SYMBOLS,
) -> dict[str, Any]:
    """经矩阵 resolve(`depth5`)。"""
    state = request.app.state.workbench
    provider = state.resolve("depth5")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    getter = _require_getter(provider, "get_depth5", "depth5")
    rows = getter(syms)
    return {
        "capability": "depth5",
        "provider": getattr(provider, "name", type(provider).__name__),
        "rows": rows,
    }


@router.get(
    "/financial",
    summary="财务报表",
    responses={**ok200(MarketItemsResponse), **RESP_PROVIDER},
)
def get_financial(
    request: Request,
    symbols: str = _Q_SYMBOLS,
    periods: int = Query(8, ge=1, le=40, description="报告期数量"),
) -> dict[str, Any]:
    """经矩阵 resolve(`financial`)。"""
    state = request.app.state.workbench
    provider = state.resolve("financial")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    getter = _require_getter(provider, "get_financial", "financial")
    items = getter(syms, periods=periods)
    return {
        "capability": "financial",
        "provider": getattr(provider, "name", type(provider).__name__),
        "items": items,
    }


@router.get(
    "/adj-factor",
    summary="复权因子",
    responses={**ok200(MarketAdjFactorResponse), **RESP_PROVIDER},
)
def get_adj_factor(
    request: Request,
    symbols: str = _Q_SYMBOLS,
    kind: str = Query("qfq", description="qfq（前复权）或 hfq（后复权）"),
    start: date | None = _Q_START,
    end: date | None = _Q_END,
    limit: int = Query(0, ge=0, le=10000, description="最大返回条数；0 不截断"),
) -> dict[str, Any]:
    """经矩阵 resolve(`adj_factor`)。"""
    state = request.app.state.workbench
    provider = state.resolve("adj_factor")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    getter = _require_getter(provider, "get_adj_factor", "adj_factor")
    rows = getter(syms, kind=kind, start=start, end=end, limit=limit)
    return {
        "capability": "adj_factor",
        "provider": getattr(provider, "name", type(provider).__name__),
        "kind": kind,
        "rows": rows,
    }


@router.get(
    "/full-minute",
    summary="当日全部分钟线",
    responses={**ok200(MarketFullMinuteResponse), **RESP_PROVIDER},
)
def get_full_minute(
    request: Request,
    symbols: str = _Q_SYMBOLS,
    trade_date: date | None = Query(
        None, description="交易日 YYYY-MM-DD；默认 provider 今日（CN）"
    ),
    count: int = Query(300, ge=0, le=1000, description="每标的最大 1m 条数"),
) -> dict[str, Any]:
    """Same-day 1m batch (full_minute) — distinct from multi-freq /minute."""
    state = request.app.state.workbench
    provider = state.resolve("full_minute")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    getter = _require_getter(provider, "get_full_minute", "full_minute")
    rows = getter(syms, trade_date=trade_date, count=count)
    return {
        "capability": "full_minute",
        "provider": getattr(provider, "name", type(provider).__name__),
        "trade_date": trade_date.isoformat() if trade_date else None,
        "count": count,
        "rows": rows,
    }


@router.get(
    "/daily-adjusted",
    summary="复权日 K",
    responses={**ok200(MarketDailyAdjustedResponse), **RESP_PROVIDER},
)
def get_daily_adjusted(
    request: Request,
    symbols: str = _Q_SYMBOLS,
    kind: str = Query("qfq", description="qfq（前复权）或 hfq（后复权）"),
    start: date | None = _Q_START,
    end: date | None = _Q_END,
) -> dict[str, Any]:
    """Unadjusted daily OHLC scaled by adj_factor (not a matrix capability id)."""
    state = request.app.state.workbench
    daily_provider = state.resolve("daily")
    factor_provider = state.resolve("adj_factor")
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    daily_rows = daily_provider.get_daily(syms, start=start, end=end)
    getter = _require_getter(factor_provider, "get_adj_factor", "adj_factor")
    # Do not clip factor dates to the daily window (keep 1900 sentinel / earlier steps).
    factor_rows = getter(syms, kind=kind)
    try:
        rows = apply_adjust(daily_rows, factor_rows, kind=kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "capabilities": ["daily", "adj_factor"],
        "providers": {
            "daily": getattr(daily_provider, "name", type(daily_provider).__name__),
            "adj_factor": getattr(
                factor_provider, "name", type(factor_provider).__name__
            ),
        },
        "kind": kind,
        "rows": rows,
    }
