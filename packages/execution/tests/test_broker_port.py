"""Broker port + THS sim tests (CI zero public net)."""

from __future__ import annotations

from datetime import datetime

import pytest

from stock_platform_execution import (
    BrokerConfigError,
    DraftBlocked,
    IdempotentReplay,
    PaperBroker,
    PaperLedger,
    ProfileBlocked,
    resolve_broker,
)
from stock_platform_execution.gated import GatedBroker, assert_sim_gates
from stock_platform_execution.ths_sim import (
    ExperimentalThsHttpTransport,
    MockThsTransport,
    ThsSimBroker,
)
from stock_platform_execution.timing import CHINA_TZ


def test_resolve_broker_default_paper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STOCK_PLATFORM_BROKER", raising=False)
    b = resolve_broker()
    assert isinstance(b, PaperBroker)
    assert b.name == "paper"


def test_resolve_broker_rejects_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCK_PLATFORM_BROKER", "futu")
    with pytest.raises(BrokerConfigError, match="paper"):
        resolve_broker()


def test_paper_broker_positions_after_fill() -> None:
    broker = PaperBroker()
    now = datetime(2026, 9, 7, 9, 40, tzinfo=CHINA_TZ)
    draft = broker.build_draft(
        strategy_hash="h",
        signal_trade_date="2026-09-04",
        orders=[{"symbol": "600519", "side": "buy", "qty": 100, "price": 10.0}],
        now=now,
    )
    assert draft["broker"] == "paper"
    assert draft["liveTradingEnabled"] is False
    result = broker.execute_draft(draft["draftId"], now=now)
    assert result["accepted"] is True
    pos = broker.get_positions()
    assert len(pos) == 1
    assert pos[0].symbol == "600519"
    assert pos[0].qty == 100
    acct = broker.get_account()
    assert acct.live_trading_enabled is False
    assert acct.environment == "SIMULATE"


def test_ths_mock_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCK_PLATFORM_BROKER", "ths_sim")
    monkeypatch.setenv("STOCK_PLATFORM_THS_MODE", "mock")
    broker = resolve_broker()
    assert isinstance(broker, ThsSimBroker)
    now = datetime(2026, 9, 7, 9, 40, tzinfo=CHINA_TZ)
    draft = broker.build_draft(
        strategy_hash="h",
        signal_trade_date="2026-09-04",
        orders=[{"symbol": "510300", "side": "buy", "qty": 200, "price": 4.5}],
        now=now,
    )
    assert draft["broker"] == "ths_sim"
    result = broker.execute_draft(draft["draftId"], now=now)
    assert result["accepted"] is True
    assert result["liveTradingEnabled"] is False
    assert result["thsMode"] == "mock"
    pos = broker.get_positions()
    assert pos[0].qty == 200
    with pytest.raises(IdempotentReplay):
        broker.execute_draft(draft["draftId"], now=now)


def test_ths_decision_only_refuses_execute() -> None:
    broker = ThsSimBroker(MockThsTransport())
    now = datetime(2026, 9, 7, 9, 40, tzinfo=CHINA_TZ)
    draft = broker.build_draft(
        strategy_hash="h",
        signal_trade_date="2026-09-04",
        orders=[{"symbol": "510300", "side": "buy", "qty": 100}],
        decision_only=True,
        now=now,
    )
    assert draft["orders"] == []
    with pytest.raises(DraftBlocked):
        broker.execute_draft(draft["draftId"], now=now)


def test_ths_experimental_fail_closed_without_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCK_PLATFORM_BROKER", "ths_sim")
    monkeypatch.setenv("STOCK_PLATFORM_THS_MODE", "experimental")
    monkeypatch.delenv("STOCK_PLATFORM_THS_BASE_URL", raising=False)
    monkeypatch.delenv("STOCK_PLATFORM_THS_TOKEN", raising=False)
    with pytest.raises(BrokerConfigError, match="STOCK_PLATFORM_THS"):
        resolve_broker()


def test_ths_experimental_pending_without_injection() -> None:
    transport = ExperimentalThsHttpTransport(base_url="https://example.invalid", token="x")
    with pytest.raises(Exception, match="pending|stable|wire-up"):
        transport.authenticate()


def test_gated_broker_blocks_bad_profile() -> None:
    with pytest.raises(ProfileBlocked):
        assert_sim_gates(profile={"liveTradingEnabled": True})
    inner = PaperBroker()
    gated = GatedBroker(inner, require_active_hash=True)
    gated.set_active_hash("active")
    now = datetime(2026, 9, 7, 9, 40, tzinfo=CHINA_TZ)
    with pytest.raises(DraftBlocked, match="admission"):
        gated.build_draft(
            strategy_hash="other",
            signal_trade_date="2026-09-04",
            orders=[{"symbol": "510300", "side": "buy", "qty": 100}],
            now=now,
        )
    draft = gated.build_draft(
        strategy_hash="active",
        signal_trade_date="2026-09-04",
        orders=[{"symbol": "510300", "side": "buy", "qty": 100, "price": 1.0}],
        now=now,
    )
    assert draft["executionEligible"] is True


def test_paper_ledger_still_default_path() -> None:
    """Regression: PaperLedger API unchanged for workbench."""
    ledger = PaperLedger()
    now = datetime(2026, 9, 7, 9, 40, tzinfo=CHINA_TZ)
    draft = ledger.build_draft(
        strategy_hash="h",
        signal_trade_date="2026-09-04",
        orders=[{"symbol": "510300", "side": "buy", "qty": 100}],
        now=now,
    )
    assert draft["environment"] == "SIMULATE"
