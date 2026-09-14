"""Market state vs execution commit boundary (broker-free)."""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

MARKET_FIELDS = frozenset(
    {
        "lastSignalDate",
        "tradingDayIndex",
        "previousRegime",
        "pendingRegime",
        "pendingRegimeDays",
        "pendingSignal",
        "cachedDecision",
    }
)

EXECUTION_FIELDS = frozenset(
    {
        "lastRebalanceIndex",
        "riskBrakeActive",
        "riskBrakeStartedIndex",
        "riskPeakValue",
    }
)

ACTIVE_PENDING = frozenset(
    {
        "pending",
        "partially_submitted",
        "execution_blocked",
        "broker_accepted",
        "partially_filled",
        "unknown",
    }
)


def empty_decision_state(strategy_hash: str) -> dict[str, Any]:
    return {
        "schemaVersion": 2,
        "strategyHash": strategy_hash,
        "tradingDayIndex": -1,
        "lastRebalanceIndex": -1,
    }


def compose_calculation_state(
    strategy_hash: str,
    market_state: dict[str, Any] | None,
    committed_state: dict[str, Any] | None,
) -> dict[str, Any]:
    """Market overlays calculation; committed execution fields only from accept path."""
    state = empty_decision_state(strategy_hash)
    if market_state and market_state.get("strategyHash") == strategy_hash:
        for key in MARKET_FIELDS:
            if key in market_state:
                state[key] = copy.deepcopy(market_state[key])
    if committed_state and committed_state.get("strategyHash") == strategy_hash:
        for key in EXECUTION_FIELDS:
            if key in committed_state:
                state[key] = copy.deepcopy(committed_state[key])
    state["schemaVersion"] = 2
    state["strategyHash"] = strategy_hash
    return state


def extract_market_state(proposed_state: dict[str, Any] | None, strategy_hash: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schemaVersion": 2,
        "strategyHash": strategy_hash,
        "stateRole": "market_calculation",
    }
    for key in MARKET_FIELDS:
        if proposed_state and key in proposed_state:
            result[key] = copy.deepcopy(proposed_state[key])
    return result


def committed_state_after_acceptance(
    proposed_state: dict[str, Any] | None,
    strategy_hash: str,
    accepted_at: str,
) -> dict[str, Any]:
    state = copy.deepcopy(proposed_state or empty_decision_state(strategy_hash))
    state["schemaVersion"] = 2
    state["strategyHash"] = strategy_hash
    state["stateRole"] = "accepted_execution"
    state["lastRebalanceIndex"] = int(state.get("tradingDayIndex", -1))
    state["committedAt"] = accepted_at
    return state


def pending_is_active(payload: dict[str, Any] | None, strategy_hash: str | None = None) -> bool:
    if not isinstance(payload, dict) or payload.get("status") not in ACTIVE_PENDING:
        return False
    return not strategy_hash or payload.get("strategyHash") == strategy_hash


def build_pending_rebalance(
    *,
    strategy_hash: str,
    signal_trade_date: str,
    planned_execution_date: str | None,
    target_weights: dict[str, float],
    now: datetime,
    previous: dict[str, Any] | None = None,
    trigger: str = "rebalance",
) -> dict[str, Any]:
    """Hang intent across windows; always carry *latest* target weights (never stale qty)."""
    prior = previous if pending_is_active(previous, strategy_hash) else {}
    old_target = prior.get("targetWeights") if isinstance(prior.get("targetWeights"), dict) else {}
    transition = "created" if not prior else ("continued" if old_target == target_weights else "replaced")
    return {
        "schemaVersion": 2,
        "status": "pending",
        "strategyHash": strategy_hash,
        "originSignalTradeDate": str(
            prior.get("originSignalTradeDate") or signal_trade_date
        ),
        "signalTradeDate": signal_trade_date,
        "plannedExecutionDate": planned_execution_date,
        "targetWeights": copy.deepcopy(target_weights),
        "originTrigger": str(prior.get("originTrigger") or trigger),
        "transition": transition,
        "createdAt": str(prior.get("createdAt") or now.isoformat(timespec="seconds")),
        "updatedAt": now.isoformat(timespec="seconds"),
    }
