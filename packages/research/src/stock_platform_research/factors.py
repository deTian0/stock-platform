"""Factor library (milestone ``S2``).

Single mathematical source for research factors **beyond** the two that lvrev
actually weights (``low_vol`` 0.5 + ``reversal`` 0.5). Every factor is a pure
function of a PIT feature frame — no network, no DB, no side effects.

The library carries three *new orthogonal* factors next to the two baseline
ones (acceptance: "在 lvrev（低波 0.5 + 反转 0.5）之外新增至少 2 个正交因子"):

===========  ===============================================================
name         idea
===========  ===============================================================
``long_reversal``
             6-month reversal — ``-(close.shift(20) / close.shift(120) - 1)``;
             skips the most recent month so it does not re-measure the same
             20-day window as ``reversal``. Declared ``+1`` because in A-shares
             medium-term momentum is absent / inverted (long-horizon reversal).
``max_ret``  MAX / lottery demand — trailing 20-day **maximum** daily return
             (``ret1``). Extreme single-day spikes predict *lower* forward
             returns, so its intended sign is negative.
``illiq``    Amihud illiquidity — trailing 20-day mean of ``|ret1| / amount``,
             scaled by ``1e9``. Needs the ``amount`` column (present in the
             engine ``daily_price`` dump).
===========  ===============================================================

Each :class:`FactorSpec` declares the **intended sign** (``direction``) of the
factor→forward-return relation; :mod:`factor_ic` uses it to decide admission.
Nothing here is enabled by default — the lvrev composite keeps ``vol=0.5,
rev=0.5`` and the new weights default to ``0`` (see :func:`lvrev.score_lvrev`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

import pandas as pd

#: 6-month reversal: skip the most recent ``LONG_REV_SKIP`` bars (≈ 1 month) …
LONG_REV_SKIP = 20
#: … then measure the return ``LONG_REV_LOOKBACK`` bars back (≈ 6 months).
LONG_REV_LOOKBACK = 120
#: trailing window for the MAX (lottery) factor.
MAX_WINDOW = 20
#: trailing window for the Amihud illiquidity factor.
ILLIQ_WINDOW = 20
#: readability scale for Amihud (raw values are ~1e-9).
ILLIQ_SCALE = 1e9

#: the two factors lvrev already weights (kept for IC/ICIR bookkeeping).
BASELINE_FACTORS: tuple[str, ...] = ("low_vol", "reversal")
#: the new orthogonal factors introduced by ``S2``.
NEW_FACTORS: tuple[str, ...] = ("long_reversal", "max_ret", "illiq")


@dataclass(frozen=True)
class FactorSpec:
    """One library factor: a PIT-safe computation + its intended direction."""

    name: str
    label: str
    direction: int  # +1 / -1 — intended sign of ``factor -> forward return``
    description: str
    compute: Callable[[pd.DataFrame], pd.Series]


def _rolling_by_code(df: pd.DataFrame, series: pd.Series, window: int, how: str) -> pd.Series:
    """Trailing ``window`` aggregate of ``series`` within each ``code``.

    Mirrors the ``groupby(...).rolling(...).reset_index(level=0, drop=True)``
    idiom already used in :func:`backtest.compute_features`, and re-pins the
    index to the input frame so the result always aligns 1:1.
    """
    grouped = series.groupby(df["code"], sort=False)
    rolling = grouped.rolling(window, min_periods=window)
    out = getattr(rolling, how)().reset_index(level=0, drop=True)
    return out.set_axis(df.index)


def _low_vol(df: pd.DataFrame) -> pd.Series:
    """Baseline: raw 20-day realised vol (lower is better → direction ``-1``)."""
    if "vol20" in df.columns:
        return df["vol20"].astype(float)
    return pd.Series(float("nan"), index=df.index)


def _reversal(df: pd.DataFrame) -> pd.Series:
    """Baseline: raw 20-day price change (recent losers revert → direction ``-1``)."""
    if "rev_chg" in df.columns:
        return df["rev_chg"].astype(float)
    return pd.Series(float("nan"), index=df.index)


def _long_reversal(df: pd.DataFrame) -> pd.Series:
    """6-month **reversal** — negated 12-1 return, orthogonal to the 20-day one.

    Declared direction ``+1``: a *lower* past 6-month return predicts a higher
    forward return. The realised IC sign measured by
    :func:`factor_ic.build_factor_ic_report` must agree, else the factor is
    **not** enabled.
    """
    close = df.groupby("code", sort=False)["close"]
    out = -(close.shift(LONG_REV_SKIP) / close.shift(LONG_REV_LOOKBACK) - 1.0)
    return out.set_axis(df.index)


def _max_ret(df: pd.DataFrame) -> pd.Series:
    """Trailing 20-day maximum daily return (MAX / lottery demand)."""
    if "ret1" not in df.columns:
        return pd.Series(float("nan"), index=df.index)
    return _rolling_by_code(df, df["ret1"].astype(float), MAX_WINDOW, "max")


def _illiq(df: pd.DataFrame) -> pd.Series:
    """Amihud illiquidity: mean ``|ret1| / amount`` over 20 days, scaled."""
    if "ret1" not in df.columns or "amount" not in df.columns:
        return pd.Series(float("nan"), index=df.index)
    amount = df["amount"].astype(float)
    per_bar = df["ret1"].abs() / amount.where(amount > 0)
    return _rolling_by_code(df, per_bar, ILLIQ_WINDOW, "mean") * ILLIQ_SCALE


#: Registry — ``name -> FactorSpec`` (insertion order is the report order).
FACTOR_LIBRARY: dict[str, FactorSpec] = {
    "low_vol": FactorSpec(
        "low_vol", "低波动", -1,
        "20 日已实现波动率；越低越好（基线因子）", _low_vol,
    ),
    "reversal": FactorSpec(
        "reversal", "短期反转", -1,
        "过去 20 个交易日涨幅；近期弱者反弹（基线因子）", _reversal,
    ),
    "long_reversal": FactorSpec(
        "long_reversal", "6 个月反转", +1,
        "-(close.shift(20)/close.shift(120)-1)；跳过最近一月，与 20 日反转正交（新增）", _long_reversal,
    ),
    "max_ret": FactorSpec(
        "max_ret", "极端收益 MAX", -1,
        "过去 20 日单日最大涨幅（彩票偏好）；越高未来收益越低（新增）", _max_ret,
    ),
    "illiq": FactorSpec(
        "illiq", "Amihud 非流动性", +1,
        "过去 20 日 mean(|ret1|/amount)×1e9；越不流动预期收益越高（新增）", _illiq,
    ),
}


def list_factors() -> list[str]:
    """Library factor names in registry order."""
    return list(FACTOR_LIBRARY)


def factor_spec(name: str) -> FactorSpec:
    """Look up a :class:`FactorSpec`; raises ``KeyError`` for unknown names."""
    try:
        return FACTOR_LIBRARY[name]
    except KeyError as exc:  # pragma: no cover - defensive
        raise KeyError(
            f"unknown factor: {name!r}; known={list(FACTOR_LIBRARY)}"
        ) from exc


def build_feature_frame(bars: pd.DataFrame, *, pct_scale: str = "auto") -> pd.DataFrame:
    """Bars → feature frame with the extra columns the new factors need.

    Thin wrapper over :func:`backtest.compute_features` (the single point for
    PIT feature construction & corporate-action adjustment) that also keeps the
    raw ``vol`` / ``amount`` columns. ``compute_features`` is untouched for every
    existing caller because ``keep_extra`` defaults to empty.
    """
    from .backtest import compute_features

    return compute_features(bars, pct_scale=pct_scale, keep_extra=("vol", "amount"))


def build_factor_frame(
    feats: pd.DataFrame,
    *,
    factors: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Raw factor values for every library factor as columns.

    Input must be a frame carrying ``code`` and (for the momentum factor)
    ``close``; ``vol20`` / ``rev_chg`` / ``ret1`` / ``amount`` light up the
    corresponding factors. Missing inputs yield ``NaN`` columns rather than a
    hard failure, so a partial frame degrades gracefully.
    """
    names: Iterable[str] = list(factors) if factors is not None else list(FACTOR_LIBRARY)
    data = {name: factor_spec(name).compute(feats) for name in names}
    return pd.DataFrame(data, index=feats.index)


def factor_correlation(frame: pd.DataFrame) -> pd.DataFrame:
    """Pairwise Spearman correlation of raw factor columns (orthogonality check).

    Spearman == Pearson on ranks, computed with plain pandas/numpy so the module
    stays **scipy-free** (``DataFrame.corr(method="spearman")`` would import
    ``scipy.stats``). NaN pairs are dropped pairwise, matching pandas semantics.
    """
    return frame.rank().corr()
