"""Unit tests for apply_adjust (deterministic, no HTTP)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from stock_platform_providers.adjust import apply_adjust
from stock_platform_providers.replay import ReplayProvider, ReplayTransport

FIXTURES = Path(__file__).parent / "fixtures"


def test_qfq_divides_historical_close() -> None:
    # a-stock-data §1.4: 2015-01-05 不复权 202.52 / 1.4118 ≈ 143.46
    bars = [{"date": "2015-01-05", "close": 202.52, "volume": 1000}]
    factors = [{"trade_date": "2015-01-05", "ex_factor": 1.4118}]
    out = apply_adjust(bars, factors, kind="qfq")
    assert len(out) == 1
    assert out[0]["close"] == round(202.52 / 1.4118, 4)
    assert out[0]["volume"] == 1000
    assert out[0]["ex_factor"] == 1.4118
    assert out[0]["adjust_kind"] == "qfq"


def test_hfq_multiplies() -> None:
    bars = [{"date": "2015-01-05", "close": 202.52}]
    factors = [{"date": "2015-01-05", "factor": 6.291}]
    out = apply_adjust(bars, factors, kind="hfq")
    assert out[0]["close"] == round(202.52 * 6.291, 4)
    assert out[0]["adjust_kind"] == "hfq"


def test_qfq_times_is_wrong_direction() -> None:
    raw = 202.52
    factor = 1.4118
    qfq = apply_adjust([{"date": "2015-01-05", "close": raw}], [{"date": "2015-01-05", "factor": factor}], kind="qfq")
    assert qfq[0]["close"] != round(raw * factor, 4)
    assert qfq[0]["close"] == round(raw / factor, 4)


def test_empty_factors_fail_closed() -> None:
    with pytest.raises(ValueError, match="empty"):
        apply_adjust([{"date": "2026-09-01", "close": 1410.0}], [])


def test_empty_bars_ok() -> None:
    assert apply_adjust([], [{"trade_date": "1900-01-01", "ex_factor": 1.0}]) == []


def test_bar_before_first_factor_fails() -> None:
    with pytest.raises(ValueError, match="earlier"):
        apply_adjust(
            [{"date": "1899-12-31", "close": 1.0}],
            [{"trade_date": "1900-01-01", "ex_factor": 1.0}],
        )


def test_zero_factor_fails() -> None:
    with pytest.raises(ValueError, match="is 0"):
        apply_adjust(
            [{"date": "2026-09-01", "close": 10.0}],
            [{"trade_date": "2026-09-01", "ex_factor": 0}],
        )


def test_step_function_uses_latest_not_after_bar() -> None:
    bars = [
        {"date": "2024-01-01", "close": 100.0},
        {"date": "2026-07-01", "close": 200.0},
    ]
    factors = [
        {"trade_date": "1900-01-01", "ex_factor": 2.0},
        {"trade_date": "2026-06-26", "ex_factor": 1.0},
    ]
    out = apply_adjust(bars, factors, kind="qfq")
    assert out[0]["close"] == 50.0
    assert out[0]["ex_factor"] == 2.0
    assert out[1]["close"] == 200.0
    assert out[1]["ex_factor"] == 1.0


def test_mixed_symbols_require_factor_symbol() -> None:
    with pytest.raises(ValueError, match="mixed-symbol"):
        apply_adjust(
            [
                {"symbol": "600519", "date": "2026-09-01", "close": 1.0},
                {"symbol": "000001", "date": "2026-09-01", "close": 2.0},
            ],
            [{"trade_date": "1900-01-01", "ex_factor": 1.0}],
        )


def test_replay_daily_qfq_latest_factor_is_one() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    daily = provider.get_daily(
        ["600519"], start=date(2026, 9, 1), end=date(2026, 9, 2)
    )
    factors = provider.get_adj_factor(["600519"], kind="qfq")
    out = apply_adjust(daily, factors, kind="qfq")
    assert len(out) == len(daily)
    # Sep-2026 bars sit after the latest qfq factor date (2026-06-26 → 1.0)
    assert all(row["ex_factor"] == 1.0 for row in out)
    assert out[0]["close"] == daily[0]["close"]
    assert out[0]["volume"] == daily[0]["volume"]


def test_does_not_mutate_input() -> None:
    bars = [{"date": "2015-01-05", "close": 202.52}]
    factors = [{"trade_date": "2015-01-05", "ex_factor": 2.0}]
    apply_adjust(bars, factors, kind="qfq")
    assert bars[0]["close"] == 202.52
