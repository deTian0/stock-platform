"""Tests for lvrev scoring and entry gates."""

from __future__ import annotations

import pandas as pd
import pytest

from stock_platform_research import apply_entry_gates, score_lvrev


@pytest.fixture
def sample_lvrev_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "code": ["600519", "000001", "300750"],
            "name": ["茅台", "平安", "宁德"],
            "vol20": [0.1, 0.3, 0.5],
            "rev_chg": [-0.05, -0.02, 0.03],
            "debt_ratio": [30, 60, 45],
            "revenue_growth": [10, -5, 20],
            "pb": [10, 0.8, 5],
            "ps_ttm": [5, 1, 3],
            "pe": [30, 8, 50],
            "close": [1800, 15, 200],
            "ma20": [1800, 15, 195],
            "ma60": [1700, 14, 190],
            "rs20": [0.5, 0.3, 0.6],
        }
    )


def test_score_lvrev_normal(sample_lvrev_df: pd.DataFrame) -> None:
    out = score_lvrev(sample_lvrev_df)
    assert "composite_score" in out.columns
    assert len(out) == len(sample_lvrev_df)
    vals = out["composite_score"].tolist()
    assert vals == sorted(vals, reverse=True)
    assert (out["composite_score"] >= 0).all()


def test_score_lvrev_empty() -> None:
    out = score_lvrev(pd.DataFrame())
    assert "composite_score" in out.columns
    assert len(out) == 0


def test_score_lvrev_missing_columns() -> None:
    df = pd.DataFrame({"code": ["A", "B"]})
    out = score_lvrev(df)
    assert len(out) == 2


def test_score_lvrev_value_factor_changes_scores() -> None:
    df = pd.DataFrame(
        {
            "vol20": [0.2, 0.4],
            "rev_chg": [-0.03, 0.02],
            "debt_ratio": [40, 60],
            "revenue_growth": [10, 5],
            "pb": [5, 2],
            "ps_ttm": [3, 1],
            "pe": [20, 10],
        }
    )
    base = score_lvrev(df, value_factor=False)["composite_score"]
    val = score_lvrev(df, value_factor=True)["composite_score"]
    assert not base.equals(val)


def test_apply_entry_gates_normal(sample_lvrev_df: pd.DataFrame) -> None:
    mask = apply_entry_gates(sample_lvrev_df, reversal_q=0.30)
    assert mask.dtype == bool
    assert mask.tolist() == [True, False, False]


def test_apply_entry_gates_trend_down_rejects() -> None:
    df = pd.DataFrame(
        {
            "rev_chg": [-0.1, -0.1],
            "close": [10, 10],
            "ma20": [9, 9],
            "ma60": [10, 10],
            "vol20": [0.1, 0.1],
        }
    )
    assert apply_entry_gates(df).tolist() == [False, False]


def test_apply_entry_gates_falling_knife_rejects() -> None:
    df = pd.DataFrame(
        {
            "rev_chg": [-0.1],
            "close": [8.0],
            "ma20": [10.0],
            "ma60": [9.0],
            "vol20": [0.1],
        }
    )
    assert apply_entry_gates(df).tolist() == [False]
