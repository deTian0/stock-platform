"""Deterministic research / review / debate slots — providers only via resolve().

Optional LLM status and deep-graph live in ``agents_llm.py`` (ADR 0088).
``GET /api/debate/report?engine=llm`` still lands here but lazy-loads the LLM face
inside ``DebateAgentPlugin``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from stock_platform_agents import (
    AgentError,
    DebateAgentPlugin,
    ResearchAgentPlugin,
    ReviewAgentPlugin,
)
from stock_platform_providers import SymbolError

from stock_platform_workbench.openapi_models import (
    RESP_400,
    RESP_409,
    AgentReportResponse,
    ok200,
)

router = APIRouter(tags=["agents"])


@router.get(
    "/api/research/report",
    summary="个股研报槽",
    responses={**ok200(AgentReportResponse), **RESP_400, **RESP_409},
)
def research_report(
    request: Request,
    symbol: str = Query(..., description="CN ticker, e.g. 600519"),
    asof: str | None = Query(None, description="YYYY-MM-DD; historical skips realtime"),
) -> dict[str, Any]:
    """Research agent slot — daily via capability matrix resolve only."""
    state = request.app.state.workbench
    provider = state.resolve("daily")
    try:
        return ResearchAgentPlugin(provider).run(symbol, asof=asof)
    except (AgentError, SymbolError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/api/review/report",
    summary="复盘报告槽",
    responses={**ok200(AgentReportResponse), **RESP_400, **RESP_409},
)
def review_report(
    request: Request,
    symbol: str = Query(..., description="CN ticker"),
    asof: str | None = Query(None, description="YYYY-MM-DD"),
) -> dict[str, Any]:
    """Review agent slot — daily via capability matrix resolve only."""
    state = request.app.state.workbench
    provider = state.resolve("daily")
    try:
        return ReviewAgentPlugin(provider).run(symbol, asof=asof)
    except (AgentError, SymbolError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/api/debate/report",
    summary="Bull/Bear/Risk 辩论报告",
    responses={**ok200(AgentReportResponse), **RESP_400, **RESP_409},
)
def debate_report(
    request: Request,
    symbol: str = Query(..., description="CN ticker"),
    asof: str | None = Query(None, description="YYYY-MM-DD; historical skips realtime"),
    engine: str = Query(
        "deterministic",
        description="deterministic (default) | llm (optional; fail-closed)",
    ),
) -> dict[str, Any]:
    """Deterministic (default) or optional LLM debate; LLM fail-closed without env."""
    state = request.app.state.workbench
    provider = state.resolve("daily")
    try:
        return DebateAgentPlugin(provider).run(symbol, asof=asof, engine=engine)
    except (AgentError, SymbolError) as exc:
        # LlmUnavailableError subclasses AgentError — both map to 400.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
