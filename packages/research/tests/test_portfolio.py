"""Portfolio metrics + run_portfolio_pit (ADR 0043) — fixture panel only."""

from __future__ import annotations

import pandas as pd
import pytest

from stock_platform_research.portfolio import (
    approx_turnover_from_curve,
    compute_metrics,
    hhi,
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


# ---------- B2: concentration + notional turnover ----------


def test_hhi_shares_and_extremes() -> None:
    assert hhi([1, 1, 1, 1]) == pytest.approx(0.25)
    assert hhi([1.0]) == pytest.approx(1.0)
    assert hhi([]) == 0.0
    assert hhi([0.0, 0.0]) == 0.0
    # scale-free: raw market values == normalised weights
    assert hhi([200.0, 100.0]) == pytest.approx(hhi([2.0, 1.0]))


def test_compute_metrics_reports_b2_fields() -> None:
    curve = [
        {"equity": 100.0, "n_positions": 2, "hhi": 0.6, "top_weight": 0.7, "invested_ratio": 0.8},
        {"equity": 120.0, "n_positions": 2, "hhi": 0.5, "top_weight": 0.6, "invested_ratio": 0.9},
        {"equity": 90.0, "n_positions": 0, "hhi": 0.0, "top_weight": 0.0, "invested_ratio": 0.0},
    ]
    trades = [
        {"net_ret": 5.0, "held_days": 10, "entry_value": 1000.0, "exit_value": 1100.0},
        {"net_ret": -2.0, "held_days": 20, "entry_value": 1000.0, "exit_value": 980.0},
    ]
    m = compute_metrics(curve, trades, initial_capital=100.0)
    assert m["n_days"] == 3
    assert m["max_drawdown"] == pytest.approx(-0.25, abs=1e-6)
    assert m["avg_hhi"] == pytest.approx((0.6 + 0.5 + 0.0) / 3, abs=1e-6)
    assert m["avg_top_weight"] == pytest.approx((0.7 + 0.6 + 0.0) / 3, abs=1e-6)
    assert m["avg_invested_ratio"] == pytest.approx((0.8 + 0.9 + 0.0) / 3, abs=1e-6)
    assert m["avg_positions"] == pytest.approx(4 / 3, abs=1e-4)
    assert m["max_positions"] == 2
    assert m["turnover_notional_per_year"] is not None
    assert m["turnover_notional_per_year"] > 0


def test_compute_metrics_missing_b2_fields_are_none() -> None:
    m = compute_metrics([{"equity": 100.0}, {"equity": 101.0}], [], initial_capital=100.0)
    assert m["avg_hhi"] is None
    assert m["avg_top_weight"] is None
    assert m["avg_invested_ratio"] is None
    assert m["avg_positions"] is None
    assert m["max_positions"] == 0
    assert m["turnover_notional_per_year"] is None


def test_compute_metrics_empty_keeps_b2_keys() -> None:
    m = compute_metrics([], [], initial_capital=50000.0)
    assert m["n_days"] == 0
    assert m["turnover_notional_per_year"] is None
    assert m["avg_hhi"] is None
    assert m["avg_top_weight"] is None
    assert m["avg_invested_ratio"] is None
    assert m["avg_positions"] is None
    assert m["max_positions"] == 0


def test_portfolio_metrics_carry_core_block() -> None:
    out = portfolio_metrics(
        [{"trade_date": "d1", "equity": 1.0, "n_picks": 0},
         {"trade_date": "d2", "equity": 1.1, "n_picks": 1}],
        [],
        final_equity=1.1,
    )
    assert out["cagr"] == pytest.approx(1.1 ** (252 / 2) - 1, rel=1e-3)
    assert "sharpe" in out and "sortino" in out and "calmar" in out
    assert out["n_days"] == 2
