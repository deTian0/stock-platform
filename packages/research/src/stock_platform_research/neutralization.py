"""Industry neutralization & style-exposure constraints (milestone ``S4``).

Convention ported from ``a-stock-engine/src/factor_engine.py``:

- ``_zscore`` — **industry-grouped z-score** of a raw factor: group mean/std,
  ``clip(lower=0.001)`` on the std, result clipped to ±3;
- composite de-mean — ``raw - groupby("sector")["raw"].transform("mean")``.

Platform scoring is *rank*-based (``lvrev.factor_scores`` yields ``[0, 1]``
percentile ranks) rather than z-based, so the same convention is expressed on
the **score frame**:

===========================================  =============================
``mode``                                      per-industry transform
===========================================  =============================
``"demean"`` (default)                        ``s - group_mean(s)``
``"zscore"``                                  ``(s - group_mean) / max(group_std, eps)``
===========================================  =============================

Because both transforms move the score out of ``[0, 1]``, ``rescale="rank"``
(default) re-maps each neutralized factor to ``[0, 1]`` by a global percentile
rank — this *preserves* the ordering the neutralization produced while keeping
the downstream ``min_pick_score`` floor on its original scale.

Style exposures (``style=("vol20", ...)``) are removed by per-industry OLS
residualization against those columns (:func:`residualize`).

**Nothing here runs unless a caller passes a :class:`NeutralizeParams` down to**
:func:`lvrev.score_lvrev`; leaving it ``None`` reproduces the pre-``S4``
composite bit-for-bit. This module is pure: no network, no DB, no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

#: Rows with no industry label land in this self-contained group.
UNKNOWN_GROUP = "__UNKNOWN__"
#: Floor on a group's std so ``zscore`` cannot divide by zero.
STD_FLOOR = 0.001
#: Supported per-industry transforms.
NEUTRALIZE_MODES = ("demean", "zscore")
#: Supported post-neutralization rescalings.
NEUTRALIZE_RESCALES = ("rank", "none")


@dataclass(frozen=True)
class NeutralizeParams:
    """Every knob of the ``S4`` neutralization step.

    The defaults describe *industry de-mean + rank rescale* — the mildest
    useful configuration. Constructing one and passing it to
    :func:`lvrev.score_lvrev` is the **only** way to turn neutralization on.
    """

    #: column on the scored frame that carries the industry label.
    industry_col: str = "industry"
    #: ``"demean"`` (subtract group mean) or ``"zscore"`` (group z, clipped).
    mode: str = "demean"
    #: clip bound for ``mode="zscore"``.
    clip: float = 3.0
    #: groups with fewer members than this are left **raw** (no meaningful cross-section).
    min_group_size: int = 5
    #: ``"rank"`` re-maps each neutralized factor to ``[0, 1]``; ``"none"`` keeps the raw scale.
    rescale: str = "rank"
    #: additionally de-mean the *composite* per industry (faithful to the engine).
    composite_demean: bool = True
    #: style-exposure columns to orthogonalize each factor against (e.g. ``("vol20",)``).
    style: tuple[str, ...] = ()
    #: clip bound on the style residuals (``None`` disables).
    style_clip: float | None = 3.0

    def __post_init__(self) -> None:
        if self.mode not in NEUTRALIZE_MODES:
            raise ValueError(
                f"mode must be one of {NEUTRALIZE_MODES}, got {self.mode!r}"
            )
        if self.rescale not in NEUTRALIZE_RESCALES:
            raise ValueError(
                f"rescale must be one of {NEUTRALIZE_RESCALES}, got {self.rescale!r}"
            )
        if self.min_group_size < 1:
            raise ValueError("min_group_size must be >= 1")
        # normalise ``style`` to a tuple of str for hashability/equality.
        object.__setattr__(self, "style", tuple(str(c) for c in self.style))


def resolve_groups(
    source: pd.DataFrame,
    *,
    col: str = "industry",
    unknown: str = UNKNOWN_GROUP,
) -> pd.Series:
    """Industry label per row; missing / blank labels become one ``unknown`` group.

    When ``col`` is absent entirely the whole cross-section collapses into a
    single ``unknown`` group — neutralization then degrades gracefully to a
    **global** de-mean (never a crash, never a silent no-op).
    """
    if col not in source.columns:
        return pd.Series(unknown, index=source.index, dtype="object")
    raw = source[col]
    blank = raw.isna() | (raw.astype(str).str.strip() == "")
    return raw.astype(object).where(~blank, unknown).astype(str)


def _rank01(s: pd.Series) -> pd.Series:
    """Global percentile rank in ``[0, 1]``; NaN → neutral ``0.5`` (lvrev convention)."""
    return s.rank(pct=True, na_option="keep").fillna(0.5)


def industry_neutralize_series(
    s: pd.Series,
    groups: pd.Series,
    *,
    mode: str = "demean",
    clip: float = 3.0,
    min_group_size: int = 5,
) -> pd.Series:
    """Neutralize one score series against industry groups.

    Groups smaller than ``min_group_size`` keep their **raw** values; every
    other row is de-meaned (``"demean"``) or z-scored and clipped
    (``"zscore"``). The input series is never mutated.
    """
    if mode not in NEUTRALIZE_MODES:
        raise ValueError(f"mode must be one of {NEUTRALIZE_MODES}, got {mode!r}")
    vals = pd.Series(s).astype(float)
    grp = pd.Series(groups).reindex(vals.index)
    grouped = vals.groupby(grp, sort=False)
    mean = grouped.transform("mean")
    if mode == "zscore":
        std = grouped.transform("std").clip(lower=STD_FLOOR)
        adjusted = ((vals - mean) / std).clip(-float(clip), float(clip))
    else:
        adjusted = vals - mean
    big = grouped.transform("count") >= int(min_group_size)
    return adjusted.where(big, vals)


def residualize(
    s: pd.Series,
    exposures: pd.DataFrame | pd.Series,
    *,
    groups: pd.Series | None = None,
    clip: float | None = None,
    min_rows: int = 5,
) -> pd.Series:
    """OLS residual of ``s`` on ``exposures`` (with intercept), fitted **per group**.

    Rows with a missing ``s`` or a missing exposure keep their raw value (they
    never enter the fit). A group with fewer than ``max(min_rows, k+2)`` usable
    rows is left raw — an under-determined fit is worse than none.
    """
    vals = pd.Series(s).astype(float)
    if isinstance(exposures, pd.Series):
        exposures = exposures.to_frame()
    X = exposures.astype(float).reindex(vals.index)
    if X.shape[1] == 0:
        return vals.copy()
    if groups is None:
        groups = pd.Series("__ALL__", index=vals.index, dtype="object")
    grp = pd.Series(groups).reindex(vals.index)
    out = vals.copy()
    for _, idx in grp.groupby(grp, sort=False).groups.items():
        idx = pd.Index(idx)
        yv = vals.loc[idx].to_numpy(dtype=float)
        Xv = X.loc[idx].to_numpy(dtype=float)
        ok = np.isfinite(yv) & np.isfinite(Xv).all(axis=1)
        need = max(int(min_rows), Xv.shape[1] + 2)
        if int(ok.sum()) < need:
            continue
        design = np.column_stack([np.ones(int(ok.sum())), Xv[ok]])
        coef, *_ = np.linalg.lstsq(design, yv[ok], rcond=None)
        resid = yv[ok] - design @ coef
        if clip is not None:
            resid = np.clip(resid, -float(clip), float(clip))
        out.loc[pd.Index(idx)[ok]] = resid
    return out


def neutralize_factor_scores(
    scores: pd.DataFrame,
    source: pd.DataFrame,
    params: NeutralizeParams,
) -> pd.DataFrame:
    """Apply industry (and optional style) neutralization to a factor-score frame.

    ``scores`` holds one column per factor (``lvrev.factor_scores`` output);
    ``source`` is the frame the scores were computed from — it carries the
    industry label and any style-exposure columns. Column order and index are
    preserved.
    """
    groups = resolve_groups(source, col=params.industry_col)
    style_cols: Sequence[str] = tuple(
        c for c in params.style if c in source.columns
    )
    out: dict[str, pd.Series] = {}
    for name in scores.columns:
        col = industry_neutralize_series(
            scores[name],
            groups,
            mode=params.mode,
            clip=params.clip,
            min_group_size=params.min_group_size,
        )
        if style_cols:
            col = residualize(
                col,
                source[list(style_cols)],
                groups=groups,
                clip=params.style_clip,
            )
        if params.rescale == "rank":
            col = _rank01(col)
        out[name] = col
    return pd.DataFrame(out, index=scores.index)


def attach_industry(
    frame: pd.DataFrame,
    mapping: Mapping[str, str] | None,
    *,
    col: str = "industry",
) -> pd.DataFrame:
    """Add an industry label column from a ``code -> industry`` mapping.

    ``mapping=None`` returns the frame unchanged (the pre-``S4`` behaviour). An
    unmapped or blank code receives :data:`UNKNOWN_GROUP` so downstream grouping
    stays total. The input frame is never mutated.
    """
    if mapping is None or frame.empty:
        # nothing to label; also protects the ``prepare_book_frame`` empty-frame
        # path (an empty frame carries no columns after ``compute_features``).
        return frame
    if "code" not in frame.columns:
        raise ValueError("attach_industry requires a 'code' column")
    out = frame.copy()
    # engine ``daily_price.code`` is ``000001.SZ`` while ``fundamentals.code`` is
    # bare ``000001`` — both sides go through ``portfolio.norm_code`` (the single
    # 6-digit normalisation used by the asset-class / stamp-exemption rules).
    from .portfolio import norm_code

    lookup = {norm_code(k): str(v) for k, v in mapping.items() if v is not None}
    codes = out["code"].astype(str).str.replace(".", "", regex=False).str[:6]
    labels = codes.map(lookup)
    blank = labels.isna() | (labels.astype(str).str.strip() == "")
    out[col] = labels.where(~blank, UNKNOWN_GROUP).astype(str)
    return out


def industry_exposure(
    codes: Iterable[str],
    mapping: Mapping[str, str] | None,
) -> dict[str, float]:
    """Industry weight profile of a code list (equal weight), for A/B diagnostics.

    Returns ``{"n_codes", "n_industries", "max_weight", "max_industry", "hhi"}``.
    An empty list → all zeros with ``max_industry=None``. Unmapped codes collapse
    into :data:`UNKNOWN_GROUP`, so the weights always sum to 1.
    """
    codes = [str(c) for c in codes]
    n = len(codes)
    if n == 0:
        return {
            "n_codes": 0,
            "n_industries": 0,
            "max_weight": 0.0,
            "max_industry": None,
            "hhi": 0.0,
        }
    from .portfolio import norm_code

    lookup = {norm_code(k): str(v) for k, v in (mapping or {}).items() if v is not None}
    labels = [lookup.get(norm_code(c), UNKNOWN_GROUP) for c in codes]
    counts: dict[str, int] = {}
    for lab in labels:
        counts[lab] = counts.get(lab, 0) + 1
    weights = {k: v / n for k, v in counts.items()}
    top = max(weights.items(), key=lambda kv: kv[1])
    return {
        "n_codes": n,
        "n_industries": len(weights),
        "max_weight": float(top[1]),
        "max_industry": top[0],
        "hhi": float(sum(w * w for w in weights.values())),
    }


__all__ = [
    "NEUTRALIZE_MODES",
    "NEUTRALIZE_RESCALES",
    "STD_FLOOR",
    "UNKNOWN_GROUP",
    "NeutralizeParams",
    "attach_industry",
    "industry_exposure",
    "industry_neutralize_series",
    "neutralize_factor_scores",
    "residualize",
    "resolve_groups",
]
