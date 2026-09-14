"""Paper execution routes — SIMULATE only; no live broker."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
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

router = APIRouter(tags=["paper"])


def _parse_now(raw: str | None, market: str = "CN") -> datetime | None:
    if not raw:
        return None
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return market_now(market, dt)
    return dt


class DraftRequest(BaseModel):
    signal_trade_date: str
    orders: list[dict[str, Any]] = Field(default_factory=list)
    decision_only: bool = False
    now: str | None = None
    market: str = "CN"


class ActivateRequest(BaseModel):
    strategy_hash: str
    universe: list[str] = Field(default_factory=lambda: ["510300"])


@router.get("/api/paper/status")
def paper_status(request: Request) -> dict[str, Any]:
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


@router.post("/api/paper/strategies/draft")
def save_draft(request: Request, body: ActivateRequest) -> dict[str, Any]:
    paper = request.app.state.workbench.paper
    spec = build_strategy_spec(universe=body.universe or ["510300"])
    # Allow client to pin hash via rebuilding — always hash from spec
    saved = paper.lifecycle.save_draft(spec)
    return saved


@router.post("/api/paper/strategies/validate")
def validate_strategy(request: Request, body: ActivateRequest) -> dict[str, Any]:
    paper = request.app.state.workbench.paper
    try:
        return paper.lifecycle.mark_validated(body.strategy_hash)
    except ActivationBlocked as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/paper/strategies/activate")
def activate_strategy(request: Request, body: ActivateRequest) -> dict[str, Any]:
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/paper/drafts")
def create_draft(request: Request, body: DraftRequest) -> dict[str, Any]:
    paper = request.app.state.workbench.paper
    active = paper.lifecycle.active
    if not active:
        raise HTTPException(status_code=400, detail="no active strategy; activate explicitly first")
    try:
        mid = get_market_strategy(body.market).market_id
        return paper.broker.build_draft(
            strategy_hash=str(active["strategyHash"]),
            signal_trade_date=body.signal_trade_date,
            orders=body.orders,
            decision_only=body.decision_only,
            market=mid,
            now=_parse_now(body.now, mid) or market_now(mid),
        )
    except (DraftBlocked, ProfileBlocked, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/paper/drafts/{draft_id}/execute")
def execute_draft(
    request: Request,
    draft_id: str,
    now: str | None = None,
    market: str = "CN",
) -> dict[str, Any]:
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc
