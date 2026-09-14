"""Profile, lifecycle, admission, paper ledger tests."""

from __future__ import annotations

from datetime import datetime

import pytest

from stock_platform_execution import (
    ActivationBlocked,
    DraftBlocked,
    IdempotentReplay,
    PaperLedger,
    ProfileBlocked,
    StrategyLifecycle,
    build_strategy_spec,
    evaluate_admission,
    strategy_hash,
    validate_simulation_profile,
)
from stock_platform_execution.timing import CHINA_TZ


def test_profile_blocks_live() -> None:
    with pytest.raises(ProfileBlocked, match="liveTradingEnabled"):
        validate_simulation_profile({"liveTradingEnabled": True})


def test_profile_blocks_non_simulate() -> None:
    with pytest.raises(ProfileBlocked, match="SIMULATE"):
        validate_simulation_profile({"allowedEnvironment": "REAL"})


def test_lifecycle_activate_requires_safety_and_hash() -> None:
    life = StrategyLifecycle()
    spec = build_strategy_spec(universe=["510300"])
    h = strategy_hash(spec)
    life.save_draft(spec)
    life.mark_validated(h)
    with pytest.raises(ActivationBlocked, match="executionSafety"):
        life.activate(h, execution_safety_passed=False)
    active = life.activate(h, execution_safety_passed=True)
    assert active["stage"] == "active"
    # Editing a new draft does not change active
    life.save_draft(build_strategy_spec(universe=["159915"]))
    assert life.active["strategyHash"] == h


def test_admission_disclaimer() -> None:
    out = evaluate_admission(
        data_ok=True,
        simulate_ok=True,
        live_off=True,
        hash_ok=True,
        timing_ok=True,
        idempotency_ok=True,
        order_guards_ok=True,
    )
    assert out["passed"] is True
    assert "not proven" in out["disclaimer"].lower() or "不代表" in out["disclaimer"] or "not proven" in out["disclaimer"]


def test_paper_decision_only_strips_orders() -> None:
    ledger = PaperLedger()
    now = datetime(2026, 9, 7, 9, 40, tzinfo=CHINA_TZ)
    draft = ledger.build_draft(
        strategy_hash="h",
        signal_trade_date="2026-09-04",
        orders=[{"symbol": "510300", "side": "buy", "qty": 100}],
        decision_only=True,
        now=now,
    )
    assert draft["orders"] == []
    assert draft["decisionOnly"] is True
    with pytest.raises(DraftBlocked):
        ledger.execute_draft(draft["draftId"], now=now)


def test_paper_after_window_zero_orders() -> None:
    ledger = PaperLedger()
    now = datetime(2026, 9, 7, 10, 30, tzinfo=CHINA_TZ)
    draft = ledger.build_draft(
        strategy_hash="h",
        signal_trade_date="2026-09-04",
        orders=[{"symbol": "510300", "side": "buy", "qty": 100}],
        now=now,
    )
    assert draft["orders"] == []
    assert draft["executionWindowStatus"] == "after_window"


def test_paper_execute_and_idempotent() -> None:
    ledger = PaperLedger()
    now = datetime(2026, 9, 7, 9, 40, tzinfo=CHINA_TZ)
    draft = ledger.build_draft(
        strategy_hash="h",
        signal_trade_date="2026-09-04",
        orders=[{"symbol": "510300", "side": "buy", "qty": 100}],
        now=now,
    )
    assert draft["executionEligible"] is True
    result = ledger.execute_draft(draft["draftId"], now=now)
    assert result["accepted"] is True
    with pytest.raises(IdempotentReplay) as exc:
        ledger.execute_draft(draft["draftId"], now=now)
    assert exc.value.execution_id == result["executionId"]


def test_paper_status_banner() -> None:
    assert "SIMULATE" in PaperLedger().status()["banner"]


def test_paper_draft_stores_market_id_default_cn() -> None:
    ledger = PaperLedger()
    now = datetime(2026, 9, 7, 9, 40, tzinfo=CHINA_TZ)
    draft = ledger.build_draft(
        strategy_hash="h",
        signal_trade_date="2026-09-04",
        orders=[{"symbol": "510300", "side": "buy", "qty": 100}],
        now=now,
    )
    assert draft["marketId"] == "CN"


def test_paper_us_market_skips_independence_day() -> None:
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    ledger = PaperLedger()
    # 2025-07-03 Thu after ET daily bar final → plan skips Jul4 → Mon Jul7
    now = datetime(2025, 7, 7, 9, 40, tzinfo=et)
    draft = ledger.build_draft(
        strategy_hash="h",
        signal_trade_date="2025-07-03",
        orders=[{"symbol": "AAPL", "side": "buy", "qty": 10}],
        now=now,
        market="US",
    )
    assert draft["marketId"] == "US"
    assert draft["plannedExecutionDate"] == "2025-07-07"
    assert draft["executionEligible"] is True
    result = ledger.execute_draft(draft["draftId"], now=now)
    assert result["marketId"] == "US"
    assert result["accepted"] is True
