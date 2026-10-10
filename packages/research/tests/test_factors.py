"""``S2`` factor library tests — factor maths, PIT safety, registry shape.

No network, no DB: everything is built from a synthetic bars frame.

⚠️ The synthetic bars deliberately **omit** ``pct_chg``. ``compute_features``
rebuilds ``close`` from ``pct_chg`` when that column is present (corporate-action
repair), so a fixture with ``pct_chg == 0`` everywhere collapses ``close`` to a
constant and every factor becomes degenerate. Real loaders always carry a
meaningful ``pct_chg``; unit fixtures simply leave it out.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_platform_research.backtest import compute_features
from stock_platform_research.factors import (
    BASELINE_FACTORS,
    FACTOR_LIBRARY,
    NEW_FACTORS,
    build_factor_frame,
    build_feature_frame,
    factor_correlation,
    factor_spec,
    list_factors,
)


def _bars(*, n_codes: int = 20, n_days: int = 160, seed: int = 7, amount: bool = True) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=n_days).strftime("%Y-%m-%d")
    rows: list[dict[str, object]] = []
    for c in range(n_codes):
        code = f"{600000 + c}.SH"
        # spread per-code vol so low_vol has a real cross-section
        rets = rng.normal(0.0002, 0.008 + 0.0005 * c, n_days)
        close = 12.0 * np.cumprod(1.0 + rets)
        for d, cl in zip(dates, close, strict=True):
            row: dict[str, object] = {"code": code, "date": d, "close": float(cl)}
            if amount:
                row["amount"] = float(10 ** rng.uniform(7.0, 8.5))
                row["vol"] = float(10 ** rng.uniform(4.0, 6.0))
            rows.append(row)
    return pd.DataFrame(rows)


def test_registry_shape() -> None:
    assert set(FACTOR_LIBRARY) == set(BASELINE_FACTORS) | set(NEW_FACTORS)
    assert len(NEW_FACTORS) >= 2, "S2 acceptance: ≥2 new orthogonal factors"
    assert len(set(NEW_FACTORS)) == len(NEW_FACTORS)
    assert not (set(NEW_FACTORS) & set(BASELINE_FACTORS))
    for name, spec in FACTOR_LIBRARY.items():
        assert spec.name == name
        assert spec.direction in (1, -1)
        assert spec.label and spec.description
        assert callable(spec.compute)
    assert list_factors() == list(FACTOR_LIBRARY)


def test_unknown_factor_raises() -> None:
    with pytest.raises(KeyError):
        factor_spec("no-such-factor")


def test_feature_frame_adds_extras_without_touching_default_path() -> None:
    bars = _bars()
    feats = build_feature_frame(bars)
    assert {"vol", "amount"}.issubset(feats.columns)
    # default path (no keep_extra) must remain the legacy 9-column set
    plain = compute_features(bars)
    assert "amount" not in plain.columns
    assert "vol" not in plain.columns


def test_factor_frame_has_every_library_column() -> None:
    feats = build_feature_frame(_bars())
    frame = build_factor_frame(feats)
    assert list(frame.columns) == list(FACTOR_LIBRARY)
    assert len(frame) == len(feats)
    for col in frame.columns:
        assert frame[col].notna().any(), f"{col} has no finite values"


def test_long_reversal_is_negated_twelve_minus_one() -> None:
    feats = build_feature_frame(_bars(n_codes=3, n_days=220))
    frame = build_factor_frame(feats, factors=["long_reversal"])
    close = feats.groupby("code", sort=False)["close"]
    raw = close.shift(20) / close.shift(120) - 1.0
    assert frame["long_reversal"].round(10).equals((-raw).round(10))


def test_max_ret_is_trailing_max_of_daily_returns() -> None:
    feats = build_feature_frame(_bars(n_codes=4, n_days=140))
    frame = build_factor_frame(feats, factors=["max_ret"])
    expect = (
        feats.groupby("code", sort=False)["ret1"]
        .rolling(20, min_periods=20)
        .max()
        .reset_index(level=0, drop=True)
        .set_axis(feats.index)
    )
    assert frame["max_ret"].round(10).equals(expect.round(10))


def test_illiq_needs_amount_and_is_positive_when_present() -> None:
    feats = build_feature_frame(_bars(n_codes=4, n_days=140))
    missing = build_factor_frame(feats.drop(columns=["amount"]), factors=["illiq"])
    assert missing["illiq"].isna().all()

    present = build_factor_frame(feats, factors=["illiq"])
    values = present["illiq"].dropna()
    assert len(values) > 0
    assert (values > 0).all()


def test_factors_are_pit_safe() -> None:
    """Corrupting the *future* must not move any past factor value."""
    bars = _bars(n_codes=5, n_days=160)
    feats = build_feature_frame(bars)
    frame = build_factor_frame(feats)

    last_dates = sorted(bars["date"].unique())[-30:]
    bars2 = bars.copy()
    bars2.loc[bars2["date"].isin(last_dates), "close"] *= 3.0
    feats2 = build_feature_frame(bars2)
    frame2 = build_factor_frame(feats2)

    cut = sorted(feats["trade_date"].unique())[-31]
    left = frame.loc[feats["trade_date"] <= cut].reset_index(drop=True)
    right = frame2.loc[feats2["trade_date"] <= cut].reset_index(drop=True)
    assert left.equals(right)


def test_new_factors_do_not_duplicate_the_short_reversal_window() -> None:
    """6-month reversal skips the recent month → must differ from 20-day reversal."""
    feats = build_feature_frame(_bars(n_codes=25, n_days=220))
    frame = build_factor_frame(feats, factors=["long_reversal", "reversal"])
    both = frame.dropna()
    assert len(both) > 0
    corr = float(both["long_reversal"].rank().corr(both["reversal"].rank()))
    assert abs(corr) < 0.5


def test_factor_correlation_covers_the_requested_set() -> None:
    feats = build_feature_frame(_bars())
    names = ["low_vol", "reversal", "long_reversal"]
    corr = factor_correlation(build_factor_frame(feats, factors=names))
    assert list(corr.columns) == names
    assert list(corr.index) == names
    for name in names:
        assert abs(float(corr.loc[name, name]) - 1.0) < 1e-9
