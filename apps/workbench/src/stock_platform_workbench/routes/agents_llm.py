"""Optional LLM advisory routes (sidecar) — status + deep multi-role graph.

Deterministic research / review / debate report slots live in ``agents.py``.
These endpoints require the agents LLM face (lazy-imported) and stay fail-closed
without ``STOCK_PLATFORM_LLM_DEBATE`` + API key (ADR 0034 / 0045 / 0088).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from stock_platform_agents import AgentError, LlmUnavailableError
from stock_platform_providers import SymbolError

from stock_platform_workbench.openapi_models import (
    RESP_400,
    RESP_409,
    AgentReportResponse,
    DebateStatusResponse,
    ok200,
)

router = APIRouter(tags=["agents-llm"])


@router.get(
    "/api/debate/status",
    summary="辩论引擎状态",
    responses=ok200(DebateStatusResponse),
)
def debate_status() -> dict[str, Any]:
    """LLM debate availability + deep-graph status (default off)."""
    from stock_platform_agents.llm import deep_llm_graph_status, llm_debate_status

    out = llm_debate_status()
    out["deepGraph"] = deep_llm_graph_status()
    return out


class DeepGraphRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    symbol: str = Field(..., description="CN ticker")
    asof: str | None = Field(None, description="YYYY-MM-DD")
    roles: list[str] | None = Field(None, description="Optional role subset")
    lookback_days: int = Field(
        60, ge=5, le=250, alias="lookbackDays", description="Lookback calendar days"
    )


@router.get(
    "/api/debate/deep-graph/status",
    summary="深度多角色 LLM 图状态",
    responses=ok200(DebateStatusResponse),
)
def deep_graph_status() -> dict[str, Any]:
    """M-A4: deeper multi-role LLM graph status (default off)."""
    from stock_platform_agents.llm import deep_llm_graph_status

    return deep_llm_graph_status()


@router.post(
    "/api/debate/deep-graph",
    summary="运行深度多角色 LLM 图",
    responses={**ok200(AgentReportResponse), **RESP_400, **RESP_409},
)
def deep_graph(request: Request, body: DeepGraphRequest) -> dict[str, Any]:
    """M-A4 optional deeper LLM graph — non-default; fail-closed; no dataflows."""
    from stock_platform_agents.llm import run_deep_llm_graph

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
