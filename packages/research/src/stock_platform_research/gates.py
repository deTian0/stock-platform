"""Entry / risk gates shared by lvrev live and backtest paths."""

from __future__ import annotations

from dataclasses import dataclass, replace

import pandas as pd


@dataclass(frozen=True)
class EntryGateParams:
    """Every tunable constant of :func:`apply_entry_gates`, in one object.

    The defaults reproduce the ``a-stock-engine lvrev_scorer`` port **verbatim**,
    so ``EntryGateParams()`` is exactly the ``B1`` baseline. ``S3`` lifts the
    previously hard-coded numbers (the ``0.93`` distance-to-MA band and the
    ``vol20 > median`` filter) out of the function body so a sensitivity sweep can
    move **one** knob at a time without keeping a second copy of the gate.

    ``reversal_q`` is the cross-sectional oversold quantile (a *relative* gate);
    ``ma20_band`` / ``ma60_band`` are the distance-to-MA floors (``close < ma * band``
    rejects); ``vol_filter`` turns the "noisier than the market median" rejection
    on / off.
    """

    reversal_q: float = 0.30
    ma20_band: float = 0.93
    ma60_band: float = 0.93
    vol_filter: bool = True


def apply_entry_gates(
    df: pd.DataFrame,
    reversal_q: float | None = None,
    *,
    params: EntryGateParams | None = None,
) -> pd.Series:
    """Boolean mask: True = pass (buyable). Ported from a-stock-engine lvrev_scorer.

    Vectorised (B1). The original row-wise loop cost ~8.8M ``iterrows`` calls on
    a full-market backtest (1621 sessions × ~5400 codes). Every branch of that
    loop **rejects** the row, so it is exactly equivalent to "reject if ANY
    condition holds" — which broadcasts over the frame. Semantics are unchanged;
    ``tests/test_gates.py`` proves equivalence against a reference loop.

    Resolution order (``S3``): an explicit ``reversal_q`` argument overrides
    ``params.reversal_q``; when both are absent the ``EntryGateParams()`` default
    (``0.30``) is used, so ``apply_entry_gates(df)`` stays bit-for-bit the pre-``S3``
    behaviour.
    """
    p = params if params is not None else EntryGateParams()
    if reversal_q is not None:
        p = replace(p, reversal_q=float(reversal_q))

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
        float(df["rev_chg"].quantile(p.reversal_q))
        if "rev_chg" in df.columns and df["rev_chg"].notna().any()
        else -0.05
    )

    keep = pd.Series(True, index=df.index)
    # 1. downtrend: MA20 below MA60
    keep &= ~(ma20.notna() & ma60.notna() & (ma20 <= ma60))
    # 2. price too far below MA20
    keep &= ~(ma20.notna() & close.notna() & (ma20 > 0) & (close < ma20 * p.ma20_band))
    # 3. not oversold enough on the cross-section
    keep &= ~(rev.notna() & (rev > chg_q))
    # 4. price too far below MA60
    keep &= ~(ma60.notna() & close.notna() & (ma60 > 0) & (close < ma60 * p.ma60_band))
    # 5. noisier than the market median
    if p.vol_filter and vol_med != float("inf"):
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


__all__ = ["EntryGateParams", "apply_entry_gates", "apply_risk_gates"]
