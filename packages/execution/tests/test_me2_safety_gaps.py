"""M-E2 safety gap regressions from V2 mapping (SIMULATE only)."""

from __future__ import annotations

from datetime import datetime

import pytest

from stock_platform_execution import (
    ActivationBlocked,
    DraftBlocked,
    PaperBroker,
    build_strategy_spec,
    evaluate_admission,
    strategy_hash,
)
from stock_platform_execution.gated import GatedBroker
from stock_platform_execution.lifecycle import StrategyLifecycle
from stock_platform_execution.timing import CHINA_TZ


def test_lifecycle_rejects_wrong_validate_hash() -> None:
    life = StrategyLifecycle()
    spec = build_strategy_spec(universe=["510300"])
    life.save_draft(spec)
    with pytest.raises(ActivationBlocked, match="draft hash mismatch"):
        life.mark_validated("0" * 64)


def test_lifecycle_rejects_wrong_activate_hash() -> None:
    life = StrategyLifecycle()
    spec = build_strategy_spec(universe=["510300"])
    h = strategy_hash(spec)
    life.save_draft(spec)
    life.mark_validated(h)
    with pytest.raises(ActivationBlocked, match="validatedHash mismatch"):
        life.activate("f" * 64, execution_safety_passed=True)


def test_admission_fails_when_hash_not_ok() -> None:
    out = evaluate_admission(
        data_ok=True,
        simulate_ok=True,
        live_off=True,
        hash_ok=False,
        timing_ok=True,
        idempotency_ok=True,
        order_guards_ok=True,
    )
    assert out["passed"] is False
    assert out["criteria"]["hash"] is False


def test_gated_broker_blocks_mismatched_strategy_hash() -> None:
    gated = GatedBroker(PaperBroker(), require_active_hash=True)
    gated.set_active_hash("expected-hash")
    now = datetime(2026, 9, 7, 9, 40, tzinfo=CHINA_TZ)
    with pytest.raises(DraftBlocked, match="admission"):
        gated.build_draft(
            strategy_hash="wrong-hash",
            signal_trade_date="2026-09-04",
            orders=[{"symbol": "510300", "side": "buy", "qty": 100}],
            now=now,
        )


def test_admission_fails_when_order_guards_off() -> None:
    """P2 fee/min-order style gate: order_guards must stay fail-closed."""
    out = evaluate_admission(
        data_ok=True,
        simulate_ok=True,
        live_off=True,
        hash_ok=True,
        timing_ok=True,
        idempotency_ok=True,
        order_guards_ok=False,
    )
    assert out["passed"] is False
    assert out["criteria"]["order_guards"] is False
