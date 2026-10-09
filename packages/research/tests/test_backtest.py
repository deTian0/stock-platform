"""Tests for the B1 portfolio backtest engine (positions / costs / metrics)."""

from __future__ import annotations

import pandas as pd
import pytest

from stock_platform_research.backtest import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_STAMP_SELL_RATE,
    asset_class,
    compute_features,
    compute_metrics,
    is_etf,
    is_fund,
    norm_code,
    run_portfolio_backtest,
    trade_cost,
)


def _make_bars(series: dict[str, list[float]], start: str = "2023-01-02") -> pd.DataFrame:
    n = len(next(iter(series.values())))
    days = pd.bdate_range(start, periods=n)
    rows = []
    for code, prices in series.items():
        prev = None
        for d, p in zip(days, prices):
            pct = 0.0 if prev in (None, 0) else (p / prev - 1.0)
            rows.append(
                {
                    "code": code,
                    "date": d.date().isoformat(),
                    "close": float(p),
                    "pct_chg": float(pct),
                }
            )
            prev = p
    return pd.DataFrame(rows)


# ---------- code helpers ----------

def test_norm_code_strips_market_suffix():
    assert norm_code("600519.SH") == "600519"
    assert norm_code("000001.SZ") == "000001"
    assert norm_code("000001") == "000001"


def test_is_fund_and_is_etf_prefixes():
    assert is_fund("510300.SH") is True
    assert is_fund("159915.SZ") is True
    assert is_fund("600519.SH") is False
    assert is_etf("510300.SH") is True
    assert is_etf("159915.SZ") is True
    assert is_etf("600519.SH") is False


def test_trade_cost_stocks_vs_etf():
    # stock: commission both sides, stamp duty sell-only
    assert trade_cost("600519.SH", is_buy=True) == pytest.approx(DEFAULT_COMMISSION_RATE)
    assert trade_cost("600519.SH", is_buy=False) == pytest.approx(
        DEFAULT_COMMISSION_RATE + DEFAULT_STAMP_SELL_RATE
    )
    # ETF: commission only, no stamp duty
    assert trade_cost("510300.SH", is_buy=False) == pytest.approx(DEFAULT_COMMISSION_RATE)


# ---------- features ----------

def test_compute_features_shapes_and_columns():
    bars = _make_bars({"600519.SH": [10.0 + 0.01 * i for i in range(80)]})
    feats = compute_features(bars)
    for col in ("trade_date", "ret1", "vol20", "rev_chg", "ma20", "ma60"):
        assert col in feats.columns
    # ma60 needs a full 60-bar history -> first 59 rows NaN
    assert feats["ma60"].isna().sum() == 59
    assert feats["ma60"].notna().sum() == 80 - 59


def test_compute_features_requires_columns():
    with pytest.raises(ValueError, match="missing columns"):
        compute_features(pd.DataFrame({"code": ["600519.SH"], "close": [1.0]}))


# ---------- metrics ----------

def test_compute_metrics_empty_is_all_zero():
    m = compute_metrics([], [], initial_capital=50000.0)
    assert m["n_days"] == 0
    assert m["total_return"] == 0.0
    assert m["sharpe"] == 0.0
    assert m["n_trades"] == 0


def test_compute_metrics_monotonic_curve():
    curve = [{"equity": 100.0 * (1.01 ** i)} for i in range(60)]
    m = compute_metrics(curve, [], initial_capital=100.0)
    assert m["n_days"] == 60
    assert m["total_return"] > 0
    assert m["max_drawdown"] == 0.0  # never below the running peak
    assert m["sharpe"] > 0


def test_compute_metrics_drawdown_is_negative():
    curve = [
        {"equity": 100.0},
        {"equity": 120.0},
        {"equity": 90.0},  # -25% from peak 120
        {"equity": 110.0},
    ]
    m = compute_metrics(curve, [], initial_capital=100.0)
    assert m["max_drawdown"] == pytest.approx(-0.25, abs=1e-6)


# ---------- engine ----------

def test_backtest_runs_and_returns_contract():
    series = {
        "600519.SH": [10.0 * (1.0 + 0.002 * i) for i in range(200)],
        "000001.SZ": [8.0 * (1.0 + 0.001 * i) for i in range(200)],
    }
    bars = _make_bars(series)
    res = run_portfolio_backtest(
        bars,
        initial_capital=50000.0,
        min_pick_score=0.0,
        min_hold=5,
        max_positions=5,
        max_picks_per_day=2,
    )
    assert res["ok"] is True
    assert res["environment"] == "SIMULATE"
    assert res["liveTradingEnabled"] is False
    assert res["n_days"] > 0
    assert len(res["equity_curve"]) == res["n_days"]
    assert res["metrics"]["n_days"] == res["n_days"]
    assert res["params"]["min_hold"] == 5


def test_backtest_never_holds_more_than_max_positions():
    series = {
        f"60000{j}.SH": [10.0 * (1.0 + 0.001 * i + 0.0005 * j) for i in range(160)]
        for j in range(6)
    }
    bars = _make_bars(series)
    res = run_portfolio_backtest(
        bars, min_pick_score=0.0, min_hold=3, max_positions=2, max_picks_per_day=6
    )
    for point in res["equity_curve"]:
        assert point["n_positions"] <= 2


def test_backtest_regime_false_blocks_entries():
    series = {"600519.SH": [10.0 * (1.0 + 0.002 * i) for i in range(160)]}
    bars = _make_bars(series)
    res = run_portfolio_backtest(bars, min_pick_score=0.0, regime={})  # all days default True
    assert res["ok"] is True
    # explicit all-False regime -> never enters
    dates = {d: False for d in bars["date"].unique()}
    res2 = run_portfolio_backtest(bars, min_pick_score=0.0, regime=dates)
    assert res2["metrics"]["n_trades"] == 0
    assert res2["final_equity"] == pytest.approx(50000.0)


def test_backtest_excludes_funds_by_default():
    series = {
        "600519.SH": [10.0 * (1.0 + 0.002 * i) for i in range(160)],
        "510300.SH": [4.0 * (1.0 + 0.002 * i) for i in range(160)],
    }
    bars = _make_bars(series)
    res = run_portfolio_backtest(bars, min_pick_score=0.0)
    entered = {t["code"] for t in res["trades"]}
    assert "510300.SH" not in entered


def test_backtest_empty_range_is_fail_closed():
    bars = _make_bars({"600519.SH": [10.0 + i for i in range(80)]})
    res = run_portfolio_backtest(bars, start="2030-01-01", end="2030-12-31")
    assert res["ok"] is False
    assert "no bars" in res["reason"]
    assert res["metrics"]["n_days"] == 0


# ---------- B2: concentration scalars + notional turnover ----------

def test_backtest_curve_carries_concentration_scalars():
    series = {
        "600519.SH": [10.0 * (1.0 + 0.002 * i) for i in range(200)],
        "000001.SZ": [8.0 * (1.0 + 0.001 * i) for i in range(200)],
    }
    bars = _make_bars(series)
    res = run_portfolio_backtest(
        bars, min_pick_score=0.0, min_hold=5, max_positions=5, max_picks_per_day=2
    )
    for point in res["equity_curve"]:
        assert 0.0 <= point["hhi"] <= 1.0
        assert 0.0 <= point["top_weight"] <= 1.0
        assert 0.0 <= point["invested_ratio"] <= 1.0
    holding_days = [p for p in res["equity_curve"] if p["n_positions"] >= 1]
    assert holding_days, "expected at least one holding day"
    assert any(p["hhi"] > 0 for p in holding_days)
    # metrics pick the fields up from the curve
    assert res["metrics"]["max_positions"] >= 1
    assert res["metrics"]["avg_hhi"] is not None


def test_backtest_trades_carry_notional():
    series = {"600519.SH": [10.0 * (1.0 + 0.002 * i) for i in range(200)]}
    bars = _make_bars(series)
    res = run_portfolio_backtest(
        bars, min_pick_score=0.0, min_hold=5, max_positions=3, max_picks_per_day=1
    )
    assert res["trades"], "expected at least one round trip"
    for t in res["trades"]:
        assert t["entry_value"] > 0
        assert t["exit_value"] > 0
    assert res["metrics"]["turnover_notional_per_year"] is not None


# ---------- B3: cost model / slippage ----------

def test_backtest_cost_params_default_to_zero_friction_extras():
    bars = _make_bars({"600519.SH": [10.0 * (1.0 + 0.002 * i) for i in range(200)]})
    res = run_portfolio_backtest(
        bars, min_pick_score=0.0, min_hold=5, max_positions=3, max_picks_per_day=1
    )
    assert res["params"]["commission_rate"] == DEFAULT_COMMISSION_RATE
    assert res["params"]["stamp_sell_rate"] == DEFAULT_STAMP_SELL_RATE
    assert res["params"]["slippage_bps"] == 0.0
    assert res["params"]["min_commission"] == 0.0


def test_backtest_slippage_worsens_fills_for_shared_entries():
    series = {"600519.SH": [10.0 * (1.0 + 0.002 * i) for i in range(200)]}
    bars = _make_bars(series)
    kw = dict(min_pick_score=0.0, min_hold=5, max_positions=3, max_picks_per_day=1)
    base = run_portfolio_backtest(bars, **kw)
    slipped = run_portfolio_backtest(bars, slippage_bps=50.0, **kw)  # 0.5% per side
    assert base["trades"] and slipped["trades"]

    def _key(trade: dict) -> tuple[str, int]:
        return (trade["code"], trade["entry_idx"])

    base_by_key = {_key(t): t for t in base["trades"]}
    slipped_by_key = {_key(t): t for t in slipped["trades"]}
    shared = set(base_by_key) & set(slipped_by_key)
    assert shared, "expected at least one entry common to both runs"
    for k in shared:
        # same entry day ⇒ same reference close ⇒ slipped buy fills higher
        assert slipped_by_key[k]["entry_price"] > base_by_key[k]["entry_price"]
    assert slipped["final_equity"] < base["final_equity"]


def test_backtest_zero_cost_has_no_fee_drag():
    series = {"600519.SH": [10.0 * (1.0 + 0.002 * i) for i in range(200)]}
    bars = _make_bars(series)
    kw = dict(min_pick_score=0.0, min_hold=5, max_positions=3, max_picks_per_day=1)
    base = run_portfolio_backtest(bars, **kw)
    free = run_portfolio_backtest(
        bars, commission_rate=0.0, stamp_sell_rate=0.0, **kw
    )
    assert free["trades"]
    assert free["final_equity"] > base["final_equity"]
    for t in free["trades"]:
        # with no cost and no slippage, net equals gross
        assert t["net_ret"] == pytest.approx(t["gross_ret"], abs=1e-6)


# ---------- B4: universe selection + asset-class reporting ----------

_MIXED_SERIES = {
    "600519.SH": [10.0 * (1.0 + 0.002 * i) for i in range(200)],
    "000001.SZ": [8.0 * (1.0 + 0.001 * i) for i in range(200)],
    "510300.SH": [4.0 * (1.0 + 0.0015 * i) for i in range(200)],
    "159915.SZ": [3.0 * (1.0 + 0.0012 * i) for i in range(200)],
}
_MIXED_KW = dict(min_pick_score=0.0, min_hold=5, max_positions=5, max_picks_per_day=4)
_ETF_CODES = {"510300.SH", "159915.SZ"}
_STOCK_CODES = {"600519.SH", "000001.SZ"}


def test_backtest_universe_etf_only_excludes_stocks():
    bars = _make_bars(_MIXED_SERIES)
    res = run_portfolio_backtest(bars, universe="etf", **_MIXED_KW)
    entered = {t["code"] for t in res["trades"]}
    assert entered, "expected ETF entries"
    assert entered <= _ETF_CODES
    assert res["params"]["universe"] == "etf"
    assert set(res["metrics"]["by_asset"]) <= {"etf"}


def test_backtest_universe_all_is_mixed_pool():
    bars = _make_bars(_MIXED_SERIES)
    stock = run_portfolio_backtest(bars, universe="stock", **_MIXED_KW)
    mixed = run_portfolio_backtest(bars, universe="all", **_MIXED_KW)
    entered = {t["code"] for t in mixed["trades"]}
    assert entered & _ETF_CODES, "mixed book must hold at least one ETF"
    assert entered & _STOCK_CODES, "mixed book must hold at least one stock"
    assert set(mixed["metrics"]["by_asset"]) == {"stock", "etf"}
    assert mixed["params"]["universe"] == "all"
    # the stock-only run never touched an ETF
    assert {t["code"] for t in stock["trades"]} <= _STOCK_CODES


def test_backtest_trades_carry_asset_class():
    bars = _make_bars(_MIXED_SERIES)
    res = run_portfolio_backtest(bars, universe="all", **_MIXED_KW)
    assert res["trades"]
    for t in res["trades"]:
        assert t["asset_class"] in ("stock", "etf", "fund")
        assert t["asset_class"] == asset_class(t["code"])
    by_asset = res["metrics"]["by_asset"]
    assert by_asset["etf"]["n_trades"] == sum(
        1 for t in res["trades"] if t["asset_class"] == "etf"
    )


def test_backtest_legacy_exclude_funds_alias_matches_universe():
    bars = _make_bars(_MIXED_SERIES)
    legacy = run_portfolio_backtest(bars, exclude_funds=False, **_MIXED_KW)
    modern = run_portfolio_backtest(bars, universe="all", **_MIXED_KW)
    assert legacy["final_equity"] == modern["final_equity"]
    assert legacy["params"]["universe"] == "all"
    # explicit exclude_funds=True reproduces the stock-only baseline
    stock = run_portfolio_backtest(bars, exclude_funds=True, **_MIXED_KW)
    assert stock["final_equity"] == run_portfolio_backtest(
        bars, universe="stock", **_MIXED_KW
    )["final_equity"]


def test_backtest_rejects_unknown_universe():
    bars = _make_bars({"600519.SH": [10.0 + i for i in range(80)]})
    with pytest.raises(ValueError, match="universe"):
        run_portfolio_backtest(bars, universe="bogus")
