"""Tests for the B3 cost / friction model (``portfolio.CostModel``).

Two things are pinned here:

1. **Semantics** — proportional rate, currency-cost floor, slipped fill price,
   ``zero()``, and the ``costs == notional × trade_cost`` identity when no floor
   is set.
2. **Cross-line alignment** — the platform's rates and ETF prefix table must
   match ``a-stock-engine/local_backtest.py``. The engine module is *parsed
   statically* — never imported: it belongs to another repo and touches SQLite at
   construction time. When the engine file is absent (CI, another machine) the
   alignment tests **skip** rather than fail.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from stock_platform_research import backtest, portfolio
from stock_platform_research.portfolio import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_STAMP_SELL_RATE,
    CostModel,
    trade_cost,
)

ENGINE_PATH_ENV = "STOCK_PLATFORM_ENGINE_REPO"
DEFAULT_ENGINE_PATH = Path(r"D:\workspace\stock_trading\a-stock-engine\local_backtest.py")

MIXED_CODES = ("600519.SH", "000001.SZ", "510300.SH", "159915.SZ", "159915")


def _engine_source() -> str:
    raw = os.environ.get(ENGINE_PATH_ENV)
    path = Path(raw) if raw else DEFAULT_ENGINE_PATH
    if path.is_dir():
        path = path / "local_backtest.py"
    if not path.is_file():
        pytest.skip(f"engine reference file not found: {path}")
    return path.read_text(encoding="utf-8")


def _engine_rates(text: str) -> tuple[float, float]:
    comm = re.search(r"^COMMISSION_RATE\s*=\s*([0-9.eE+-]+)", text, re.M)
    stamp = re.search(r"^STAMP_SELL_RATE\s*=\s*([0-9.eE+-]+)", text, re.M)
    assert comm and stamp, "engine rate constants not found"
    return float(comm.group(1)), float(stamp.group(1))


def _engine_etf_prefixes(text: str) -> set[str]:
    block = re.search(r"def _is_etf\(.*?(?=\n    @staticmethod)", text, re.S)
    assert block, "engine _is_etf not found"
    prefixes = set(re.findall(r'"(\d+)"', block.group(0)))
    assert prefixes, "engine ETF prefixes not found"
    return prefixes


# ---------- cross-line alignment (engine reference) ----------

def test_engine_rate_constants_match_platform_defaults():
    comm, stamp = _engine_rates(_engine_source())
    assert DEFAULT_COMMISSION_RATE == pytest.approx(comm)
    assert DEFAULT_STAMP_SELL_RATE == pytest.approx(stamp)


def test_etf_prefix_table_matches_engine():
    assert set(portfolio._ETF_PREFIXES) == _engine_etf_prefixes(_engine_source())


def test_trade_cost_matches_engine_in_all_quadrants():
    text = _engine_source()
    comm, stamp = _engine_rates(text)
    prefixes = tuple(_engine_etf_prefixes(text))

    def engine_trade_cost(code: str, is_buy: bool) -> float:
        c = code.replace(".", "")[:6]
        if c.startswith(prefixes):
            return comm
        return comm if is_buy else comm + stamp

    model = CostModel(commission_rate=comm, stamp_sell_rate=stamp)
    for code in MIXED_CODES:
        for is_buy in (True, False):
            assert model.trade_cost(code, is_buy=is_buy) == pytest.approx(
                engine_trade_cost(code, is_buy)
            )


# ---------- semantics ----------

def test_default_model_rates():
    m = CostModel()
    assert m.trade_cost("600519.SH", is_buy=True) == pytest.approx(DEFAULT_COMMISSION_RATE)
    assert m.trade_cost("600519.SH", is_buy=False) == pytest.approx(
        DEFAULT_COMMISSION_RATE + DEFAULT_STAMP_SELL_RATE
    )
    # ETF: commission only, no stamp duty
    assert m.trade_cost("510300.SH", is_buy=False) == pytest.approx(DEFAULT_COMMISSION_RATE)


def test_slippage_moves_fill_price_both_ways():
    slipped = CostModel(slippage_bps=10.0)  # 10 bp = 0.1%
    assert slipped.fill_price(100.0, is_buy=True) == pytest.approx(100.1)
    assert slipped.fill_price(100.0, is_buy=False) == pytest.approx(99.9)
    flat = CostModel()
    assert flat.fill_price(100.0, is_buy=True) == 100.0
    assert flat.fill_price(100.0, is_buy=False) == 100.0


def test_costs_apply_commission_floor():
    plain = CostModel()
    assert plain.costs(10_000.0, "600519.SH", is_buy=True) == pytest.approx(
        10_000.0 * DEFAULT_COMMISSION_RATE
    )
    assert plain.costs(10_000.0, "600519.SH", is_buy=False) == pytest.approx(
        10_000.0 * (DEFAULT_COMMISSION_RATE + DEFAULT_STAMP_SELL_RATE)
    )
    assert plain.costs(10_000.0, "510300.SH", is_buy=False) == pytest.approx(
        10_000.0 * DEFAULT_COMMISSION_RATE
    )
    # a ¥5 floor only bites on small tickets
    floored = CostModel(min_commission=5.0)
    assert floored.costs(1_000.0, "600519.SH", is_buy=True) == pytest.approx(5.0)
    assert floored.costs(1_000_000.0, "600519.SH", is_buy=True) == pytest.approx(
        1_000_000.0 * DEFAULT_COMMISSION_RATE
    )
    # non-positive notional never fabricates a cost
    assert plain.costs(0.0, "600519.SH", is_buy=True) == 0.0
    assert plain.costs(-100.0, "600519.SH", is_buy=False) == 0.0


def test_costs_equals_rate_times_notional_without_floor():
    m = CostModel()
    for code in ("600519.SH", "510300.SH"):
        for is_buy in (True, False):
            notional = 12_345.0
            assert m.costs(notional, code, is_buy=is_buy) == pytest.approx(
                notional * m.trade_cost(code, is_buy=is_buy)
            )


def test_zero_model_is_all_in_zero():
    z = CostModel.zero()
    assert z.slippage_bps == 0.0
    assert z.min_commission == 0.0
    assert z.trade_cost("600519.SH", is_buy=False) == 0.0
    assert z.costs(10_000.0, "600519.SH", is_buy=False) == 0.0
    assert z.fill_price(9.99, is_buy=True) == 9.99


def test_module_trade_cost_delegates_to_cost_model():
    assert trade_cost("600519.SH", is_buy=False) == pytest.approx(
        CostModel().trade_cost("600519.SH", is_buy=False)
    )
    assert trade_cost(
        "600519.SH", is_buy=False, commission_rate=0.001, stamp_sell_rate=0.0
    ) == pytest.approx(0.001)


def test_cost_model_is_single_definition_across_modules():
    assert backtest.CostModel is portfolio.CostModel
    assert backtest.trade_cost is portfolio.trade_cost
    assert backtest.is_etf is portfolio.is_etf
    assert backtest.is_fund is portfolio.is_fund
    assert backtest.norm_code is portfolio.norm_code
    assert backtest.DEFAULT_COMMISSION_RATE == portfolio.DEFAULT_COMMISSION_RATE
    assert backtest.DEFAULT_STAMP_SELL_RATE == portfolio.DEFAULT_STAMP_SELL_RATE
