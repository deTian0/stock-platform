"""Portfolio metrics + run_portfolio_pit (ADR 0043) — fixture panel only."""

from __future__ import annotations

import pandas as pd
import pytest

from stock_platform_research.portfolio import (
    approx_turnover_from_curve,
    compute_metrics,
    drawdown_series,
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


def test_drawdown_series_is_index_aligned_and_non_positive() -> None:
    curve = [
        {"date": "d1", "equity": 1.0},
        {"date": "d2", "equity": 1.1},
        {"date": "d3", "equity": 0.99},
        {"date": "d4", "equity": 0.88},
    ]
    series = drawdown_series(curve)
    assert len(series) == len(curve)  # index-aligned for the workbench table
    assert [p["date"] for p in series] == ["d1", "d2", "d3", "d4"]
    assert all(p["drawdown"] <= 0 for p in series)
    assert series[0]["drawdown"] == pytest.approx(0.0)
    assert series[1]["drawdown"] == pytest.approx(0.0)  # new high → no drawdown
    assert series[2]["drawdown"] == pytest.approx((0.99 / 1.1) - 1.0)
    assert series[3]["drawdown"] == pytest.approx((0.88 / 1.1) - 1.0)


def test_max_drawdown_is_deepest_point_of_series() -> None:
    curve = [
        {"date": "d1", "equity": 1.0},
        {"date": "d2", "equity": 0.9},
        {"date": "d3", "equity": 1.2},
        {"date": "d4", "equity": 1.02},
    ]
    series = drawdown_series(curve)
    assert max_drawdown_from_curve(curve) == pytest.approx(
        min(p["drawdown"] for p in series)
    )


def test_drawdown_series_skips_non_positive_but_stays_aligned() -> None:
    curve = [
        {"date": "d1", "equity": 1.0},
        {"date": "d2", "equity": 0.85},
        {"date": "d3", "equity": 0.0},  # suspended: repeats previous depth
        {"date": "d4", "equity": 1.0},
    ]
    series = drawdown_series(curve)
    assert len(series) == 4
    assert series[1]["drawdown"] == pytest.approx(-0.15)
    assert series[2]["drawdown"] == pytest.approx(-0.15)  # unchanged by the skip
    assert series[3]["drawdown"] == pytest.approx(0.0)
    assert max_drawdown_from_curve(curve) == pytest.approx(-0.15)


def test_drawdown_series_empty_and_flat() -> None:
    assert drawdown_series([]) == []
    assert max_drawdown_from_curve([]) == 0.0
    flat = [{"date": "d1", "equity": 2.0}, {"date": "d2", "equity": 2.0}]
    assert [p["drawdown"] for p in drawdown_series(flat)] == [0.0, 0.0]


def _pre_b6_max_drawdown(equity_curve) -> float:
    """Exact pre-``B6`` implementation, kept as an oracle for the refactor."""
    peak = 1.0
    max_dd = 0.0
    for point in equity_curve:
        eq = float(point.get("equity") or 0.0)
        if eq <= 0:
            continue
        if eq > peak:
            peak = eq
        if peak:
            max_dd = min(max_dd, (eq / peak) - 1.0)
    return max_dd


def test_max_drawdown_matches_pre_b6_oracle() -> None:
    # 600 pseudo-random-but-deterministic points with suspensions mixed in.
    curve = []
    eq = 1.0
    for i in range(600):
        eq = eq * (1.0 + (((i * 37) % 17) - 8) / 400.0)
        if i % 53 == 0:
            curve.append({"date": "s%d" % i, "equity": 0.0})  # suspended
        else:
            curve.append({"date": "d%d" % i, "equity": eq})
    assert max_drawdown_from_curve(curve) == _pre_b6_max_drawdown(curve)
    assert max_drawdown_from_curve(curve) == pytest.approx(
        min(p["drawdown"] for p in drawdown_series(curve))
    )
