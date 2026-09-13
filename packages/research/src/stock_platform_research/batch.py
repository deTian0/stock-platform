"""Batch cross-section scoring for pre-market brief style workflows."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .gates import apply_entry_gates, apply_risk_gates
from .lvrev import score_lvrev


def score_cross_section(
    df: pd.DataFrame,
    *,
    value_factor: bool = False,
    reversal_q: float = 0.30,
    apply_gates: bool = True,
    top_n: int | None = None,
) -> pd.DataFrame:
    """Score a single-day cross-section; optionally filter by entry gates.

    Input must already be point-in-time as-of the brief date (caller responsibility).
    """
    scored = score_lvrev(df, value_factor=value_factor)
    if "trend_up" in scored.columns or "rs20" in scored.columns:
        scored = apply_risk_gates(scored)
        scored = score_lvrev(scored, value_factor=value_factor)
    if apply_gates:
        mask = apply_entry_gates(scored, reversal_q=reversal_q)
        scored = scored.loc[mask]
    if top_n is not None:
        scored = scored.head(int(top_n))
    return scored


def score_cross_section_csv(
    path: str | Path,
    *,
    output: str | Path | None = None,
    value_factor: bool = False,
    reversal_q: float = 0.30,
    top_n: int | None = 50,
) -> pd.DataFrame:
    """Load CSV → score → optional write. Used by pre-market batch jobs."""
    df = pd.read_csv(path)
    out = score_cross_section(
        df,
        value_factor=value_factor,
        reversal_q=reversal_q,
        top_n=top_n,
    )
    if output is not None:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(output, index=False)
    return out
