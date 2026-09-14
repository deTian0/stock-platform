"""Strategy config versioning + PIT compare tests."""

from __future__ import annotations

import pandas as pd
import pytest

from stock_platform_research.strategy_config import (
    compare_strategy_configs,
    default_strategy_config_dir,
    list_strategy_configs,
    load_strategy_config,
    run_strategy_pit,
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


def test_load_packaged_configs() -> None:
    configs = list_strategy_configs()
    ids = {c["id"] for c in configs}
    assert "lvrev-default-v1" in ids
    assert "lvrev-rev-heavy-v1" in ids
    cfg = load_strategy_config(default_strategy_config_dir() / "lvrev-default-v1.json")
    assert cfg.version == "1"
    assert cfg.weights["vol"] == pytest.approx(0.5)


def test_compare_strategy_configs_deterministic() -> None:
    panel = _panel()
    a = default_strategy_config_dir() / "lvrev-default-v1.json"
    b = default_strategy_config_dir() / "lvrev-rev-heavy-v1.json"
    out = compare_strategy_configs(panel, a, b)
    assert out["liveTradingEnabled"] is False
    assert out["a"]["tradeCount"] >= 1
    assert out["b"]["tradeCount"] >= 1
    assert "deltaFinalEquity" in out
    assert out["winner"] in {
        "lvrev-default-v1",
        "lvrev-rev-heavy-v1",
        "tie",
    }


def test_run_strategy_pit_from_mapping() -> None:
    panel = _panel()
    result = run_strategy_pit(
        panel,
        {
            "id": "inline",
            "version": "0",
            "top_n": 1,
            "reversal_q": 0.5,
            "weights": {"vol": 0.5, "rev": 0.5, "value": 0, "q": 0, "g": 0},
        },
    )
    assert result["finalEquity"] > 0
    assert result["config"]["id"] == "inline"
