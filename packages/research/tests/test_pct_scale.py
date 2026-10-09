"""``pct_scale`` — the single definition of the mixed-scale ``pct_chg`` dump.

The engine dump is genuinely mixed: stocks ship fractions, ETFs ship percent
points. The old ``|x| > 0.5`` heuristic mis-reads both (an IPO's +86.9 % session
is a fraction above ``0.5``; an ETF's 0.94 % session is a point value below it),
which is why the price-limit checks silently stopped firing. These tests pin the
``close``-fitting verdict, the asset-class fallback, and the contract that
``compute_features`` hands ``rules`` percent points.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_platform_research import backtest, pct_scale, rules
from stock_platform_research.backtest import compute_features, run_portfolio_backtest
from stock_platform_research.pct_scale import (
    SCALE_FRACTION,
    SCALE_POINTS,
    detect_pct_scale,
    normalize_pct_chg,
)

DAYS = pd.bdate_range("2024-01-02", periods=120)


def _bars(code: str, closes: list[float], pcts: list[float]) -> pd.DataFrame:
    n = len(closes)
    assert n == len(pcts)
    return pd.DataFrame(
        {
            "code": [code] * n,
            "date": [d.date().isoformat() for d in DAYS[:n]],
            "close": closes,
            "pct_chg": pcts,
        }
    )


def _fraction_series(code: str, n: int = 30, step: float = 0.01) -> pd.DataFrame:
    """A code whose ``pct_chg`` is a *fraction* (0.01 == 1 %), consistent with close."""
    closes = [10.0]
    pcts = [0.0]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1.0 + step))
        pcts.append(step)
    return _bars(code, closes, pcts)


def _points_series(code: str, n: int = 30, step: float = 1.0) -> pd.DataFrame:
    """A code whose ``pct_chg`` is *percent points* (1.0 == 1 %), consistent with close."""
    closes = [1.0]
    pcts = [0.0]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1.0 + step / 100.0))
        pcts.append(step)
    return _bars(code, closes, pcts)


# ---------- the verdict ----------


def test_detect_separates_fraction_stocks_from_point_funds() -> None:
    bars = pd.concat(
        [_fraction_series("600519.SH"), _points_series("159967")], ignore_index=True
    )
    verdict = detect_pct_scale(bars)
    assert verdict["600519.SH"] == SCALE_FRACTION
    assert verdict["159967"] == SCALE_POINTS


def test_detect_is_not_fooled_by_a_large_fraction_move() -> None:
    """An IPO's +86.9 % first session is a fraction — ``|x| > 0.5`` would misread it."""
    n = 30
    closes = [10.0]
    pcts = [0.0]
    for _ in range(n - 1):
        closes.append(closes[-1] * 1.01)
        pcts.append(0.01)
    closes[1] = closes[0] * (1.0 + 0.869)  # +86.9 % day one
    pcts[1] = 0.869
    bars = _bars("688081.SH", closes, pcts)
    assert detect_pct_scale(bars)["688081.SH"] == SCALE_FRACTION


def test_detect_falls_back_to_asset_class_prior_below_min_votes() -> None:
    """Too few votable rows ⇒ prior, never a guess from noise."""
    stock = _fraction_series("600519.SH", n=4)
    fund = _points_series("159967", n=4)
    verdict = detect_pct_scale(pd.concat([stock, fund], ignore_index=True))
    assert verdict["600519.SH"] == SCALE_FRACTION
    assert verdict["159967"] == SCALE_POINTS


def test_detect_ignores_corporate_action_rows_in_the_vote() -> None:
    """A split fakes a huge ``close`` gap; that row must not vote (nor flip the code)."""
    bars = _fraction_series("600551.SH", n=30)
    bars.loc[10, "close"] = float(bars.loc[9, "close"]) * 0.5  # fake -50 % ex-split gap
    assert detect_pct_scale(bars)["600551.SH"] == SCALE_FRACTION


def test_detect_covers_every_code_present() -> None:
    bars = pd.concat(
        [_fraction_series("600519.SH"), _points_series("159967")], ignore_index=True
    )
    verdict = detect_pct_scale(bars)
    assert set(verdict.index) == {"600519.SH", "159967"}


def test_detect_without_pct_column_is_empty_not_an_error() -> None:
    bars = pd.DataFrame({"code": ["600519.SH"], "close": [10.0]})
    assert detect_pct_scale(bars).empty


# ---------- the normalisation ----------


def test_normalize_returns_percent_points_and_stays_index_aligned() -> None:
    bars = pd.concat(
        [_fraction_series("600519.SH"), _points_series("159967")], ignore_index=True
    ).reset_index(drop=True)
    points, row_scale = normalize_pct_chg(bars)
    assert len(points) == len(bars)
    assert list(points.index) == list(bars.index)
    # fractions are lifted ×100; points are left alone
    stock = bars["code"] == "600519.SH"
    fund = bars["code"] == "159967"
    assert np.allclose(points[stock].to_numpy(), bars.loc[stock, "pct_chg"] * 100.0)
    assert np.allclose(points[fund].to_numpy(), bars.loc[fund, "pct_chg"])
    assert set(row_scale[stock]) == {SCALE_FRACTION}
    assert set(row_scale[fund]) == {SCALE_POINTS}


def test_normalize_never_fabricates_zero_for_missing() -> None:
    bars = _fraction_series("600519.SH", n=20)
    bars.loc[5, "pct_chg"] = np.nan
    points, _ = normalize_pct_chg(bars)
    assert pd.isna(points.iloc[5])


# ---------- single definition + the rules contract ----------


def test_normalize_is_the_single_definition_everywhere() -> None:
    assert backtest.normalize_pct_chg is pct_scale.normalize_pct_chg
    assert backtest.normalize_pct_chg is normalize_pct_chg


def test_compute_features_hands_rules_percent_points() -> None:
    """After ``compute_features`` the column satisfies the ``rules`` contract."""
    n = 30
    closes = [10.0]
    pcts = [0.0]
    for i in range(1, n):
        # a 10 % sealed limit-up on session 20, plain +1 % elsewhere (fraction scale)
        step = 0.10 if i == 20 else 0.01
        closes.append(closes[-1] * (1.0 + step))
        pcts.append(step)
    bars = _bars("600519.SH", closes, pcts)

    feats = compute_features(bars)  # default pct_scale="auto"
    row = feats.iloc[20]
    assert float(row["pct_chg"]) == pytest.approx(10.0, abs=1e-3)
    assert rules.is_limit_up("600519.SH", float(row["pct_chg"])) is True
    # …and the legacy verbatim path would have missed it entirely
    legacy = compute_features(bars, pct_scale="verbatim")
    assert float(legacy.iloc[20]["pct_chg"]) == pytest.approx(0.10, abs=1e-4)
    assert rules.is_limit_up("600519.SH", float(legacy.iloc[20]["pct_chg"])) is False


def test_verbatim_keeps_the_legacy_column_untouched() -> None:
    bars = _fraction_series("600519.SH", n=30)
    feats = compute_features(bars, pct_scale="verbatim")
    assert np.allclose(
        feats["pct_chg"].to_numpy(), bars["pct_chg"].to_numpy().astype("float32")
    )


def test_backtest_echoes_the_scale_in_params() -> None:
    bars = _fraction_series("600519.SH", n=80)
    auto = run_portfolio_backtest(bars, min_pick_score=0.0)
    assert auto["params"]["pct_scale"] == "auto"
    verbatim = run_portfolio_backtest(bars, min_pick_score=0.0, pct_scale="verbatim")
    assert verbatim["params"]["pct_scale"] == "verbatim"
