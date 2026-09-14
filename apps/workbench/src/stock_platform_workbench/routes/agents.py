"""Research / review agent slots — providers only via workbench resolve()."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from stock_platform_agents import (
    AgentError,
    DebateAgentPlugin,
    LlmUnavailableError,
    ResearchAgentPlugin,
    ReviewAgentPlugin,
    debate_brief_picks,
    llm_debate_status,
)
from stock_platform_providers import SymbolError

router = APIRouter(tags=["agents"])


@router.get("/api/research/report")
def research_report(
    request: Request,
    symbol: str = Query(...),
    asof: str | None = Query(None, description="YYYY-MM-DD; historical skips realtime"),
) -> dict[str, Any]:
    state = request.app.state.workbench
    provider = state.resolve("daily")
    try:
        return ResearchAgentPlugin(provider).run(symbol, asof=asof)
    except (AgentError, SymbolError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/review/report")
def review_report(
    request: Request,
    symbol: str = Query(...),
    asof: str | None = Query(None),
) -> dict[str, Any]:
    state = request.app.state.workbench
    provider = state.resolve("daily")
    try:
        return ReviewAgentPlugin(provider).run(symbol, asof=asof)
    except (AgentError, SymbolError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/debate/status")
def debate_status() -> dict[str, Any]:
    return llm_debate_status()


@router.get("/api/debate/report")
def debate_report(
    request: Request,
    symbol: str = Query(...),
    asof: str | None = Query(None, description="YYYY-MM-DD; historical skips realtime"),
    engine: str = Query(
        "deterministic",
        description="deterministic (default) | llm (optional; fail-closed)",
    ),
) -> dict[str, Any]:
    state = request.app.state.workbench
    provider = state.resolve("daily")
    try:
        return DebateAgentPlugin(provider).run(symbol, asof=asof, engine=engine)
    except LlmUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (AgentError, SymbolError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
