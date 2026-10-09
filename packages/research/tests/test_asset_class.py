"""Tests for the B4 asset-class layer (``portfolio.asset_class`` + ``by_asset``).

Three things are pinned:

1. **Semantics** — ``asset_class`` maps a code to ``stock`` / ``etf`` / ``fund``
   off the same prefix tables that drive the ETF stamp exemption, so the two can
   never drift apart.
2. **Cross-line alignment** — the platform's ``is_fund`` / ``is_etf`` prefix
   tables must match ``a-stock-engine/local_backtest.py`` (``_is_fund`` /
   ``_is_etf``). The engine module is *parsed statically* — never imported: it
   belongs to another repo and touches SQLite at construction time. When the
   engine file is absent (CI, another machine) the alignment tests **skip**.
3. **Reporting** — ``compute_metrics(...)["by_asset"]`` splits a mixed book's
   trade log by class without fabricating a bucket for trades that carry neither
   a ``code`` nor an ``asset_class``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from stock_platform_research import backtest, portfolio
from stock_platform_research.portfolio import asset_class, compute_metrics, is_etf, is_fund

ENGINE_PATH_ENV = "STOCK_PLATFORM_ENGINE_REPO"
DEFAULT_ENGINE_PATH = Path(r"D:\workspace\stock_trading\a-stock-engine\local_backtest.py")


def _engine_source() -> str:
    raw = os.environ.get(ENGINE_PATH_ENV)
    path = Path(raw) if raw else DEFAULT_ENGINE_PATH
    if path.is_dir():
        path = path / "local_backtest.py"
    if not path.is_file():
        pytest.skip(f"engine reference file not found: {path}")
    return path.read_text(encoding="utf-8")


def _engine_is_fund_prefixes(text: str) -> set[str]:
    block = re.search(r"def _is_fund\(.*?(?=\n    @staticmethod)", text, re.S)
    assert block, "engine _is_fund not found"
    prefixes = set(re.findall(r'"(\d)"', block.group(0)))
    assert prefixes, "engine _is_fund prefixes not found"
    return prefixes


def _engine_is_etf_prefixes(text: str) -> set[str]:
    block = re.search(r"def _is_etf\(.*?(?=\n    @staticmethod)", text, re.S)
    assert block, "engine _is_etf not found"
    prefixes = set(re.findall(r'"(\d+)"', block.group(0)))
    assert prefixes, "engine ETF prefixes not found"
    return prefixes


# ---------- semantics ----------

def test_asset_class_three_way():
    assert asset_class("600519.SH") == "stock"
    assert asset_class("000001.SZ") == "stock"
    assert asset_class("300750.SZ") == "stock"
    assert asset_class("688981.SH") == "stock"
    # ETFs (in the prefix table) — stamp exempt
    assert asset_class("510300.SH") == "etf"
    assert asset_class("159915.SZ") == "etf"
    assert asset_class("159915") == "etf"
    # on-exchange fund NOT in the ETF table (e.g. convertible bond 12xxxx) → fund
    assert asset_class("123456.SZ") == "fund"
    assert asset_class("110000.SH") == "fund"


def test_asset_class_is_consistent_with_prefix_tables():
    for code in ("600519.SH", "000001.SZ", "510300.SH", "159915.SZ", "123456.SZ"):
        ac = asset_class(code)
        if ac == "etf":
            assert is_etf(code) and is_fund(code)
        elif ac == "fund":
            assert is_fund(code) and not is_etf(code)
        else:
            assert not is_fund(code) and not is_etf(code)


def test_asset_class_single_definition_across_modules():
    assert backtest.asset_class is portfolio.asset_class
    assert "asset_class" in backtest.__dict__
    # exported from the package root too
    import stock_platform_research as spr

    assert spr.asset_class is portfolio.asset_class
    assert spr.UNIVERSES == ("stock", "etf", "all")


# ---------- cross-line alignment (engine reference) ----------

def test_is_fund_prefixes_match_engine():
    engine = _engine_is_fund_prefixes(_engine_source())
    platform = {"1", "5"}  # portfolio.is_fund docstring contract
    assert platform == engine


def test_etf_prefix_table_still_matches_engine():
    assert set(portfolio._ETF_PREFIXES) == _engine_is_etf_prefixes(_engine_source())


def test_asset_class_agrees_with_engine_classifier():
    text = _engine_source()
    fund_prefixes = tuple(_engine_is_fund_prefixes(text))
    etf_prefixes = tuple(_engine_is_etf_prefixes(text))

    def engine_class(code: str) -> str:
        c = code.replace(".", "")[:6]
        if c.startswith(etf_prefixes):
            return "etf"
        if c.startswith(fund_prefixes):
            return "fund"
        return "stock"

    for code in ("600519.SH", "000001.SZ", "510300.SH", "159915.SZ", "123456.SZ"):
        assert asset_class(code) == engine_class(code)


# ---------- by_asset reporting ----------

def test_by_asset_splits_mixed_trade_log():
    curve = [{"equity": 100.0}]
    trades = [
        {"code": "600519.SH", "net_ret": 5.0, "entry_value": 1000.0, "exit_value": 1100.0},
        {"code": "510300.SH", "net_ret": -2.0, "entry_value": 1000.0, "exit_value": 980.0},
        {"code": "510300.SH", "net_ret": 3.0, "entry_value": 1000.0, "exit_value": 1030.0},
    ]
    by_asset = compute_metrics(curve, trades, initial_capital=100.0)["by_asset"]
    assert set(by_asset) == {"stock", "etf"}
    assert by_asset["stock"]["n_trades"] == 1
    assert by_asset["stock"]["win_rate"] == pytest.approx(1.0)
    assert by_asset["etf"]["n_trades"] == 2
    assert by_asset["etf"]["win_rate"] == pytest.approx(0.5)
    assert by_asset["etf"]["avg_net_ret"] == pytest.approx(0.5)
    # notional = entry + exit for each leg in the bucket
    assert by_asset["etf"]["turnover_notional"] == pytest.approx(4010.0)
    assert by_asset["stock"]["turnover_notional"] == pytest.approx(2100.0)


def test_by_asset_prefers_explicit_field():
    trades = [{"code": "510300.SH", "asset_class": "stock", "net_ret": 1.0}]
    by_asset = compute_metrics([{"equity": 100.0}], trades, initial_capital=100.0)["by_asset"]
    assert set(by_asset) == {"stock"}


def test_by_asset_empty_and_unattributable():
    # no trades → empty
    assert compute_metrics([{"equity": 100.0}], [], initial_capital=100.0)["by_asset"] == {}
    # a trade with neither code nor asset_class is skipped, not bucketed as junk
    trades = [{"symbol": "AAA", "net_ret": 1.0}]
    assert compute_metrics([{"equity": 100.0}], trades, initial_capital=100.0)["by_asset"] == {}
    # empty input keeps the key present
    assert compute_metrics([], [], initial_capital=1.0)["by_asset"] == {}
