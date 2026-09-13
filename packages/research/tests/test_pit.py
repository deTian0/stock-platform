"""PIT backtest / no-lookahead guards."""

from __future__ import annotations

import pandas as pd
import pytest

from stock_platform_research import assert_no_lookahead_columns, run_pit_long_only


def test_assert_no_lookahead_rejects_fwd() -> None:
    with pytest.raises(ValueError, match="lookahead"):
        assert_no_lookahead_columns(["vol20", "fwd_ret_1d"])


def test_run_pit_long_only_uses_next_open_fill() -> None:
    # Two symbols × three days. Features as-of T; fill at T+1 open.
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
    panel = pd.DataFrame(rows)
    result = run_pit_long_only(panel, top_n=1, reversal_q=0.5)
    assert result["n_dates"] == 3
    assert result["trades"], "expected at least one trade"
    # AAA should win gates (lower vol + deeper drawdown)
    assert all(t["symbol"] == "AAA" for t in result["trades"])
    # First signal day close 10 → next open 10.2
    t0 = result["trades"][0]
    assert t0["signal_close"] == 10
    assert t0["fill_open"] == pytest.approx(10.2)
    assert t0["ret"] == pytest.approx(0.02)


def test_run_pit_rejects_panel_with_lookahead_features() -> None:
    panel = pd.DataFrame(
        {
            "trade_date": ["2026-09-01", "2026-09-02"],
            "symbol": ["A", "A"],
            "open": [1, 1],
            "close": [1, 1],
            "vol20": [0.1, 0.1],
            "rev_chg": [-0.1, -0.1],
            "ma20": [2, 2],
            "ma60": [1, 1],
            "fwd_ret_1d": [0.1, 0.1],
        }
    )
    with pytest.raises(ValueError, match="lookahead"):
        run_pit_long_only(panel, feature_columns=["vol20", "rev_chg", "fwd_ret_1d"])
