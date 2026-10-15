"""Unit tests for ``research.attribution`` (milestone ``Y3``).

All fixtures are synthetic and deterministic — no network, no engine ``market.db``
(the CLI end-to-end tests build their own tiny SQLite in ``tmp_path``).
"""

from __future__ import annotations

import io
import json
import os
import sqlite3

import pandas as pd
import pytest

from stock_platform_research import attribution as at
from stock_platform_research import attribution_cli as cli
from stock_platform_research.backtest import prepare_book_frame

BENCH = "000905.SZ"


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _bars(periods: int = 230, codes: int = 8, start: str = "2024-01-01") -> pd.DataFrame:
    """Deterministic bars: each code gets a different drift + amplitude (no RNG)."""
    days = pd.bdate_range(start, periods=periods)
    rows = []
    for i in range(codes):
        code = f"{600000 + i:06d}"
        drift = -0.0006 + 0.00035 * i
        price = 12.0 + i
        for j, d in enumerate(days):
            wave = 0.09 * ((j + 3 * i) % 21 - 10) / 10.0
            pct = drift + 0.012 * ((j + i) % 7 - 3) / 3.0
            price = max(1.0, price * (1.0 + pct) + wave * 0.05)
            rows.append(
                {
                    "code": code,
                    "date": d.date().isoformat(),
                    "close": round(price, 4),
                    "pct_chg": round(pct * 100.0, 4),
                }
            )
    return pd.DataFrame(rows)


def _bench_bars(periods: int = 230, start: str = "2024-01-01") -> pd.DataFrame:
    """A slow, low-volatility index series for the excess-return path."""
    days = pd.bdate_range(start, periods=periods)
    price = 5000.0
    rows = []
    for j, d in enumerate(days):
        pct = 0.0003 + 0.004 * ((j) % 9 - 4) / 4.0
        price = max(1.0, price * (1.0 + pct))
        rows.append(
            {"code": BENCH, "date": d.date().isoformat(), "close": round(price, 4), "pct_chg": round(pct * 100.0, 4)}
        )
    return pd.DataFrame(rows)


def _feats(bars: pd.DataFrame | None = None) -> pd.DataFrame:
    return prepare_book_frame(bars if bars is not None else _bars(), universe="stock")


def _make_db(path, *, with_benchmark: bool = True, with_industry: bool = True) -> None:
    bars = _bars()
    if with_benchmark:
        bars = pd.concat([bars, _bench_bars()], ignore_index=True)
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE daily_price (code TEXT, date TEXT, close REAL, pct_chg REAL)")
    con.executemany(
        "INSERT INTO daily_price VALUES (?,?,?,?)",
        list(bars[["code", "date", "close", "pct_chg"]].itertuples(index=False, name=None)),
    )
    con.execute("CREATE TABLE fundamentals (code TEXT, industry TEXT, name TEXT)")
    if with_industry:
        industries = ["银行", "白酒", "医药", "电子"]
        con.executemany(
            "INSERT INTO fundamentals VALUES (?,?,?)",
            [(f"{600000 + i:06d}", industries[i % len(industries)], f"票{i}") for i in range(8)],
        )
    con.commit()
    con.close()


def _simple_panel(scores, values, *, horizons=(1, 3, 5), floor: float = 0.80) -> pd.DataFrame:
    n = len(scores)
    data: dict = {
        "code": [f"{i:06d}" for i in range(n)],
        "trade_date": pd.to_datetime(["2026-01-05"] * n),
        "close": [10.0] * n,
        "composite_score": list(scores),
        "passesFloor": [s >= floor for s in scores],
    }
    for k in horizons:
        data[f"fwd_{k}"] = list(values)
        data[f"excess_{k}"] = list(values)
    return pd.DataFrame(data)


def _curve_row(horizon: int, mean: float, *, adequate: bool = True, n: int = 50) -> dict:
    return {
        "horizon": horizon,
        "n": n if adequate else 3,
        "adequate": adequate,
        "mean": mean,
        "median": mean,
        "upRate": 0.5,
        "meanReturn": mean,
        "meanExcess": mean,
    }


def _curve_row2(horizon: int, *, excess: float, ret: float, adequate: bool = True) -> dict:
    """A curve row whose绝对 (``ret``) and相对 (``excess``) readings differ."""
    row = _curve_row(horizon, excess, adequate=adequate)
    row["meanExcess"] = excess
    row["meanReturn"] = ret
    return row


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def test_num_is_nan_safe():
    assert at._num(None) is None
    assert at._num("nope") is None
    assert at._num(float("nan")) is None
    assert at._num("1.5") == 1.5


def test_mean_and_median_of_empty():
    assert at._mean([]) is None
    assert at._median([]) is None
    assert at._mean([1.0, 3.0]) == 2.0
    assert at._median([1.0, 3.0, 5.0]) == 3.0


def test_module_has_no_top_level_providers_import():
    src = io.open(at.__file__, encoding="utf-8").read()
    offenders = [
        line
        for line in src.splitlines()
        if (line.startswith("from ") or line.startswith("import ")) and "providers" in line
    ]
    assert offenders == []


# --------------------------------------------------------------------------- #
# attach_forward_returns
# --------------------------------------------------------------------------- #
def test_attach_forward_returns_values_and_censoring():
    days = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"])
    frame = pd.DataFrame({"code": ["A"] * 4, "trade_date": days, "close": [10.0, 11.0, 12.1, 13.31]})
    out = at.attach_forward_returns(frame, horizons=(1, 2))
    assert out["fwd_1"].iloc[0] == pytest.approx(0.10)
    assert out["fwd_2"].iloc[0] == pytest.approx(0.21)
    assert pd.isna(out["fwd_1"].iloc[-1])  # censored tail
    assert pd.isna(out["fwd_2"].iloc[-2])


def test_attach_forward_returns_never_crosses_codes():
    ts = pd.to_datetime(["2026-01-05", "2026-01-06"])
    frame = pd.DataFrame(
        {
            "code": ["A", "B", "A", "B"],
            "trade_date": [ts[0], ts[0], ts[1], ts[1]],
            "close": [10.0, 1000.0, 11.0, 2000.0],
        }
    )
    out = at.attach_forward_returns(frame, horizons=(1,)).set_index(["code", "trade_date"])
    assert out.loc[("A", ts[0]), "fwd_1"] == pytest.approx(0.10)
    assert out.loc[("B", ts[0]), "fwd_1"] == pytest.approx(1.00)


def test_attach_forward_returns_empty():
    assert at.attach_forward_returns(pd.DataFrame(), horizons=(1,)).empty


# --------------------------------------------------------------------------- #
# benchmark alignment
# --------------------------------------------------------------------------- #
def test_prepare_benchmark_ffills_onto_calendar():
    bench = pd.DataFrame({"date": ["2026-01-05", "2026-01-07"], "close": [100.0, 110.0]})
    series = at.prepare_benchmark(bench, ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"])
    assert [float(v) for v in series] == [100.0, 100.0, 110.0, 110.0]


def test_prepare_benchmark_none_or_empty():
    assert at.prepare_benchmark(None, ["2026-01-05"]) is None
    assert at.prepare_benchmark(pd.DataFrame(), ["2026-01-05"]) is None
    assert at.prepare_benchmark(pd.DataFrame({"date": [], "close": []}), ["2026-01-05"]) is None


def test_prepare_benchmark_rejects_bad_frame():
    with pytest.raises(ValueError):
        at.prepare_benchmark(pd.DataFrame({"foo": [1.0]}), ["2026-01-05"])


def test_bench_forward_uses_own_calendar():
    series = pd.Series([100.0, 110.0, 121.0], index=pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]))
    out = at._bench_forward(series, (1,)).set_index("trade_date")
    assert out.loc[pd.Timestamp("2026-01-05"), "bench_fwd_1"] == pytest.approx(0.10)


# --------------------------------------------------------------------------- #
# build_signal_panel / select_set
# --------------------------------------------------------------------------- #
def test_build_signal_panel_produces_gated_rows():
    panel = at.build_signal_panel(_feats(), horizons=(1, 3))
    assert panel["nGated"] > 0
    assert panel["basis"] == at.BASIS_RAW
    assert panel["benchmarkAvailable"] is False
    frame = panel["panel"]
    for col in ("code", "trade_date", "composite_score", "passesFloor", "fwd_1", "fwd_3"):
        assert col in frame.columns
    assert "excess_1" not in frame.columns


def test_build_signal_panel_with_benchmark_yields_excess():
    panel = at.build_signal_panel(_feats(), benchmark=_bench_bars(), horizons=(1, 3))
    assert panel["benchmarkAvailable"] is True
    assert panel["basis"] == at.BASIS_EXCESS
    frame = panel["panel"]
    assert "excess_1" in frame.columns
    assert frame["excess_1"].notna().any()


def test_build_signal_panel_empty_feats():
    panel = at.build_signal_panel(pd.DataFrame(), horizons=(1,))
    assert panel["nGated"] == 0 and panel["panel"].empty


def test_score_floor_drives_passes_floor():
    feats = _feats()
    loose = at.build_signal_panel(feats, score_floor=0.0, horizons=(1,))
    tight = at.build_signal_panel(feats, score_floor=0.99, horizons=(1,))
    assert loose["nGated"] == tight["nGated"]
    assert loose["nPicks"] >= tight["nPicks"]


def test_select_set_filters_and_rejects_bad_name():
    panel = _simple_panel([0.1, 0.9], [0.01, 0.02])
    assert len(at.select_set(panel, at.SET_GATED)) == 2
    assert len(at.select_set(panel, at.SET_PICKS)) == 1
    with pytest.raises(ValueError):
        at.select_set(panel, "nope")


# --------------------------------------------------------------------------- #
# horizon_curve
# --------------------------------------------------------------------------- #
def test_horizon_curve_means_and_adequacy():
    panel = _simple_panel([0.9, 0.9], [0.02, 0.04], horizons=(1, 3))
    curve = at.horizon_curve(panel, horizons=(1, 3), which=at.SET_PICKS, min_sample=20)
    assert len(curve) == 2
    assert curve[0]["n"] == 2
    assert curve[0]["adequate"] is False
    assert curve[0]["mean"] == pytest.approx(0.03)


def test_horizon_curve_adequate_flag():
    panel = _simple_panel([0.9] * 30, [0.01] * 30, horizons=(1,))
    curve = at.horizon_curve(panel, horizons=(1,), which=at.SET_PICKS, min_sample=20)
    assert curve[0]["adequate"] is True and curve[0]["n"] == 30


def test_horizon_curve_empty_selection_is_zeroed():
    panel = _simple_panel([0.1, 0.2], [0.01, 0.02], horizons=(1,))  # no picks over floor
    curve = at.horizon_curve(panel, horizons=(1,), which=at.SET_PICKS)
    assert curve[0]["n"] == 0 and curve[0]["mean"] is None and curve[0]["adequate"] is False


# --------------------------------------------------------------------------- #
# score_curve
# --------------------------------------------------------------------------- #
def test_score_curve_increasing():
    panel = _simple_panel([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8], [1, 2, 3, 4, 5, 6, 7, 8], horizons=(5,))
    out = at.score_curve(panel, horizon=5, buckets=4, which=at.SET_GATED, min_sample=2)
    assert out["spearman"] == pytest.approx(1.0)
    assert out["direction"] == "increasing"
    assert out["topMinusBottom"] > 0
    assert len(out["buckets"]) == 4


def test_score_curve_decreasing():
    panel = _simple_panel([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8], [8, 7, 6, 5, 4, 3, 2, 1], horizons=(5,))
    out = at.score_curve(panel, horizon=5, buckets=2, which=at.SET_GATED, min_sample=2)
    assert out["spearman"] == pytest.approx(-1.0)
    assert out["direction"] == "decreasing"
    assert out["topMinusBottom"] < 0


def test_score_curve_flat():
    panel = _simple_panel([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8], [0.01] * 8, horizons=(5,))
    out = at.score_curve(panel, horizon=5, buckets=4, which=at.SET_GATED, min_sample=2)
    assert out["direction"] == "flat"
    assert out["topMinusBottom"] == pytest.approx(0.0)


def test_score_curve_thin_sample_not_adequate():
    panel = _simple_panel([0.1, 0.9], [0.01, 0.02], horizons=(5,))
    out = at.score_curve(panel, horizon=5, which=at.SET_GATED, min_sample=20)
    assert out["adequate"] is False


def test_score_curve_missing_column():
    out = at.score_curve(pd.DataFrame(), horizon=5)
    assert out["n"] == 0 and out["spearman"] is None


# --------------------------------------------------------------------------- #
# cost_drag / payoff_profile
# --------------------------------------------------------------------------- #
def test_cost_drag_detects_sign_flip():
    # ``book_replay`` emits percent points (+40.0 == +40%); the module normalises ×0.01.
    trades = [
        {"gross_ret": 40.0, "net_ret": -30.0, "held_days": 5},
        {"gross_ret": 60.0, "net_ret": -10.0, "held_days": 7},
    ]
    out = at.cost_drag(trades)
    assert out["unit"] == "fraction"
    assert out["n"] == 2
    assert out["meanGross"] == pytest.approx(0.5)
    assert out["meanNet"] == pytest.approx(-0.2)
    assert out["meanCost"] == pytest.approx(0.7)
    assert out["costShare"] == pytest.approx(1.4)
    assert out["signFlipped"] is True
    assert out["avgHoldDays"] == pytest.approx(6.0)


def test_cost_drag_empty():
    out = at.cost_drag([])
    assert out["n"] == 0 and out["meanNet"] is None and out["signFlipped"] is None


def test_payoff_profile_split():
    out = at.payoff_profile(
        [{"net_ret": 100.0}, {"net_ret": 200.0}, {"net_ret": -100.0}, {"net_ret": -300.0}]
    )
    assert out["unit"] == "fraction"
    assert out["n"] == 4
    assert out["winRate"] == pytest.approx(0.5)
    assert out["avgWin"] == pytest.approx(1.5)
    assert out["avgLoss"] == pytest.approx(-2.0)
    assert out["payoffRatio"] == pytest.approx(0.75)
    assert out["expectancy"] == pytest.approx(-0.25)


def test_payoff_profile_empty():
    out = at.payoff_profile([])
    assert out["n"] == 0 and out["winRate"] is None


# --------------------------------------------------------------------------- #
# concentration
# --------------------------------------------------------------------------- #
def test_concentration_by_reason_loss_share():
    trades = [
        {"reason": "stop_loss(-8.1%)", "net_ret": -400.0, "exit_date": "2026-01-30"},
        {"reason": "stop_loss(-9.5%)", "net_ret": -600.0, "exit_date": "2026-01-31"},
        {"reason": "target(+5.2%)", "net_ret": 100.0, "exit_date": "2026-02-28"},
    ]
    out = at.concentration(trades, by="reason")
    assert out["byZh"] == "退出原因"
    assert out["groupCount"] == 2  # stop_loss(-8.1%) / stop_loss(-9.5%) fold into one bucket
    assert out["groups"][0]["group"] == "stop_loss"
    assert out["worst"]["total"] == pytest.approx(-10.0)
    assert out["maxLossGroup"] == "stop_loss"
    assert out["maxLossShare"] == pytest.approx(1.0)


def test_concentration_month_and_industry_with_norm_code():
    trades = [
        {"code": "600000.SH", "net_ret": -100.0, "exit_date": "2026-01-30"},
        {"code": "600001.SH", "net_ret": 50.0, "exit_date": "2026-02-27"},
    ]
    by_month = at.concentration(trades, by="month")
    assert [g["group"] for g in by_month["groups"]] == ["2026-01", "2026-02"]
    by_ind = at.concentration(trades, by="industry", industry_map={"600000": "银行", "600001": "白酒"})
    assert {g["group"] for g in by_ind["groups"]} == {"银行", "白酒"}


def test_concentration_empty_and_all_positive():
    assert at.concentration([], by="month")["groups"] == []
    out = at.concentration([{"reason": "x", "net_ret": 100.0}], by="reason")
    assert out["maxLossShare"] is None


# --------------------------------------------------------------------------- #
# diagnose (pure)
# --------------------------------------------------------------------------- #
def test_diagnose_signal_no_edge():
    curve = [_curve_row(1, -0.01), _curve_row(5, -0.02), _curve_row(20, -0.03)]
    out = at.diagnose(curve_picks=curve)
    assert out["causes"][0]["code"] == at.CAUSE_SIGNAL_NO_EDGE
    assert out["causes"][0]["severity"] == at.SEVERITY_ALERT


def test_diagnose_hold_too_long():
    curve = [_curve_row(1, 0.02), _curve_row(5, 0.03), _curve_row(20, -0.01)]
    out = at.diagnose(curve_picks=curve, realized_hold_days=34.0)
    codes = [c["code"] for c in out["causes"]]
    assert at.CAUSE_HOLD_TOO_LONG in codes
    cause = next(c for c in out["causes"] if c["code"] == at.CAUSE_HOLD_TOO_LONG)
    assert cause["evidence"]["peakHorizon"] == 5
    assert cause["evidence"]["realizedHoldDays"] == 34.0


def test_diagnose_hold_too_short():
    curve = [_curve_row(1, -0.01), _curve_row(5, -0.005), _curve_row(20, 0.04)]
    out = at.diagnose(curve_picks=curve)
    assert at.CAUSE_HOLD_TOO_SHORT in [c["code"] for c in out["causes"]]


def test_diagnose_score_not_monotonic_alert():
    curve = [_curve_row(5, 0.01)]
    score = {"n": 100, "horizon": 5, "spearman": -0.12, "topMinusBottom": -0.02, "direction": "decreasing"}
    out = at.diagnose(curve_picks=curve, score=score)
    cause = next(c for c in out["causes"] if c["code"] == at.CAUSE_SCORE_NOT_MONOTONIC)
    assert cause["severity"] == at.SEVERITY_ALERT


def test_diagnose_score_flat_is_warn():
    curve = [_curve_row(5, 0.01)]
    score = {"n": 100, "horizon": 5, "spearman": 0.01, "topMinusBottom": 0.0, "direction": "flat"}
    out = at.diagnose(curve_picks=curve, score=score)
    cause = next(c for c in out["causes"] if c["code"] == at.CAUSE_SCORE_WEAK)
    assert cause["severity"] == at.SEVERITY_WARN


def test_diagnose_cost_erodes_edge_alert():
    curve = [_curve_row(5, 0.01)]
    cost = {"n": 40, "meanGross": 0.5, "meanNet": -0.2, "meanCost": 0.7, "costShare": 1.4, "avgHoldDays": 6.0}
    out = at.diagnose(curve_picks=curve, cost=cost)
    cause = next(c for c in out["causes"] if c["code"] == at.CAUSE_COST_ERODES_EDGE)
    assert cause["severity"] == at.SEVERITY_ALERT


def test_diagnose_cost_share_warn():
    curve = [_curve_row(5, 0.01)]
    cost = {"n": 40, "meanGross": 1.0, "meanNet": 0.5, "meanCost": 0.5, "costShare": 0.5, "avgHoldDays": 6.0}
    out = at.diagnose(curve_picks=curve, cost=cost)
    cause = next(c for c in out["causes"] if c["code"] == at.CAUSE_COST_ERODES_EDGE)
    assert cause["severity"] == at.SEVERITY_WARN


def test_diagnose_payoff_unfavorable():
    curve = [_curve_row(5, 0.01)]
    payoff = {"n": 40, "winRate": 0.37, "avgWin": 1.0, "avgLoss": -2.0, "payoffRatio": 0.5, "expectancy": -0.38}
    out = at.diagnose(curve_picks=curve, payoff=payoff)
    assert at.CAUSE_PAYOFF_UNFAVORABLE in [c["code"] for c in out["causes"]]


def test_diagnose_concentrated_loss():
    curve = [_curve_row(5, 0.01)]
    block = {
        "by": "month",
        "byZh": "月份",
        "n": 40,
        "maxLossGroup": "2026-01",
        "maxLossShare": 0.7,
        "overallMean": -0.1,
        "groups": [{"group": "2026-01"}, {"group": "2026-02"}],
    }
    out = at.diagnose(curve_picks=curve, concentrations=[block])
    cause = next(c for c in out["causes"] if c["code"] == at.CAUSE_CONCENTRATED_LOSS)
    assert "2026-01" in cause["title"]


def test_diagnose_no_single_cause():
    curve = [_curve_row(1, 0.01), _curve_row(5, 0.02)]
    out = at.diagnose(curve_picks=curve)
    assert out["causes"][0]["code"] == at.CAUSE_NO_SINGLE_CAUSE
    assert out["causes"][0]["severity"] == at.SEVERITY_INFO
    assert out["verdict"] == at.CAUSE_NO_SINGLE_CAUSE


def test_diagnose_falls_back_to_gated_when_picks_thin():
    gated = [_curve_row(5, -0.03)]
    out = at.diagnose(curve_picks=[_curve_row(5, 0.0, adequate=False)], curve_gated=gated)
    assert out["basisSet"] == at.SET_GATED
    assert out["notes"]
    assert at.CAUSE_SIGNAL_NO_EDGE in [c["code"] for c in out["causes"]]


def test_diagnose_all_inadequate_makes_no_conclusion():
    out = at.diagnose(curve_picks=[_curve_row(5, 0.0, adequate=False)])
    assert out["basisSet"] == at.SET_PICKS
    assert out["causes"][0]["code"] == at.CAUSE_NO_SINGLE_CAUSE
    assert out["notes"]


def test_diagnose_orders_alert_before_warn():
    curve = [_curve_row(5, -0.05)]
    cost = {"n": 40, "meanGross": 1.0, "meanNet": 0.6, "meanCost": 0.4, "costShare": 0.4, "avgHoldDays": 6.0}
    out = at.diagnose(curve_picks=curve, cost=cost)
    severities = [c["severity"] for c in out["causes"]]
    assert severities[0] == at.SEVERITY_ALERT
    assert severities == sorted(severities, key=lambda s: -at._SEVERITY_WEIGHT[s])


def test_diagnose_edge_only_long_horizon():
    curve = [
        _curve_row2(1, excess=-0.02, ret=-0.03),
        _curve_row2(5, excess=-0.01, ret=-0.02),
        _curve_row2(40, excess=0.05, ret=-0.06),
    ]
    out = at.diagnose(curve_picks=curve)
    assert at.CAUSE_EDGE_ONLY_LONG_HORIZON in [c["code"] for c in out["causes"]]


def test_diagnose_no_absolute_edge_alert():
    curve = [_curve_row2(1, excess=0.01, ret=-0.01), _curve_row2(5, excess=0.02, ret=-0.02)]
    out = at.diagnose(curve_picks=curve)
    cause = next(c for c in out["causes"] if c["code"] == at.CAUSE_NO_ABSOLUTE_EDGE)
    assert cause["severity"] == at.SEVERITY_ALERT


def test_diagnose_skips_single_group_concentration():
    curve = [_curve_row(5, 0.01)]
    block = {
        "by": "assetClass",
        "byZh": "资产类别",
        "n": 85,
        "maxLossGroup": "stock",
        "maxLossShare": 1.0,
        "overallMean": -0.02,
        "groups": [{"group": "stock"}],
    }
    out = at.diagnose(curve_picks=curve, concentrations=[block])
    assert at.CAUSE_CONCENTRATED_LOSS not in [c["code"] for c in out["causes"]]


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def test_render_markdown_has_all_sections():
    payload = {
        "ok": True,
        "generatedAt": "2026-10-15",
        "start": "2025-10-14",
        "end": "2026-10-14",
        "nDays": 243,
        "benchmarkSymbol": BENCH,
        "benchmarkAvailable": True,
        "scoreFloor": 0.80,
        "nGated": 100,
        "nPicks": 20,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "curvePicks": [_curve_row(1, -0.01), _curve_row(5, -0.02)],
        "curveGated": [_curve_row(5, -0.015)],
        "score": {
            "horizon": 5,
            "n": 100,
            "adequate": True,
            "spearman": -0.1,
            "direction": "decreasing",
            "topMinusBottom": -0.02,
            "buckets": [{"lo": 0.0, "hi": 0.5, "n": 50, "mean": 0.01, "upRate": 0.5}],
        },
        "cost": {"n": 20, "meanGross": 0.1, "meanNet": -0.1, "meanCost": 0.2, "costShare": 2.0, "avgHoldDays": 6.0, "signFlipped": True},
        "payoff": {"n": 20, "winRate": 0.37, "avgWin": 1.0, "avgLoss": -2.0, "payoffRatio": 0.5, "expectancy": -0.38, "best": 5.0, "worst": -6.0},
        "concentrations": [
            {"by": "month", "byZh": "月份", "overallTotal": -3.0, "groups": [{"group": "2026-01", "n": 5, "mean": -0.6, "total": -3.0, "lossShare": 1.0}]}
        ],
        "diagnosis": at.diagnose(curve_picks=[_curve_row(1, -0.01), _curve_row(5, -0.02)]),
        "disclaimer": "SIMULATE",
    }
    md = at.render_attribution_markdown(payload)
    for needle in ("收益归因", "一、信号有效性曲线", "二、评分单调性", "三、成本拖累", "四、赔率结构", "五、亏损集中度", "六、根因裁决"):
        assert needle in md


def test_render_markdown_not_ok():
    assert "无可用数据" in at.render_attribution_markdown({"ok": False, "reason": "boom"})


# --------------------------------------------------------------------------- #
# CLI helpers + end-to-end
# --------------------------------------------------------------------------- #
def test_cli_resolve_benchmark_code(monkeypatch):
    monkeypatch.delenv("STOCK_PLATFORM_BENCHMARK_SYMBOL", raising=False)
    assert cli._resolve_benchmark_code("") == "000905.SZ"
    assert cli._resolve_benchmark_code("000300.SH") == "000300.SH"
    monkeypatch.setenv("STOCK_PLATFORM_BENCHMARK_SYMBOL", "000852")
    assert cli._resolve_benchmark_code("") == "000852.SZ"


def test_cli_parse_horizons():
    assert cli._parse_horizons("5,1,3") == (1, 3, 5)
    assert cli._parse_horizons("") == at.DEFAULT_HORIZONS
    assert cli._parse_horizons("0,-2") == at.DEFAULT_HORIZONS


def test_cli_last_bar_date(tmp_path):
    db = tmp_path / "market.db"
    _make_db(db)
    assert cli._last_bar_date(str(db)) == _bars()["date"].max()


def test_cli_end_to_end_writes_report(tmp_path):
    db = tmp_path / "market.db"
    _make_db(db)
    days = sorted(_bars()["date"].unique())
    code = cli.main(
        [
            "--db", str(db),
            "--start", days[65],
            "--end", days[-1],
            "--out-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    out = tmp_path / "out"
    payload = json.loads((out / "attribution.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["universe"] == "stock"
    assert payload["benchmarkAvailable"] is True
    assert payload["basis"] == at.BASIS_EXCESS
    assert payload["nGated"] > 0
    assert payload["diagnosis"]["causes"]
    assert (out / "attribution.md").is_file()
    assert (out / "attribution.html").is_file()


def test_cli_no_benchmark_uses_raw_basis(tmp_path):
    db = tmp_path / "market.db"
    _make_db(db, with_benchmark=False)
    days = sorted(_bars()["date"].unique())
    code = cli.main(
        ["--db", str(db), "--start", days[65], "--end", days[-1], "--no-benchmark",
         "--out-dir", str(tmp_path / "out")]
    )
    assert code == 0
    payload = json.loads((tmp_path / "out" / "attribution.json").read_text(encoding="utf-8"))
    assert payload["benchmarkAvailable"] is False
    assert payload["basis"] == at.BASIS_RAW


def test_cli_missing_benchmark_code_falls_back(tmp_path):
    db = tmp_path / "market.db"
    _make_db(db, with_benchmark=False)
    days = sorted(_bars()["date"].unique())
    code = cli.main(
        ["--db", str(db), "--start", days[65], "--end", days[-1], "--benchmark", "000300.SH",
         "--out-dir", str(tmp_path / "out")]
    )
    assert code == 0
    payload = json.loads((tmp_path / "out" / "attribution.json").read_text(encoding="utf-8"))
    assert payload["benchmarkAvailable"] is False


def test_cli_no_replay_skips_cost_blocks(tmp_path):
    db = tmp_path / "market.db"
    _make_db(db)
    days = sorted(_bars()["date"].unique())
    code = cli.main(
        ["--db", str(db), "--start", days[65], "--end", days[-1], "--no-replay",
         "--out-dir", str(tmp_path / "out")]
    )
    assert code == 0
    payload = json.loads((tmp_path / "out" / "attribution.json").read_text(encoding="utf-8"))
    assert payload["scoreFloorReplay"] is False
    assert payload["cost"]["n"] == 0


def test_cli_no_write_and_json_flag(tmp_path, capsys):
    db = tmp_path / "market.db"
    _make_db(db, with_industry=False)
    days = sorted(_bars()["date"].unique())
    code = cli.main(
        ["--db", str(db), "--start", days[65], "--end", days[-1], "--no-write", "--json"]
    )
    assert code == 0
    printed = capsys.readouterr().out
    assert "收益归因" in printed
    assert '"ok": true' in printed.replace('"ok":true', '"ok": true')
    assert not (tmp_path / "data").exists()


def test_cli_missing_db_exits(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["--db", str(tmp_path / "nope.db")])


def test_cli_no_rows_returns_2(tmp_path, capsys):
    db = tmp_path / "market.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE daily_price (code TEXT, date TEXT, close REAL, pct_chg REAL)")
    con.commit()
    con.close()
    assert cli.main(["--db", str(db), "--no-write"]) == 2
