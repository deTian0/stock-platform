"""Entry / risk gates shared by lvrev live and backtest paths."""

from __future__ import annotations

import pandas as pd


def apply_entry_gates(df: pd.DataFrame, reversal_q: float = 0.30) -> pd.Series:
    """Boolean mask: True = pass (buyable). Ported from a-stock-engine lvrev_scorer.

    Vectorised (B1). The original row-wise loop cost ~8.8M ``iterrows`` calls on
    a full-market backtest (1621 sessions × ~5400 codes). Every branch of that
    loop **rejects** the row, so it is exactly equivalent to "reject if ANY
    condition holds" — which broadcasts over the frame. Semantics are unchanged;
    ``tests/test_gates.py`` proves equivalence against a reference loop.
    """
    if len(df) == 0:
        return pd.Series([], dtype=bool)

    nan = pd.Series(float("nan"), index=df.index)

    def col(name: str) -> pd.Series:
        return df[name] if name in df.columns else nan

    close = col("close")
    ma20 = col("ma20")
    ma60 = col("ma60")
    vol = col("vol20")
    rev = col("rev_chg")

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

    keep = pd.Series(True, index=df.index)
    # 1. downtrend: MA20 below MA60
    keep &= ~(ma20.notna() & ma60.notna() & (ma20 <= ma60))
    # 2. price too far below MA20
    keep &= ~(ma20.notna() & close.notna() & (ma20 > 0) & (close < ma20 * 0.93))
    # 3. not oversold enough on the cross-section
    keep &= ~(rev.notna() & (rev > chg_q))
    # 4. price too far below MA60
    keep &= ~(ma60.notna() & close.notna() & (ma60 > 0) & (close < ma60 * 0.93))
    # 5. noisier than the market median
    if vol_med != float("inf"):
        keep &= ~(vol.notna() & (vol > vol_med))
    return keep


def apply_risk_gates(df: pd.DataFrame) -> pd.DataFrame:
    """Filter by trend_up / rs20 soft floor when columns exist (engine factor_engine)."""
    c = df.copy()
    if "trend_up" in c.columns:
        c = c[c["trend_up"] == True]  # noqa: E712
    if "rs20" in c.columns:
        c = c[c["rs20"] >= -8.0]
    return c
