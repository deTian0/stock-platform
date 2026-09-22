"""M-R5 strategy A/B sidecar tests (default off; zero public net)."""

from __future__ import annotations

import pandas as pd
import pytest

from stock_platform_research.strategy_ab import (
    attach_strategy_ab,
    run_strategy_ab_sidecar,
    strategy_ab_enabled,
    strategy_ab_status,
)


def _panel() -> pd.DataFrame:
    rows = []
    for sym, closes, opens, vols, revs in [
        ("AAA", [10, 10.5, 11], [10, 10.2, 10.8], [0.1, 0.1, 0.1], [-0.1, -0.1, -0.1]),
        ("BBB", [20, 19, 18], [20, 19.5, 18.5], [0.5, 0.5, 0.5], [0.05, 0.05, 0.05]),
    ]:
        for i, d in enumerate(["2026-09-01", "2026-09-02", "2026-09-03"]):
            rows.append(
                {
                    "trade_date": d,
                    "symbol": sym,
                    "open": opens[i],
                    "close": closes[i],
                    "vol20": vols[i],
                    "rev_chg": revs[i],
                    "ma20": closes[i],
                    "ma60": closes[i] * 0.9,
                }
            )
    return pd.DataFrame(rows)


def test_strategy_ab_default_off() -> None:
    assert strategy_ab_enabled(env={}) is False
    assert strategy_ab_status(env={})["enabled"] is False
    assert strategy_ab_status(env={})["defaultOnDailyPath"] is False


def test_strategy_ab_env_on() -> None:
    assert strategy_ab_enabled(env={"STOCK_PLATFORM_STRATEGY_AB": "1"}) is True
    assert strategy_ab_enabled(env={}, request_flag=True) is True


def test_run_strategy_ab_sidecar() -> None:
    out = run_strategy_ab_sidecar(_panel(), panel_source="fixture")
    assert out["ok"] is True
    assert out["replacesPicks"] is False
    assert out["liveTradingEnabled"] is False
    assert out["winner"] in {"lvrev-default-v1", "lvrev-rev-heavy-v1", "tie"}


def test_attach_strategy_ab_mutates_brief() -> None:
    brief: dict = {"picks": [{"symbol": "AAA"}], "asof": "2026-09-03"}
    attach_strategy_ab(brief, _panel(), panel_source="fixture")
    assert brief["strategyAb"]["ok"] is True
    assert brief["picks"][0]["symbol"] == "AAA"
