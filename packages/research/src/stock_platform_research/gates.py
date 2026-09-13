"""Entry / risk gates shared by lvrev live and backtest paths."""

from __future__ import annotations

import pandas as pd


def apply_entry_gates(df: pd.DataFrame, reversal_q: float = 0.30) -> pd.Series:
    """Boolean mask: True = pass (buyable). Ported from a-stock-engine lvrev_scorer."""
    if len(df) == 0:
        return pd.Series([], dtype=bool)

    keep = pd.Series(True, index=df.index)

    vol_med = (
        float(df["vol20"].median())
        if "vol20" in df.columns and df["vol20"].notna().any()
        else float("inf")
    )
    chg_q = (
        float(df["rev_chg"].quantile(reversal_q))
        if "rev_chg" in df.columns and df["rev_chg"].notna().any()
        else -0.05
    )

    for idx, row in df.iterrows():
        close = row.get("close")
        ma20 = row.get("ma20")
        ma60 = row.get("ma60")
        vol = row.get("vol20")
        rev = row.get("rev_chg")

        if ma20 is not None and ma60 is not None and not pd.isna(ma20) and not pd.isna(ma60):
            if ma20 <= ma60:
                keep[idx] = False
                continue
        if ma20 is not None and close is not None and not pd.isna(ma20) and ma20 > 0:
            if close < ma20 * 0.93:
                keep[idx] = False
                continue
        if rev is not None and not pd.isna(rev) and rev > chg_q:
            keep[idx] = False
            continue
        if ma60 is not None and close is not None and not pd.isna(ma60) and ma60 > 0:
            if close < ma60 * 0.93:
                keep[idx] = False
                continue
        if vol is not None and not pd.isna(vol) and vol_med != float("inf"):
            if vol > vol_med:
                keep[idx] = False
                continue

    return keep


def apply_risk_gates(df: pd.DataFrame) -> pd.DataFrame:
    """Filter by trend_up / rs20 soft floor when columns exist (engine factor_engine)."""
    c = df.copy()
    if "trend_up" in c.columns:
        c = c[c["trend_up"] == True]  # noqa: E712
    if "rs20" in c.columns:
        c = c[c["rs20"] >= -8.0]
    return c
