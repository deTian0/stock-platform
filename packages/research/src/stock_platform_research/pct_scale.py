"""Single source of truth for the **scale** of ``daily_price.pct_chg``.

The engine dump ships ``pct_chg`` on a *mixed* scale: essentially every stock
row carries a **fraction** (``0.0123`` == 1.23 %) while essentially every ETF row
carries **percent points** (``1.23`` == 1.23 %). The naive ``|x| > 0.5``
heuristic gets this wrong in both directions — an IPO's +86.9 % first session is
a *fraction* that exceeds ``0.5``, and an ETF's 0.94 % session is a *point* value
that does not.

So the scale is pinned by **fitting the ``close`` series**: a row votes
*fraction* when reading ``pct_chg`` as a fraction lands closer to the
``close``-implied return than reading it as percent points. Corporate actions
(splits / dividends) would poison that test, so rows whose implied move exceeds
the widest board limit are dropped from the vote. Codes without enough votable
sessions (IPOs, one-off listings) fall back to an **asset-class prior** rather
than being guessed from noise.

``rules.is_limit_up`` / ``rules.is_limit_down`` are contracted on **percent
points** (:data:`SCALE_POINTS`); everything that feeds them is expected to have
been through :func:`detect_pct_scale` first. This is the one definition — no
caller re-implements it.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .portfolio import asset_class

SCALE_FRACTION = "fraction"
SCALE_POINTS = "points"

# ±20 % is the widest A-share board limit, so a close-to-close move beyond this
# cannot be a genuine daily return — it marks a corporate action whose implied
# return is unusable for scale voting.
MAX_IMPLIED = 0.21

# Below this many votable sessions the per-code verdict falls back to the
# asset-class prior (stocks → fraction, funds / ETFs → percent points).
MIN_VOTES = 10

__all__ = [
    "MAX_IMPLIED",
    "MIN_VOTES",
    "SCALE_FRACTION",
    "SCALE_POINTS",
    "detect_pct_scale",
    "normalize_pct_chg",
    "to_points",
]


def detect_pct_scale(
    bars: pd.DataFrame,
    *,
    min_votes: int = MIN_VOTES,
    max_implied: float = MAX_IMPLIED,
) -> pd.Series:
    """Per-code verdict: is ``pct_chg`` a :data:`SCALE_FRACTION` or :data:`SCALE_POINTS`?

    ``bars`` needs ``code`` / ``close`` / ``pct_chg``. Returns a
    ``Series[code -> scale]`` covering **every** code seen, so callers can map it
    straight back onto the frame. Codes with fewer than ``min_votes`` usable rows
    get the asset-class prior instead of a vote.
    """
    if "pct_chg" not in bars.columns or "close" not in bars.columns:
        return pd.Series(dtype=object)

    codes = bars["code"].astype(str)
    frame = pd.DataFrame(
        {
            "code": codes,
            "close": pd.to_numeric(bars["close"], errors="coerce"),
            "pct": pd.to_numeric(bars["pct_chg"], errors="coerce"),
        }
    )
    implied = frame.groupby("code", sort=False)["close"].pct_change()
    usable = implied.notna() & implied.abs().le(max_implied) & frame["pct"].notna()

    verdict: dict[str, str] = {}
    if usable.any():
        sub = frame[usable]
        err_fraction = (sub["pct"] - implied[usable]).abs()
        err_points = (sub["pct"] / 100.0 - implied[usable]).abs()
        vote = (err_fraction <= err_points).astype(float)  # 1.0 -> fraction
        agg = vote.groupby(sub["code"]).agg(["mean", "size"])
        trusted = agg["size"] >= min_votes
        for code, mean in agg.loc[trusted, "mean"].items():
            verdict[str(code)] = SCALE_FRACTION if float(mean) >= 0.5 else SCALE_POINTS

    # Asset-class prior for anything without a trustworthy vote.
    for code in codes.drop_duplicates():
        key = str(code)
        if key not in verdict:
            verdict[key] = SCALE_FRACTION if asset_class(key) == "stock" else SCALE_POINTS

    return pd.Series(verdict, dtype=object).sort_index()


def to_points(pct: Any, scale: str) -> Any:
    """Convert one ``pct_chg`` value to **percent points** (the ``rules`` contract)."""
    values = pd.to_numeric(pct, errors="coerce")
    return values * 100.0 if scale == SCALE_FRACTION else values


def normalize_pct_chg(
    bars: pd.DataFrame,
    *,
    min_votes: int = MIN_VOTES,
    max_implied: float = MAX_IMPLIED,
) -> tuple[pd.Series, pd.Series]:
    """``(points, row_scale)`` — ``pct_chg`` normalised to percent points.

    ``points`` is index-aligned with ``bars``; ``row_scale`` is each row's own
    scale label (useful for diagnostics and assertions). Missing values stay NaN
    — nothing is fabricated to ``0``.
    """
    scales = detect_pct_scale(bars, min_votes=min_votes, max_implied=max_implied)
    row_scale = bars["code"].astype(str).map(scales)
    pct = pd.to_numeric(bars["pct_chg"], errors="coerce")
    points = np.where(row_scale.eq(SCALE_FRACTION), pct * 100.0, pct)
    return pd.Series(points, index=bars.index, dtype="float64"), row_scale
