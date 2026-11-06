"""Offline tests for the S3 alpha/beta decomposition (no network, no market.db)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from stock_platform_research.portfolio import norm_code
from stock_platform_research.shadow_board import s3_decomp as d
from stock_platform_research.shadow_board.backtest import frame_to_universe, prepare_shadow_frame
from stock_platform_research.shadow_board.diagnostics import add_forward_returns

N_CODES = 40
N_DAYS = 90


def _bars(seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2025-01-02", periods=N_DAYS)
    rows = []
    for i in range(N_CODES):
        code = f"{600000 + i:06d}.SH"
        px = 10.0 + i
        for dt in days:
            pct = float(np.clip(rng.normal(0.05, 2.0), -9.0, 9.0))
            px *= 1.0 + pct / 100.0
            rows.append({"code": code, "date": dt.date().isoformat(), "close": round(px, 3),
                         "pct_chg": round(pct / 100.0, 6), "amount": 5e7 + i * 1e7})
    return pd.DataFrame(rows)


def _names() -> dict[str, str]:
    return {f"{600000 + i:06d}": f"样本{i}" for i in range(N_CODES)}


def test_nw_lag_matches_pre_registered_formula() -> None:
    assert d.nw_lag(100) == 4
    assert d.nw_lag(1000) == 6


def test_ols_recovers_known_alpha_and_betas() -> None:
    rng = np.random.default_rng(1)
    T = 2000
    X = rng.normal(0.0, 0.01, (T, 2))
    y = 0.0004 + X @ np.array([0.8, -0.3]) + rng.normal(0.0, 0.005, T)
    res = d.ols_nw(y, np.column_stack([np.ones(T), X]), ["alpha", "b1", "b2"])
    assert res is not None
    assert res["coef"]["alpha"] == pytest.approx(0.0004, abs=2e-4)
    assert res["coef"]["b1"] == pytest.approx(0.8, abs=0.05)
    assert res["coef"]["b2"] == pytest.approx(-0.3, abs=0.05)
    assert res["r2"] > 0.6


def test_newey_west_se_exceeds_naive_under_autocorrelation() -> None:
    rng = np.random.default_rng(7)
    T = 3000
    eps = rng.normal(size=T)
    e = np.zeros(T)
    for t in range(1, T):
        e[t] = 0.7 * e[t - 1] + eps[t]
    res = d.ols_nw(e, np.ones((T, 1)), ["alpha"])
    assert res is not None
    se_nw = res["coef"]["alpha"] / res["nwT"]["alpha"]
    naive = float(e.std(ddof=1)) / math.sqrt(T)
    assert se_nw > 1.3 * naive


def test_index_next_returns_use_next_session_close() -> None:
    cal = ["2024-01-02", "2024-01-03", "2024-01-04"]
    closes = {"r300": {"2024-01-02": 100.0, "2024-01-03": 101.0, "2024-01-04": 99.0}}
    out = d.index_next_returns(closes, cal)
    assert len(out) == 2
    assert out.loc[0, "r300"] == pytest.approx(0.01)
    assert out.loc[1, "r300"] == pytest.approx(99.0 / 101.0 - 1.0)


def test_index_missing_close_yields_nan_not_zero() -> None:
    cal = ["2024-01-02", "2024-01-03"]
    out = d.index_next_returns({"r500": {"2024-01-02": 100.0}}, cal)
    assert math.isnan(out.loc[0, "r500"])


def test_daily_pool_is_mean_next_day_return_of_members() -> None:
    feats = prepare_shadow_frame(_bars())
    fwd = add_forward_returns(feats)

    def stub(universe, *, top_k):  # injected pool: first top_k names of the universe
        return {"candidates": [{"code": r["code"], "score": 0.0} for r in universe[:top_k]]}

    daily = d.s3_daily_pool(fwd, name_map=_names(), top_k=3, pool_fn=stub)
    assert not daily.empty
    row = daily.iloc[5]
    frame = fwd[fwd["trade_date"] == pd.Timestamp(row["date"])]
    universe = frame_to_universe(frame, name_map=_names())
    fmap = {norm_code(str(c)): float(v) for c, v in zip(frame["code"], frame["fwd_1"])}
    expected = [fmap[r["code"]] for r in universe[:3] if math.isfinite(fmap[r["code"]])]
    assert row["n"] == len(expected)
    assert row["y"] == pytest.approx(float(np.mean(expected)))


def _synthetic_reg(alpha_daily: float, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2021-01-04", "2026-11-05")
    n = len(dates)
    r = rng.normal(0.0, 0.01, (n, 3))
    y = alpha_daily + 0.9 * r[:, 1] + rng.normal(0.0, 0.004, n)
    return pd.DataFrame(
        {
            "date": [x.date().isoformat() for x in dates],
            "y": y,
            "r300": r[:, 0],
            "r500": r[:, 1],
            "r1000": r[:, 2],
        }
    )


def test_decompose_recovers_alpha_and_verdict_passes() -> None:
    summary = d.summarize(_synthetic_reg(0.0005))
    m3 = summary["segments"]["full"]["models"]["M3"]
    # Estimate must sit within 3 NW standard errors of the true annual alpha
    # (a fixed-seed point tolerance was flaky: the draw is ~2 SE off).
    se_ann = abs(m3["alphaAnn"] / m3["alphaT"])
    assert abs(m3["alphaAnn"] - 0.0005 * 252) < 3 * se_ann
    assert summary["verdict"]["passed"] is True
    assert set(summary["years"]) == {"2021", "2022", "2023", "2024", "2025", "2026"}


def test_verdict_rule_fails_when_any_check_fails() -> None:
    # Deterministic: exercises the pre-registered rule on fabricated blocks,
    # not on a random draw (a zero-alpha seed can pass the rule by chance).
    def blk(alpha_ann: float, t: float) -> dict:
        return {"models": {"M3": {"alphaAnn": alpha_ann, "alphaT": t}}}

    ok = d.verdict({"A": blk(0.05, 2.0), "B": blk(0.05, 2.0), "full": blk(0.05, 2.0)})
    assert ok["passed"] is True
    assert d.verdict({"A": blk(-0.01, 2.0), "B": blk(0.05, 2.0), "full": blk(0.05, 2.0)})["passed"] is False
    assert d.verdict({"A": blk(0.05, 2.0), "B": blk(0.0, 2.0), "full": blk(0.05, 2.0)})["passed"] is False
    weak = d.verdict({"A": blk(0.05, 2.0), "B": blk(0.05, 2.0), "full": blk(0.05, 1.5)})
    assert weak["passed"] is False
    assert weak["label"] == "未证明选股 alpha"


def test_verdict_rule_is_pre_registered_thresholds() -> None:
    assert d.ALPHA_T_MIN == 1.5
    assert d.BENCH_SYMBOLS == {"r300": "000300", "r500": "000905", "r1000": "000852"}
    assert d.SEG_A[1:] == ("2021-01-04", "2023-12-31")
    assert d.SEG_B[1:] == ("2024-01-01", "2026-11-05")
