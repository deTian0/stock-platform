"""GlobalReplayProvider tests (US/HK fixtures only)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from stock_platform_providers import (
    GlobalReplayProvider,
    GlobalReplayTransport,
    SymbolError,
    get_market_strategy,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "global"


@pytest.fixture()
def us_provider() -> GlobalReplayProvider:
    return GlobalReplayProvider(GlobalReplayTransport(FIXTURES), market="US")


@pytest.fixture()
def hk_provider() -> GlobalReplayProvider:
    return GlobalReplayProvider(GlobalReplayTransport(FIXTURES), market="HK")


def test_us_daily_and_realtime(us_provider: GlobalReplayProvider) -> None:
    rows = us_provider.get_daily(
        ["aapl"], start=date(2026, 9, 1), end=date(2026, 9, 2)
    )
    assert len(rows) == 2
    assert rows[-1]["symbol"] == "AAPL"
    assert rows[-1]["close"] == 227.0
    rt = us_provider.get_realtime(["AAPL"])
    assert rt[0]["price"] == 227.0
    assert rt[0]["source"] == "global_replay"


def test_hk_daily(hk_provider: GlobalReplayProvider) -> None:
    rows = hk_provider.get_daily(["0700.HK"], end=date(2026, 9, 2))
    assert rows[-1]["symbol"] == "00700"
    assert rows[-1]["close"] == 392.0


def test_us_provider_rejects_hk_ticker(us_provider: GlobalReplayProvider) -> None:
    with pytest.raises(SymbolError):
        us_provider.get_daily(["00700"])


def test_strategy_settle_not_applied_to_global_rows(
    us_provider: GlobalReplayProvider,
) -> None:
    """Sanity: market strategy for US has no CN T+1; provider does not invent limits."""
    us = get_market_strategy("US")
    assert us.settle_rule("stock").buy_to_sell_delay_days == 0
    assert us.limit_rules("AAPL") is not None
    assert us.limit_rules("AAPL").has_limits is False
    assert us_provider.get_daily(["AAPL"])
