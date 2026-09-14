"""Replay provider + schema normalization tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from stock_platform_providers import SymbolError, normalize_symbol
from stock_platform_providers.normalize import (
    normalize_daily_row,
    normalize_fund_flow_row,
    normalize_lhb_payload,
    normalize_realtime_row,
    normalize_unlock_payload,
)
from stock_platform_providers.replay import ReplayProvider, ReplayTransport
from stock_platform_providers.schemas import (
    DAILY_COLUMNS,
    FUND_FLOW_COLUMNS,
    LHB_TOP_KEYS,
    REALTIME_COLUMNS,
    UNLOCK_TOP_KEYS,
)

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


def test_replay_lhb_with_records() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    items = provider.get_lhb(
        ["SZ002475"], asof_date=date(2026, 5, 17), look_back_days=30
    )
    assert len(items) == 1
    item = items[0]
    assert item["symbol"] == "002475"
    assert item["source"] == "replay"
    assert len(item["records"]) == 2
    assert item["records"][0]["net_buy"] == 85200000.0
    assert item["seats"]["buy"][0]["name"] == "机构专用"
    assert item["institution"]["net_amt"] == 50000000.0
    assert set(LHB_TOP_KEYS) <= set(item.keys())


def test_replay_lhb_empty_window() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    items = provider.get_lhb(["600519"], asof_date=date(2026, 5, 17))
    assert items[0]["records"] == []
    assert items[0]["seats"]["buy"] == []
    assert items[0]["institution"]["buy_amt"] == 0.0


def test_normalize_lhb_requires_asof() -> None:
    with pytest.raises(ValueError, match="asof_date"):
        normalize_lhb_payload({"symbol": "002475", "records": []}, source="test")


def test_replay_unlock_with_events() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    items = provider.get_unlock(
        ["SZ002475"], asof_date=date(2026, 5, 17), forward_days=90
    )
    assert len(items) == 1
    item = items[0]
    assert item["symbol"] == "002475"
    assert item["source"] == "replay"
    assert len(item["history"]) == 2
    assert item["history"][0]["shares"] == 8500.0
    assert len(item["upcoming"]) == 1
    assert item["upcoming"][0]["type"] == "首发原股东限售股份"
    assert set(UNLOCK_TOP_KEYS) <= set(item.keys())


def test_replay_unlock_empty() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    items = provider.get_unlock(["600519"], asof_date=date(2026, 5, 17))
    assert items[0]["history"] == []
    assert items[0]["upcoming"] == []


def test_normalize_unlock_requires_asof() -> None:
    with pytest.raises(ValueError, match="asof_date"):
        normalize_unlock_payload({"symbol": "002475", "history": []}, source="test")


def test_normalize_symbol_still_public() -> None:
    assert normalize_symbol("sz000001") == "000001"
