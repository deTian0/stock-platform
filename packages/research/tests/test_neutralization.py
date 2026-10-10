"""``S4`` — industry neutralization & style-exposure constraints (unit level).

Pins the neutralization kernels (``neutralization.py``) and the ``score_lvrev``
hook: the pre-``S4`` path must stay **bit-identical** when ``neutralize=None``,
and the neutralized path must actually de-mean inside each industry while
keeping the composite on its original ``[0, 1]`` scale.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_platform_research.lvrev import factor_scores, score_lvrev
from stock_platform_research.neutralization import (
    UNKNOWN_GROUP,
    NeutralizeParams,
    attach_industry,
    industry_exposure,
    industry_neutralize_series,
    neutralize_factor_scores,
    residualize,
    resolve_groups,
)


def _frame() -> pd.DataFrame:
    """Two industries × six codes; industry ``A`` is systematically stronger."""
    rows = []
    for ind, base in (("A", 0.0), ("B", 5.0)):
        for i in range(6):
            rows.append(
                {
                    "code": f"{ind}{i}",
                    "industry": ind,
                    "vol20": base + i * 0.1,
                    "rev_chg": (i - 3) * 0.05,
                }
            )
    return pd.DataFrame(rows)


# --------------------------------------------------------------- params / guard


def test_params_defaults_and_validation() -> None:
    p = NeutralizeParams()
    assert p.industry_col == "industry"
    assert p.mode == "demean"
    assert p.rescale == "rank"
    assert p.composite_demean is True
    assert p.style == ()
    with pytest.raises(ValueError):
        NeutralizeParams(mode="nope")
    with pytest.raises(ValueError):
        NeutralizeParams(rescale="nope")
    with pytest.raises(ValueError):
        NeutralizeParams(min_group_size=0)
    # ``style`` is normalised to a tuple of str (hashable / comparable).
    assert NeutralizeParams(style=["vol20"]).style == ("vol20",)


def test_resolve_groups_absent_column_and_blanks() -> None:
    df = pd.DataFrame({"code": ["a", "b", "c"], "industry": ["X", None, "  "]})
    assert list(resolve_groups(df)) == ["X", UNKNOWN_GROUP, UNKNOWN_GROUP]
    # no column at all -> one global sentinel group (graceful degradation)
    assert set(resolve_groups(pd.DataFrame({"code": ["a", "b"]}))) == {UNKNOWN_GROUP}


# -------------------------------------------------------------- neutralize core


def test_demean_exact_and_group_centred() -> None:
    s = pd.Series([1.0, 2.0, 3.0, 10.0, 20.0])
    g = pd.Series(["A", "A", "A", "B", "B"])
    out = industry_neutralize_series(s, g, mode="demean", min_group_size=1)
    assert list(out) == [-1.0, 0.0, 1.0, -5.0, 5.0]


def test_small_group_is_left_raw() -> None:
    s = pd.Series([1.0, 2.0, 3.0, 10.0, 20.0])
    g = pd.Series(["A", "A", "A", "B", "B"])
    out = industry_neutralize_series(s, g, mode="demean", min_group_size=3)
    assert list(out) == [-1.0, 0.0, 1.0, 10.0, 20.0]  # B (n=2) untouched


def test_zscore_std_floor_and_clip() -> None:
    flat = pd.Series([0.0, 0.0, 0.0])
    g = pd.Series(["A", "A", "A"])
    out = industry_neutralize_series(flat, g, mode="zscore", min_group_size=1)
    assert list(out) == [0.0, 0.0, 0.0]  # zero std -> floor, not inf/NaN

    s = pd.Series([0.0] * 100 + [100.0])
    g = pd.Series(["A"] * 101)
    out = industry_neutralize_series(s, g, mode="zscore", min_group_size=1, clip=3.0)
    assert out.max() == pytest.approx(3.0)
    assert out.min() >= -3.0 - 1e-12


def test_neutralize_does_not_mutate_input() -> None:
    s = pd.Series([1.0, 2.0, 3.0])
    g = pd.Series(["A", "A", "A"])
    before = s.copy()
    industry_neutralize_series(s, g, min_group_size=1)
    pd.testing.assert_series_equal(s, before)


# ------------------------------------------------------------------ style resid


def test_residualize_removes_linear_relation() -> None:
    x = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    s = 2.0 * x + 5.0
    out = residualize(s, x, min_rows=3)
    assert out.abs().max() < 1e-9


def test_residualize_keeps_raw_when_under_determined() -> None:
    x = pd.Series([1.0, 2.0])
    s = pd.Series([10.0, 20.0])
    out = residualize(s, x, min_rows=5)
    assert list(out) == [10.0, 20.0]


def test_residualize_clip_bounds_outliers() -> None:
    x = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 999.0])
    out = residualize(s, x, min_rows=3, clip=1.0)
    assert out.abs().max() <= 1.0 + 1e-12


# --------------------------------------------------------- frame-level helpers


def test_neutralize_factor_scores_rank_rescale_is_bounded_and_ordered() -> None:
    frame = _frame()
    fs = factor_scores(frame)
    out = neutralize_factor_scores(
        fs, frame, NeutralizeParams(min_group_size=1, rescale="rank")
    )
    assert list(out.columns) == list(fs.columns)  # column order preserved
    for col in out.columns:
        assert out[col].min() >= 0.0 and out[col].max() <= 1.0


def test_neutralize_factor_scores_demean_zeroes_group_means() -> None:
    frame = _frame()
    fs = factor_scores(frame)
    out = neutralize_factor_scores(
        fs, frame, NeutralizeParams(min_group_size=1, rescale="none")
    )
    for col in out.columns:
        means = out[col].groupby(frame["industry"]).mean()
        assert means.abs().max() < 1e-9


def test_neutralize_factor_scores_applies_style_residualization() -> None:
    frame = _frame()
    # A *single* group (so the industry step only subtracts the global mean and a
    # linear score stays linear), then a score that is linear in vol20. The style
    # step must remove that exposure exactly. (With several groups the de-mean
    # already breaks global linearity, so this is tested in isolation on purpose.)
    frame["one"] = "ALL"
    scores = pd.DataFrame({"f": 0.5 * frame["vol20"] + 1.0}, index=frame.index)
    neu = NeutralizeParams(industry_col="one", min_group_size=1, rescale="none")
    plain = neutralize_factor_scores(scores, frame, neu)
    styled = neutralize_factor_scores(
        scores, frame, NeutralizeParams(industry_col="one", min_group_size=1,
                                        rescale="none", style=("vol20",))
    )
    r_plain = np.corrcoef(plain["f"], frame["vol20"])[0, 1]
    assert abs(r_plain) == pytest.approx(1.0)   # the exposure is present …
    # … and the residual carries none of it: values collapse to machine epsilon.
    # (A *correlation* assertion would be meaningless here — correlating pure
    # 1e-16 floating-point residue with the exposure returns an arbitrary number.)
    assert styled["f"].abs().max() < 1e-9


def test_attach_industry_is_a_noop_on_an_empty_frame() -> None:
    empty = pd.DataFrame({"code": [], "close": []})
    out = attach_industry(empty, {"000001": "银行"})
    assert list(out.columns) == ["code", "close"]


# ------------------------------------------------------------ industry plumbing


def test_attach_industry_normalises_suffix_and_blanks() -> None:
    frame = pd.DataFrame({"code": ["000001.SZ", "600000.SH", "300750.SZ"], "close": [1, 2, 3]})
    mapping = {"000001": "银行", "600000": "银行"}
    out = attach_industry(frame, mapping)
    assert list(out["industry"]) == ["银行", "银行", UNKNOWN_GROUP]
    assert "industry" not in frame.columns  # input untouched
    assert attach_industry(frame, None) is frame  # default-off is a no-op


def test_industry_exposure_profile() -> None:
    exp = industry_exposure(["a", "b", "c", "d"], {"a": "X", "b": "X", "c": "Y"})
    assert exp["n_codes"] == 4
    assert exp["n_industries"] == 3  # X, Y, UNKNOWN
    assert exp["max_weight"] == pytest.approx(0.5)
    assert exp["max_industry"] == "X"
    assert exp["hhi"] == pytest.approx(0.375)
    empty = industry_exposure([], {"a": "X"})
    assert empty["n_codes"] == 0 and empty["max_industry"] is None


# ------------------------------------------------------------------ lvrev hook


def test_score_lvrev_none_is_bit_identical() -> None:
    frame = _frame()
    base = score_lvrev(frame)
    explicit = score_lvrev(frame, neutralize=None)
    pd.testing.assert_series_equal(base["composite_score"], explicit["composite_score"])
    pd.testing.assert_frame_equal(base, explicit)


def test_score_lvrev_neutralize_changes_composite_and_stays_bounded() -> None:
    frame = _frame()
    raw = score_lvrev(frame)
    neu = score_lvrev(frame, neutralize=NeutralizeParams(min_group_size=1))
    # neutralization bites: the composite is no longer the raw weighted sum
    with pytest.raises(AssertionError):
        pd.testing.assert_series_equal(
            raw["composite_score"], neu["composite_score"]
        )
    assert neu["composite_score"].between(0.0, 1.0).all()
    assert neu["composite_score"].is_monotonic_decreasing


def test_score_lvrev_composite_demean_can_be_disabled() -> None:
    frame = _frame()
    neu = NeutralizeParams(min_group_size=1, composite_demean=False)
    out = score_lvrev(frame, neutralize=neu)
    assert out["composite_score"].between(0.0, 1.0).all()
