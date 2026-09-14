"""Transactional market vs execution boundary tests."""

from __future__ import annotations

from datetime import datetime

from stock_platform_execution import (
    EXECUTION_FIELDS,
    MARKET_FIELDS,
    build_pending_rebalance,
    committed_state_after_acceptance,
    compose_calculation_state,
)
from stock_platform_execution.timing import CHINA_TZ


def test_compose_keeps_committed_rebalance_index() -> None:
    h = "abc"
    market = {"strategyHash": h, "tradingDayIndex": 10, "lastSignalDate": "2026-09-01"}
    committed = {"strategyHash": h, "lastRebalanceIndex": 7, "tradingDayIndex": 99}
    state = compose_calculation_state(h, market, committed)
    assert state["tradingDayIndex"] == 10  # market field
    assert state["lastRebalanceIndex"] == 7  # committed execution field wins
    assert "lastSignalDate" in MARKET_FIELDS
    assert "lastRebalanceIndex" in EXECUTION_FIELDS


def test_market_cannot_overwrite_execution_via_market_blob() -> None:
    h = "abc"
    # Poisoned market blob trying to set execution field — compose ignores it
    market = {"strategyHash": h, "tradingDayIndex": 3, "lastRebalanceIndex": 999}
    committed = {"strategyHash": h, "lastRebalanceIndex": 2}
    state = compose_calculation_state(h, market, committed)
    assert state["lastRebalanceIndex"] == 2


def test_pending_uses_latest_target_weights() -> None:
    now = datetime(2026, 9, 8, 9, 0, tzinfo=CHINA_TZ)
    first = build_pending_rebalance(
        strategy_hash="h1",
        signal_trade_date="2026-09-04",
        planned_execution_date="2026-09-07",
        target_weights={"510300": 1.0},
        now=now,
    )
    later = build_pending_rebalance(
        strategy_hash="h1",
        signal_trade_date="2026-09-07",
        planned_execution_date="2026-09-08",
        target_weights={"510300": 0.5, "159915": 0.5},
        now=now,
        previous=first,
    )
    assert later["transition"] == "replaced"
    assert later["targetWeights"]["159915"] == 0.5
    assert later["originSignalTradeDate"] == "2026-09-04"


def test_commit_only_after_acceptance() -> None:
    proposed = {"strategyHash": "h", "tradingDayIndex": 5}
    committed = committed_state_after_acceptance(proposed, "h", "2026-09-08T09:40:00+08:00")
    assert committed["stateRole"] == "accepted_execution"
    assert committed["lastRebalanceIndex"] == 5
