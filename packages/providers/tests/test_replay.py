"""Replay provider + schema normalization tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from stock_platform_providers import SymbolError, normalize_symbol
from stock_platform_providers.normalize import (
    normalize_daily_row,
    normalize_depth5_row,
    normalize_financial_payload,
    normalize_fund_flow_row,
    normalize_lhb_payload,
    normalize_minute_row,
    normalize_news_row,
    normalize_realtime_row,
    normalize_sector_fund_flow_row,
    normalize_unlock_payload,
)
from stock_platform_providers.replay import ReplayProvider, ReplayTransport
from stock_platform_providers.schemas import (
    DAILY_COLUMNS,
    DEPTH5_COLUMNS,
    FUND_FLOW_COLUMNS,
    LHB_TOP_KEYS,
    MINUTE_COLUMNS,
    NEWS_COLUMNS,
    REALTIME_COLUMNS,
    SECTOR_FUND_FLOW_COLUMNS,
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


def test_replay_minute() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    rows = provider.get_minute(
        ["SH600519"], freq="1m", start=date(2026, 9, 1), end=date(2026, 9, 2)
    )
    assert len(rows) == 3
    assert rows[0]["symbol"] == "600519"
    assert rows[0]["source"] == "replay"
    assert rows[0]["freq"] == "1m"
    assert rows[0]["datetime"] == "2026-09-01 09:31:00"
    assert rows[0]["volume"] == 1200
    assert rows[2]["datetime"] == "2026-09-02 09:31:00"
    assert set(MINUTE_COLUMNS) <= set(rows[0].keys())
    # 5m bars filtered out when asking 1m
    fives = provider.get_minute(["600519"], freq="5m")
    assert len(fives) == 1
    assert fives[0]["freq"] == "5m"
    assert fives[0]["close"] == 1404.0


def test_replay_minute_missing_fixture_empty() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    assert provider.get_minute(["000001"], freq="1m") == []


def test_replay_depth5() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    rows = provider.get_depth5(["SH600519"])
    assert len(rows) == 1
    assert rows[0]["symbol"] == "600519"
    assert rows[0]["source"] == "replay"
    assert rows[0]["bid_prices"][0] == 1425.0
    assert rows[0]["bid_volumes"][0] == 10
    assert rows[0]["ask_prices"][0] == 1425.1
    assert rows[0]["ask_volumes"][-1] == 52
    assert len(rows[0]["bid_prices"]) == 5
    assert rows[0]["asof_ts"] == 1725260400000
    assert set(DEPTH5_COLUMNS) <= set(rows[0].keys())


def test_replay_depth5_missing_fixture_empty() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    assert provider.get_depth5(["000001"]) == []


def test_replay_financial() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    items = provider.get_financial(["SH600519"])
    assert len(items) == 1
    item = items[0]
    assert item["symbol"] == "600519"
    assert item["source"] == "replay"
    assert item["periods"] == 2
    assert item["income"][0]["period_end"] == "2026-03-31"
    assert item["income"][0]["revenue"] == 39112000000.0
    assert item["income"][0]["net_income"] == 20850000000.0
    assert item["balance"][0]["total_assets"] == 310000000000.0
    assert item["cashflow"][0]["net_operating_cash_flow"] == 22000000000.0


def test_replay_financial_missing_fixture_empty() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    assert provider.get_financial(["000001"]) == []


def test_normalize_financial_aliases() -> None:
    payload = normalize_financial_payload(
        {
            "symbol": "600519",
            "income": [{"报告期": "2026-06-30", "营业收入": "1", "净利润": "2"}],
            "balance": [],
            "cashflow": [],
        },
        source="test",
    )
    assert payload["income"][0]["revenue"] == 1.0
    assert payload["income"][0]["net_income"] == 2.0
    assert payload["balance"] == []
    assert payload["periods"] == 1


def test_replay_adj_factor() -> None:
    from stock_platform_providers.normalize import normalize_adj_factor_row
    from stock_platform_providers.schemas import ADJ_FACTOR_COLUMNS

    provider = ReplayProvider(ReplayTransport(FIXTURES))
    rows = provider.get_adj_factor(["SH600519"])
    assert len(rows) >= 3
    assert rows[0]["symbol"] == "600519"
    assert rows[0]["source"] == "replay"
    assert rows[0]["trade_date"] == "2026-06-26"
    assert rows[0]["ex_factor"] == 1.0
    assert rows[0]["trade_date"] >= rows[-1]["trade_date"]
    assert set(ADJ_FACTOR_COLUMNS) <= set(rows[0].keys())
    aliased = normalize_adj_factor_row(
        {"code": "600519", "d": "2024-01-02", "f": "1.25"},
        source="test",
    )
    assert aliased["trade_date"] == "2024-01-02"
    assert aliased["ex_factor"] == 1.25


def test_replay_adj_factor_missing_fixture_empty() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    # 510300 has daily/fund_flow for sample universe but no adj_factor fixture.
    assert provider.get_adj_factor(["510300"]) == []


def test_replay_full_minute() -> None:
    from stock_platform_providers.schemas import MINUTE_COLUMNS

    provider = ReplayProvider(ReplayTransport(FIXTURES))
    rows = provider.get_full_minute(
        ["SH600519", "000001"], trade_date=date(2026, 9, 1), count=300
    )
    assert len(rows) == 5  # 3 for 600519 on 09-01 + 2 for 000001
    assert all(r["freq"] == "1m" for r in rows)
    assert all(r["datetime"].startswith("2026-09-01") for r in rows)
    assert rows[0]["symbol"] == "600519"
    assert rows[0]["source"] == "replay"
    assert rows[3]["symbol"] == "000001"
    assert set(MINUTE_COLUMNS) <= set(rows[0].keys())
    # count truncates per symbol
    short = provider.get_full_minute(["600519"], trade_date=date(2026, 9, 1), count=2)
    assert len(short) == 2
    assert short[-1]["datetime"] == "2026-09-01 14:59:00"
    # does not fall back to minute_* fixtures
    assert provider.get_full_minute(["600000"], trade_date=date(2026, 9, 1)) == []


def test_replay_full_minute_missing_fixture_empty() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    assert provider.get_full_minute(["000002"], trade_date=date(2026, 9, 1)) == []


def test_replay_adj_factor_date_filter() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    rows = provider.get_adj_factor(
        ["600519"],
        start=date(2025, 1, 1),
        end=date(2026, 12, 31),
        limit=1,
    )
    assert len(rows) == 1
    assert rows[0]["trade_date"] == "2026-06-26"


def test_normalize_depth5_pads_levels() -> None:
    row = normalize_depth5_row(
        {
            "symbol": "600519",
            "bid_prices": [1.0, 2.0],
            "bid_volumes": [10],
            "ask_prices": [3.0],
            "ask_volumes": [4.0, 5.0, 6.0, 7.0, 8.0, 9.0],
            "asof_ts": 1725260400000,
        },
        source="test",
    )
    assert row["bid_prices"] == [1.0, 2.0, None, None, None]
    assert row["ask_volumes"] == [4.0, 5.0, 6.0, 7.0, 8.0]


def test_normalize_minute_rejects_tz() -> None:
    with pytest.raises(ValueError, match="timezone|naive"):
        normalize_minute_row(
            {
                "symbol": "600519",
                "datetime": "2026-09-01T09:31:00Z",
                "open": 1,
                "high": 1,
                "low": 1,
                "close": 1,
                "volume": 1,
            },
            source="test",
        )


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


def test_replay_sector_fund_flow() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    rows = provider.get_sector_fund_flow(
        ["90.BK0477"], start=date(2026, 9, 1), end=date(2026, 9, 2)
    )
    assert len(rows) == 2
    assert rows[0]["sector_code"] == "BK0477"
    assert rows[0]["source"] == "replay"
    assert rows[0]["asset_type"] == "sector"
    assert rows[0]["main_net"] == 350000000.0
    assert rows[0]["change_pct"] == 1.25
    assert rows[1]["main_net"] == -120000000.0
    assert set(SECTOR_FUND_FLOW_COLUMNS) <= set(rows[0].keys())


def test_replay_sector_fund_flow_missing_fixture() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    with pytest.raises(SymbolError, match="no sector_fund_flow fixture"):
        provider.get_sector_fund_flow(["BK9999"])


def test_normalize_sector_fund_flow_requires_date() -> None:
    with pytest.raises(ValueError, match="missing date"):
        normalize_sector_fund_flow_row(
            {"sector_code": "BK0477", "main_net": 1.0},
            source="test",
        )


def test_replay_news() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    rows = provider.get_news(
        ["SH600519"], start=date(2026, 9, 1), end=date(2026, 9, 2)
    )
    assert len(rows) == 2
    assert rows[0]["symbol"] == "600519"
    assert rows[0]["source"] == "replay"
    assert rows[0]["title"].startswith("贵州茅台")
    assert rows[0]["sentiment"] == 0.35
    assert rows[1]["sentiment"] is None
    assert set(NEWS_COLUMNS) <= set(rows[0].keys())


def test_replay_news_missing_fixture() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    with pytest.raises(SymbolError, match="no news fixture"):
        provider.get_news(["000001"])


def test_normalize_news_requires_title() -> None:
    with pytest.raises(ValueError, match="missing title"):
        normalize_news_row(
            {"symbol": "600519", "date": "2026-09-01"},
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
