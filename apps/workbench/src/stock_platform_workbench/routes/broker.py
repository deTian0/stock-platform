"""Read-only SIMULATE broker status (paper or ths_sim). No live trading controls."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from stock_platform_execution import evaluate_admission
from stock_platform_execution.gated import GatedBroker
from stock_platform_workbench.openapi_models import BrokerStatusResponse, ok200

router = APIRouter(tags=["broker"])


@router.get(
    "/api/broker/status",
    summary="纸面/模拟券商只读状态",
    responses=ok200(BrokerStatusResponse),
)
def broker_status(request: Request) -> dict[str, Any]:
    """Positions + account + admission; never enables live trading."""
    paper = request.app.state.workbench.paper
    broker = paper.broker
    snap = broker.status()
    positions = [p.to_dict() if hasattr(p, "to_dict") else p for p in broker.get_positions()]
    try:
        account = broker.get_account().to_dict()
    except Exception as exc:  # noqa: BLE001 — surface in panel
        account = {"error": str(exc)}
    admission = evaluate_admission(
        data_ok=True,
        simulate_ok=True,
        live_off=True,
        hash_ok=bool(paper.lifecycle.active),
        timing_ok=True,
        idempotency_ok=True,
        order_guards_ok=True,
    )
    return {
        **snap,
        "positions": positions,
        "account": account,
        "admission": admission,
        "gated": isinstance(broker, GatedBroker),
        "liveTradingEnabled": False,
        "environment": "SIMULATE",
        "hint": "Read-only status. Enable ths_sim only via STOCK_PLATFORM_BROKER env (not a live switch).",
    }
