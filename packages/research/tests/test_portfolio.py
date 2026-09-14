"""Portfolio metrics + run_portfolio_pit (ADR 0043) — fixture panel only."""

from __future__ import annotations

import pandas as pd
import pytest

from stock_platform_research.portfolio import (
    approx_turnover_from_curve,
    max_drawdown_from_curve,
    portfolio_metrics,
    run_portfolio_pit,
)


def _tiny_panel() -> pd.DataFrame:
    rows = []
    for sym, closes, opens, vols, revs in [
        ("AAA", [10, 10.5, 11, 10.8], [10, 10.2, 10.8, 10.9], [0.1] * 4, [-0.1] * 4),
        ("BBB", [20, 19, 18, 17.5], [20, 19.5, 18.5, 18.0], [0.5] * 4, [0.05] * 4),
    ]:
        for i, d in enumerate(
            ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"]
        ):
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


def test_max_drawdown_and_turnover_helpers() -> None:
    curve = [
        {"trade_date": "2026-09-01", "equity": 1.0, "n_picks": 1},
        {"trade_date": "2026-09-02", "equity": 1.1, "n_picks": 2},
        {"trade_date": "2026-09-03", "equity": 0.99, "n_picks": 0},
    ]
    assert max_drawdown_from_curve(curve) == pytest.approx((0.99 / 1.1) - 1.0)
    # |2-1| + |0-2| = 3 over 2 steps → 1.5
    assert approx_turnover_from_curve(curve) == pytest.approx(1.5)


def test_portfolio_metrics_from_pit_shapes() -> None:
    metrics = portfolio_metrics(
        [{"trade_date": "d1", "equity": 1.05, "n_picks": 1}],
        [{"symbol": "AAA", "ret": 0.05}],
        final_equity=1.05,
    )
    assert metrics["n_trades"] == 1
    assert metrics["final_equity"] == pytest.approx(1.05)
    assert metrics["max_drawdown"] == pytest.approx(0.0)
    assert metrics["environment"] == "SIMULATE"
    assert metrics["liveTradingEnabled"] is False
    assert "equal-weight" in metrics["equal_weight_note"].lower()


def test_run_portfolio_pit_attaches_metrics() -> None:
    out = run_portfolio_pit(_tiny_panel(), top_n=1, reversal_q=0.5)
    assert "metrics" in out
    assert out["metrics"]["n_trades"] == len(out["trades"])
    assert out["metrics"]["final_equity"] == pytest.approx(out["final_equity"])
    assert out["environment"] == "SIMULATE"
    assert out["liveTradingEnabled"] is False
