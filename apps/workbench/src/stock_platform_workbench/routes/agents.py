"""Research / review agent slots — providers only via workbench resolve()."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from stock_platform_agents import (
    AgentError,
    DebateAgentPlugin,
    LlmUnavailableError,
    ResearchAgentPlugin,
    ReviewAgentPlugin,
    deep_llm_graph_status,
    llm_debate_status,
    run_deep_llm_graph,
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
    out = llm_debate_status()
    out["deepGraph"] = deep_llm_graph_status()
    return out


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


class DeepGraphRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    symbol: str
    asof: str | None = None
    roles: list[str] | None = None
    lookback_days: int = Field(60, ge=5, le=250, alias="lookbackDays")


@router.get("/api/debate/deep-graph/status")
def deep_graph_status() -> dict[str, Any]:
    """M-A4: deeper multi-role LLM graph status (default off)."""
    return deep_llm_graph_status()


@router.post("/api/debate/deep-graph")
def deep_graph(request: Request, body: DeepGraphRequest) -> dict[str, Any]:
    """M-A4 optional deeper LLM graph — non-default; fail-closed; no dataflows."""
    state = request.app.state.workbench
    provider = state.resolve("daily")
    caps = [
        str(row.get("id"))
        for row in state.matrix()
        if row.get("usable") and row.get("id")
    ]
    if "daily" not in caps:
        caps.append("daily")
    try:
        return run_deep_llm_graph(
            provider,
            body.symbol,
            asof=body.asof,
            lookback_days=body.lookback_days,
            available_capabilities=caps,
            roles=body.roles,
        )
    except LlmUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (AgentError, SymbolError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
