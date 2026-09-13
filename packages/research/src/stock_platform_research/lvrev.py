"""lvrev scorer — low-vol + reversal (+ optional quality/growth/value).

Ported from a-stock-engine ``src/lvrev_scorer.py`` (production baseline v4.29
weights). This module is the single mathematical source for research scoring
inside stock-platform.
"""

from __future__ import annotations

import pandas as pd

# Locked weights (engine v4.29 / M2 rolling re-estimate OOS).
W_DEFAULT = dict(vol=0.5, rev=0.5, value=0.0, q=0.0, g=0.0)
W_VALUE = dict(vol=0.41, rev=0.41, value=0.18, q=0.0, g=0.0)


def factor_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time factor scores in [0, 1], direction aligned to expected return."""
    d = df

    if "vol20" in d.columns:
        s_vol = d["vol20"].rank(pct=True, na_option="keep")
    else:
        s_vol = pd.Series(0.5, index=d.index)
    low_vol = 1 - s_vol.fillna(0.5)

    if "rev_chg" in d.columns:
        s_rev = (-d["rev_chg"]).rank(pct=True, na_option="keep")
    elif "chg_20d" in d.columns:
        s_rev = (-d["chg_20d"]).rank(pct=True, na_option="keep")
    elif "chg_10d" in d.columns:
        s_rev = (-d["chg_10d"]).rank(pct=True, na_option="keep")
    else:
        s_rev = pd.Series(0.5, index=d.index)
    reversal = s_rev.fillna(0.5)

    s_q = pd.Series(0.5, index=d.index)
    if "debt_ratio" in d.columns:
        s_q = s_q - (d["debt_ratio"].clip(0, 100).fillna(50) / 100.0)
    s_q = s_q.rank(pct=True, na_option="keep").fillna(0.5)
    quality = s_q

    if "revenue_growth" in d.columns:
        s_g = d["revenue_growth"].clip(-50, 100).fillna(0).rank(pct=True, na_option="keep")
    else:
        s_g = pd.Series(0.5, index=d.index)
    growth = s_g.fillna(0.5)

    if "pb" in d.columns and "ps_ttm" in d.columns:
        bp_clean = d["pb"].where(d["pb"] > 0)
        sp_clean = d["ps_ttm"].where(d["ps_ttm"] > 0)
        s_val_bp = (1.0 / bp_clean).rank(pct=True, na_option="keep").fillna(0.5)
        s_val_sp = (1.0 / sp_clean).rank(pct=True, na_option="keep").fillna(0.5)
        value = (0.6 * s_val_bp + 0.4 * s_val_sp).fillna(0.5)
    else:
        value = pd.Series(0.5, index=d.index)

    return pd.DataFrame(
        {
            "low_vol": low_vol,
            "reversal": reversal,
            "quality": quality,
            "growth": growth,
            "value": value,
        },
        index=d.index,
    )


def score_lvrev(
    df: pd.DataFrame,
    value_factor: bool = False,
    ey_weight: float = 0.0,
    weights: dict | None = None,
) -> pd.DataFrame:
    """Score cross-section; returns df sorted by ``composite_score`` descending."""
    if len(df) == 0:
        out = df.copy()
        out["composite_score"] = 0.0
        return out
    d = df.copy()
    fs = factor_scores(d)

    if ey_weight > 0 and "pe" in d.columns:
        pe_clean = d["pe"].where((d["pe"] > 0) & (d["pe"] < 300))
        ey_rank = (1.0 / pe_clean).rank(pct=True, na_option="keep").fillna(0.5)
    else:
        ey_rank = 0.0

    if weights is None:
        w = dict(W_VALUE) if value_factor else dict(W_DEFAULT)
    else:
        w = {k: float(v) for k, v in weights.items()}

    d["composite_score"] = (
        w.get("vol", 0.0) * fs["low_vol"]
        + w.get("rev", 0.0) * fs["reversal"]
        + w.get("value", 0.0) * fs["value"]
        + w.get("q", 0.0) * fs["quality"]
        + w.get("g", 0.0) * fs["growth"]
        + ey_weight * ey_rank
    )
    return d.sort_values("composite_score", ascending=False)
