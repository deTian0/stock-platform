"""Offline paper-cabin buy/sell/positions (SIMULATE, no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stock_platform_execution.paper_cabin import (
    hydrate_broker,
    load_state,
    resolve_fill_price,
    save_state,
)
from stock_platform_execution.paper_cli import main


NOW = "2026-09-07T09:40:00+08:00"
SIGNAL = "2026-09-04"


def test_resolve_fill_price_explicit() -> None:
    px, src = resolve_fill_price("600519", price=12.5)
    assert px == 12.5
    assert src == "cli:--price"


def test_resolve_fill_price_requires_source() -> None:
    with pytest.raises(ValueError, match="缺少成交价"):
        resolve_fill_price("600519")


def test_cabin_buy_sell_positions_account_fills(tmp_path: Path, capsys) -> None:
    state = tmp_path / "cabin.json"

    rc = main(
        [
            "--state",
            str(state),
            "buy",
            "--symbol",
            "600519",
            "--qty",
            "100",
            "--price",
            "10",
            "--signal-date",
            SIGNAL,
            "--now",
            NOW,
        ]
    )
    assert rc == 0
    buy_out = json.loads(capsys.readouterr().out)
    assert buy_out["liveTradingEnabled"] is False
    assert buy_out["priceSource"] == "cli:--price"
    assert buy_out["execute"]["accepted"] is True
    assert any(p["symbol"] == "600519" and p["qty"] == 100 for p in buy_out["positions"])
    assert buy_out["account"]["cash"] == pytest.approx(1_000_000.0 - 1000.0)

    assert state.is_file()
    raw = json.loads(state.read_text(encoding="utf-8"))
    assert raw["cash"] == pytest.approx(999_000.0)
    assert "600519" in raw["positions"]

    assert main(["--state", str(state), "positions"]) == 0
    pos_out = json.loads(capsys.readouterr().out)
    assert pos_out["positions"][0]["qty"] == 100

    assert main(["--state", str(state), "account"]) == 0
    acct = json.loads(capsys.readouterr().out)["account"]
    assert acct["liveTradingEnabled"] is False
    assert acct["environment"] == "SIMULATE"

    assert main(["--state", str(state), "fills", "--limit", "5"]) == 0
    fills = json.loads(capsys.readouterr().out)["fills"]
    assert len(fills) == 1
    assert fills[0]["price"] == 10.0

    rc = main(
        [
            "--state",
            str(state),
            "sell",
            "--symbol",
            "600519",
            "--all",
            "--price",
            "11",
            "--signal-date",
            SIGNAL,
            "--now",
            NOW,
        ]
    )
    assert rc == 0
    sell_out = json.loads(capsys.readouterr().out)
    assert sell_out["positions"] == []
    assert sell_out["account"]["cash"] == pytest.approx(999_000.0 + 1100.0)

    broker = hydrate_broker(load_state(state))
    assert broker.get_positions() == []
    assert len(broker.get_fills()) == 2


def test_cabin_sell_refuses_without_position(tmp_path: Path) -> None:
    state = tmp_path / "empty.json"
    with pytest.raises(SystemExit, match="无持仓"):
        main(
            [
                "--state",
                str(state),
                "close",
                "--symbol",
                "600519",
                "--qty",
                "100",
                "--price",
                "10",
                "--signal-date",
                SIGNAL,
                "--now",
                NOW,
            ]
        )


def test_cabin_persist_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    state = load_state(path)
    broker = hydrate_broker(state)
    from datetime import datetime

    from stock_platform_execution.timing import CHINA_TZ

    now = datetime(2026, 9, 7, 9, 40, tzinfo=CHINA_TZ)
    draft = broker.build_draft(
        strategy_hash="h",
        signal_trade_date=SIGNAL,
        orders=[{"symbol": "510300", "side": "buy", "qty": 200, "price": 4.5}],
        now=now,
    )
    broker.execute_draft(draft["draftId"], now=now)
    from stock_platform_execution.paper_cabin import persist_broker

    persist_broker(state, broker)
    save_state(path, state)
    again = hydrate_broker(load_state(path))
    assert again.get_account().cash == pytest.approx(1_000_000.0 - 900.0)
    assert again.get_positions()[0].qty == 200
