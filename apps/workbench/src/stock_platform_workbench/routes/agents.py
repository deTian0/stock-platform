"""Research / review agent slots — providers only via workbench resolve()."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from stock_platform_agents import AgentError, ResearchAgentPlugin, ReviewAgentPlugin
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
