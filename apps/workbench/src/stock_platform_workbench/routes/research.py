"""Research brief routes — capability-matrix daily; SIMULATE product path."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from stock_platform_execution import DraftBlocked, ProfileBlocked
from stock_platform_execution.timing import market_now
from stock_platform_providers import apply_adjust, get_market_strategy
from stock_platform_agents import AgentError, LlmUnavailableError, debate_brief_picks
from stock_platform_research import (
    UniverseEmptyError,
    brief_to_orders,
    build_premarket_brief,
    default_performance_log_path,
    default_universe_fixture_path,
    log_brief_decisions,
    performance_summary,
)

from ..state import CapabilityUnavailable

router = APIRouter(prefix="/api/research", tags=["research"])


def _parse_symbols(raw: str | None) -> list[str] | None:
    if raw is None or not str(raw).strip():
        return None
    return [s.strip() for s in str(raw).split(",") if s.strip()]


def _optional_resolve(state: Any, capability: str) -> Any | None:
    try:
        return state.resolve(capability)
    except CapabilityUnavailable:
        return None


def _build_brief_for_request(
    request: Request,
    *,
    asof: date,
    symbols: list[str] | None,
    top_n: int,
    value_factor: bool,
    reversal_q: float,
    adjust_kind: str | None,
) -> dict[str, Any]:
    state = request.app.state.workbench
    daily = state.resolve("daily")
    adj = None
    adjust_fn = None
    kind = adjust_kind
    if kind:
        adj = _optional_resolve(state, "adj_factor")
        if adj is not None:
            adjust_fn = apply_adjust
        else:
            kind = None
    fund = _optional_resolve(state, "fund_flow")

    universe_path = None
    if symbols is None:
        packaged = default_universe_fixture_path()
        local = Path(state.fixtures_dir) / "universe_cn_sample.json"
        universe_path = local if local.is_file() else packaged

    try:
        return build_premarket_brief(
            asof=asof,
            symbols=symbols,
            universe_path=universe_path,
            daily_provider=daily,
            adj_provider=adj,
            fund_flow_provider=fund,
            apply_adjust_fn=adjust_fn,
            adjust_kind=kind,
            top_n=top_n,
            value_factor=value_factor,
            reversal_q=reversal_q,
        )
    except UniverseEmptyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/brief")
def get_brief(
    request: Request,
    asof: date = Query(..., description="Signal trade date (PIT as-of)"),
    symbols: str | None = Query(None, description="Comma-separated; default sample universe"),
    top_n: int = Query(10, ge=1, le=100, alias="topN"),
    value_factor: bool = Query(False, alias="valueFactor"),
    reversal_q: float = Query(0.30, alias="reversalQ"),
    adjust_kind: str | None = Query("qfq", description="qfq/hfq/none"),
) -> dict[str, Any]:
    kind = None if (adjust_kind or "").lower() in {"", "none", "raw"} else adjust_kind
    brief = _build_brief_for_request(
        request,
        asof=asof,
        symbols=_parse_symbols(symbols),
        top_n=top_n,
        value_factor=value_factor,
        reversal_q=reversal_q,
        adjust_kind=kind,
    )
    daily = request.app.state.workbench.resolve("daily")
    brief["provider"] = getattr(daily, "name", type(daily).__name__)
    return brief


class BriefToPaperRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    asof: date
    symbols: str | None = None
    top_n: int = Field(10, ge=1, le=100, alias="topN")
    value_factor: bool = Field(False, alias="valueFactor")
    reversal_q: float = Field(0.30, alias="reversalQ")
    adjust_kind: str | None = "qfq"
    qty: int = Field(100, ge=1, le=1_000_000)
    decision_only: bool = False
    now: str | None = None
    market: str = "CN"


@router.post("/brief/to-paper")
def brief_to_paper(request: Request, body: BriefToPaperRequest) -> dict[str, Any]:
    """Create a SIMULATE paper draft from brief TopN (requires active strategy)."""
    paper = request.app.state.workbench.paper
    active = paper.lifecycle.active
    if not active:
        raise HTTPException(status_code=400, detail="no active strategy; activate explicitly first")

    kind = None if (body.adjust_kind or "").lower() in {"", "none", "raw"} else body.adjust_kind
    brief = _build_brief_for_request(
        request,
        asof=body.asof,
        symbols=_parse_symbols(body.symbols),
        top_n=body.top_n,
        value_factor=body.value_factor,
        reversal_q=body.reversal_q,
        adjust_kind=kind,
    )
    orders = brief_to_orders(brief, qty=body.qty)
    mid = get_market_strategy(body.market).market_id
    if body.now:
        dt = datetime.fromisoformat(body.now.replace("Z", "+00:00"))
        now = market_now(mid, dt) if dt.tzinfo is None else dt
    else:
        now = market_now(mid)

    try:
        draft = paper.ledger.build_draft(
            strategy_hash=str(active["strategyHash"]),
            signal_trade_date=body.asof.isoformat(),
            orders=orders,
            decision_only=body.decision_only,
            market=mid,
            now=now,
        )
    except (DraftBlocked, ProfileBlocked, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "brief": brief,
        "draft": draft,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
    }


@router.get("/performance")
def get_performance(
    request: Request,
    log: str | None = Query(None, description="Optional JSONL path override"),
) -> dict[str, Any]:
    """Summarize settled recommend decisions (SIMULATE research metrics)."""
    import stock_platform_research

    path = Path(log) if log else default_performance_log_path()
    if not path.is_file():
        pkg_root = Path(stock_platform_research.__file__).resolve().parents[2]
        packaged = pkg_root / "tests" / "fixtures" / "recommend_decisions.jsonl"
        alt = Path(request.app.state.workbench.fixtures_dir) / "recommend_decisions.jsonl"
        if packaged.is_file():
            path = packaged
        elif alt.is_file():
            path = alt
    return performance_summary(path)


class LogBriefRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    asof: date
    symbols: str | None = None
    top_n: int = Field(10, ge=1, le=100, alias="topN")
    value_factor: bool = Field(False, alias="valueFactor")
    reversal_q: float = Field(0.30, alias="reversalQ")
    adjust_kind: str | None = "qfq"
    holding: str = "5d"
    log: str | None = None


@router.post("/performance/log-brief")
def post_log_brief(request: Request, body: LogBriefRequest) -> dict[str, Any]:
    """Append pending TopN decisions from a brief into the performance JSONL."""
    kind = None if (body.adjust_kind or "").lower() in {"", "none", "raw"} else body.adjust_kind
    brief = _build_brief_for_request(
        request,
        asof=body.asof,
        symbols=_parse_symbols(body.symbols),
        top_n=body.top_n,
        value_factor=body.value_factor,
        reversal_q=body.reversal_q,
        adjust_kind=kind,
    )
    path = Path(body.log) if body.log else default_performance_log_path()
    rows = log_brief_decisions(path, brief, holding=body.holding)
    return {
        "logPath": str(path),
        "appended": len(rows),
        "entries": rows,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
    }


class BriefDebateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    asof: date
    symbols: str | None = None
    top_n: int = Field(5, ge=1, le=50, alias="topN")
    value_factor: bool = Field(False, alias="valueFactor")
    reversal_q: float = Field(0.30, alias="reversalQ")
    adjust_kind: str | None = "qfq"
    engine: str = "deterministic"
    max_picks: int | None = Field(None, ge=1, le=50, alias="maxPicks")


@router.post("/brief/debate")
def brief_debate(request: Request, body: BriefDebateRequest) -> dict[str, Any]:
    """Build TopN brief then run debate on picks (default deterministic; llm fail-closed)."""
    kind = None if (body.adjust_kind or "").lower() in {"", "none", "raw"} else body.adjust_kind
    brief = _build_brief_for_request(
        request,
        asof=body.asof,
        symbols=_parse_symbols(body.symbols),
        top_n=body.top_n,
        value_factor=body.value_factor,
        reversal_q=body.reversal_q,
        adjust_kind=kind,
    )
    daily = request.app.state.workbench.resolve("daily")
    brief["provider"] = getattr(daily, "name", type(daily).__name__)
    try:
        return debate_brief_picks(
            daily,
            brief,
            engine=body.engine,
            max_picks=body.max_picks,
        )
    except LlmUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (AgentError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
