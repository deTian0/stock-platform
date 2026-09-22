"""Paper execution routes — SIMULATE only; no live broker."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field

from stock_platform_execution import (
    ActivationBlocked,
    DraftBlocked,
    IdempotentReplay,
    ProfileBlocked,
    build_strategy_spec,
    evaluate_admission,
)
from stock_platform_execution.timing import market_now
from stock_platform_providers import get_market_strategy

from ..openapi_models import (
    RESP_400,
    PaperDraftResponse,
    PaperExecuteResponse,
    PaperStatusResponse,
    StrategyEnsureDefaultResponse,
    ok200,
)
from ..paper_ux import ensure_active_simulate_strategy, friendly_execution_detail

router = APIRouter(tags=["paper"])


def _parse_now(raw: str | None, market: str = "CN") -> datetime | None:
    if not raw:
        return None
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return market_now(market, dt)
    return dt


class DraftRequest(BaseModel):
    signal_trade_date: str = Field(..., description="Signal trade date YYYY-MM-DD")
    orders: list[dict[str, Any]] = Field(default_factory=list, description="Order intents")
    decision_only: bool = Field(False, description="If true, draft is decision-only (no fill path)")
    now: str | None = Field(None, description="Clock override ISO-8601")
    market: str = Field("CN", description="Market id (CN/US/HK)")


class ActivateRequest(BaseModel):
    strategy_hash: str = Field(..., description="Strategy hash from draft/validate")
    universe: list[str] = Field(
        default_factory=lambda: ["510300"],
        description="Universe symbols for new draft specs",
    )


@router.get(
    "/api/paper/status",
    summary="纸面状态",
    responses=ok200(PaperStatusResponse),
)
def paper_status(request: Request) -> dict[str, Any]:
    """Paper broker + lifecycle snapshot; live trading always off."""
    paper = request.app.state.workbench.paper
    snap = paper.lifecycle.snapshot()
    admission = evaluate_admission(
        data_ok=True,
        simulate_ok=True,
        live_off=True,
        hash_ok=bool(snap.get("active")),
        timing_ok=True,
        idempotency_ok=True,
        order_guards_ok=True,
    )
    return {
        **paper.broker.status(),
        "lifecycle": snap,
        "admission": admission,
    }


@router.post(
    "/api/paper/strategies/draft",
    summary="保存策略草稿",
    responses={**ok200(PaperDraftResponse), **RESP_400},
)
def save_draft(request: Request, body: ActivateRequest) -> dict[str, Any]:
    """Create a SIMULATE strategy draft (hash derived from spec)."""
    paper = request.app.state.workbench.paper
    spec = build_strategy_spec(universe=body.universe or ["510300"])
    # Allow client to pin hash via rebuilding — always hash from spec
    saved = paper.lifecycle.save_draft(spec)
    return saved


@router.post(
    "/api/paper/strategies/validate",
    summary="校验策略",
    responses={**ok200(PaperDraftResponse), **RESP_400},
)
def validate_strategy(request: Request, body: ActivateRequest) -> dict[str, Any]:
    """Mark a draft strategy as validated."""
    paper = request.app.state.workbench.paper
    try:
        return paper.lifecycle.mark_validated(body.strategy_hash)
    except ActivationBlocked as exc:
        raise HTTPException(status_code=400, detail=friendly_execution_detail(exc)) from exc


@router.post(
    "/api/paper/strategies/activate",
    summary="激活策略",
    responses={**ok200(PaperDraftResponse), **RESP_400},
)
def activate_strategy(request: Request, body: ActivateRequest) -> dict[str, Any]:
    """Explicitly activate a validated SIMULATE strategy."""
    paper = request.app.state.workbench.paper
    admission = evaluate_admission(
        data_ok=True,
        simulate_ok=True,
        live_off=True,
        hash_ok=True,
        timing_ok=True,
        idempotency_ok=True,
        order_guards_ok=True,
    )
    try:
        return paper.lifecycle.activate(
            body.strategy_hash,
            execution_safety_passed=admission["passed"],
        )
    except ActivationBlocked as exc:
        raise HTTPException(status_code=400, detail=friendly_execution_detail(exc)) from exc


@router.post(
    "/api/paper/strategies/ensure-default",
    summary="确保默认 SIMULATE 策略已激活",
    responses={**ok200(StrategyEnsureDefaultResponse), **RESP_400},
)
def ensure_default_strategy(request: Request) -> dict[str, Any]:
    """One-click / idempotent: create+activate default SIMULATE strategy if none active."""
    paper = request.app.state.workbench.paper
    try:
        ensured = ensure_active_simulate_strategy(paper.lifecycle)
    except ActivationBlocked as exc:
        raise HTTPException(status_code=400, detail=friendly_execution_detail(exc)) from exc
    return {
        "active": ensured["active"],
        "strategyHash": ensured["strategyHash"],
        "strategyAutoActivated": ensured["autoActivated"],
        "strategyStatus": ensured["statusMessage"],
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
    }


@router.post(
    "/api/paper/drafts",
    summary="创建纸面订单草稿",
    responses={**ok200(PaperDraftResponse), **RESP_400},
)
def create_draft(request: Request, body: DraftRequest) -> dict[str, Any]:
    """Build a paper order draft; auto-ensures default strategy when none active."""
    paper = request.app.state.workbench.paper
    try:
        ensured = ensure_active_simulate_strategy(paper.lifecycle)
    except ActivationBlocked as exc:
        raise HTTPException(status_code=400, detail=friendly_execution_detail(exc)) from exc
    active = ensured["active"]
    try:
        mid = get_market_strategy(body.market).market_id
        draft = paper.broker.build_draft(
            strategy_hash=str(active["strategyHash"]),
            signal_trade_date=body.signal_trade_date,
            orders=body.orders,
            decision_only=body.decision_only,
            market=mid,
            now=_parse_now(body.now, mid) or market_now(mid),
        )
    except (DraftBlocked, ProfileBlocked, ValueError) as exc:
        raise HTTPException(status_code=400, detail=friendly_execution_detail(exc)) from exc
    return {
        **draft,
        "strategyAutoActivated": ensured["autoActivated"],
        "strategyStatus": ensured["statusMessage"],
        "liveTradingEnabled": False,
    }


@router.post(
    "/api/paper/drafts/{draft_id}/execute",
    summary="执行纸面草稿（幂等）",
    responses={**ok200(PaperExecuteResponse), **RESP_400},
)
def execute_draft(
    request: Request,
    draft_id: str = Path(..., description="Draft id from POST /api/paper/drafts"),
    now: str | None = Query(None, description="Clock override ISO-8601"),
    market: str = Query("CN", description="Market id"),
) -> dict[str, Any]:
    """Submit a draft; idempotent replay returns accepted=true without double-fill."""
    paper = request.app.state.workbench.paper
    try:
        mid = get_market_strategy(market).market_id
        return paper.broker.execute_draft(
            draft_id,
            market=mid,
            now=_parse_now(now, mid) or market_now(mid),
        )
    except IdempotentReplay as exc:
        return {
            "accepted": True,
            "idempotentReplay": True,
            "draftId": exc.draft_id,
            "executionId": exc.execution_id,
            "environment": "SIMULATE",
            "liveTradingEnabled": False,
        }
    except (DraftBlocked, ProfileBlocked, ValueError) as exc:
        raise HTTPException(status_code=400, detail=friendly_execution_detail(exc)) from exc
