"""Replay provider + schema normalization tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from stock_platform_providers import SymbolError, normalize_symbol
from stock_platform_providers.normalize import (
    normalize_daily_row,
    normalize_fund_flow_row,
    normalize_realtime_row,
)
from stock_platform_providers.replay import ReplayProvider, ReplayTransport
from stock_platform_providers.schemas import DAILY_COLUMNS, FUND_FLOW_COLUMNS, REALTIME_COLUMNS

FIXTURES = Path(__file__).parent / "fixtures"


def test_normalize_daily_percent_flag() -> None:
    row = normalize_daily_row(
        {
            "symbol": "600519",
            "date": "2026-09-02",
            "open": 1,
            "high": 1,
            "low": 1,
            "close": 1,
            "volume": 1,
            "amount": 100,
            "change_pct": 1.5,
            "pct_unit": "percent",
        },
        source="test",
    )
    assert row["change_pct"] == pytest.approx(0.015)
    assert set(DAILY_COLUMNS) <= set(row.keys())


def test_normalize_realtime_requires_asof() -> None:
    with pytest.raises(ValueError, match="asof_ts"):
        normalize_realtime_row(
            {"symbol": "600519", "price": 10, "volume": 1},
            source="test",
        )


def test_replay_daily_and_realtime() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    daily = provider.get_daily(["SH600519"], start=date(2026, 9, 1), end=date(2026, 9, 2))
    assert len(daily) == 2
    assert daily[0]["symbol"] == "600519"
    assert daily[0]["source"] == "replay"
    assert daily[0]["volume"] == 25000
    assert daily[0]["amount"] == 3525000000
    # second bar used pct_unit=percent
    assert daily[1]["change_pct"] == pytest.approx(0.010638)
    for col in ("date", "open", "high", "low", "close", "volume", "amount"):
        assert daily[0][col] is not None

    rt = provider.get_realtime(["600519.SH"])
    assert len(rt) == 1
    assert rt[0]["symbol"] == "600519"
    assert rt[0]["change_pct"] == pytest.approx(0.010638)
    assert rt[0]["turnover_rate"] == pytest.approx(0.0012)
    assert rt[0]["asof_ts"] == 1725260400000
    assert set(REALTIME_COLUMNS) <= set(rt[0].keys())


def test_replay_rejects_hk_before_io() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    with pytest.raises(SymbolError):
        provider.get_daily(["00700"])


def test_replay_fund_flow() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    rows = provider.get_fund_flow(
        ["SH600519"], start=date(2026, 9, 1), end=date(2026, 9, 2)
    )
    assert len(rows) == 2
    assert rows[0]["symbol"] == "600519"
    assert rows[0]["source"] == "replay"
    assert rows[0]["main_net"] == 125000000.0
    assert rows[1]["main_net"] == -82000000.0
    assert set(FUND_FLOW_COLUMNS) <= set(rows[0].keys())


def test_normalize_fund_flow_requires_date() -> None:
    with pytest.raises(ValueError, match="missing date"):
        normalize_fund_flow_row(
            {"symbol": "600519", "main_net": 1.0},
            source="test",
        )


def test_normalize_symbol_still_public() -> None:
    assert normalize_symbol("sz000001") == "000001"
