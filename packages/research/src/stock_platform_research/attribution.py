"""收益归因 / 负收益根因诊断（milestone ``Y3``）——「这套选股逻辑为什么亏钱？」

为什么存在
----------
``Y1`` 策略采纳闸门把「已验证的改进」挡在了生产之外，并留下两条线索：

- ``R4`` 绩效代理台账（近一年长窗回测）：``avgReturn=-0.38%``、``winRate=0.3735``
  —— **近一年实际是亏的**；
- ``Y1`` 真机三个样本外窗口：基线档在所有窗口都跑输基准，而 ``gate_070`` 在 2/3 窗
  有正超额（``Δ夏普`` +0.274 / ``Δ收益`` +5.90%）。

两条线索指向同一个缺口：平台**能测**「有没有变好」，却**说不清**「为什么现在是坏的」。
于是「怎么改才赚钱」只能靠猜。本模块补上这一层：

**把一段窗口的亏损，分解成少数几项互不重叠、各自可处置的原因。**

分解口径（四问）
----------------
1. **信号有没有 edge？** —— 对未来 ``k`` 个交易日（默认 ``1/3/5/10/20/40``）的
   **平均超额收益**（个股 − 基准）与胜率曲线。
2. **是不是持有期错配？** —— **绝对收益**曲线在短端见顶后转负 ⇒ 持有过久；只在长端为正
   ⇒ 持有过短。
3. **是不是成本吃掉了？** —— 同一批成交的 ``gross_ret`` 与 ``net_ret`` 对照（佣金/
   印花税/滑点），看净收益是否被从正拖到负、或吃掉多少比例。
4. **是不是集中在某一处？** —— 按月份 / 退出原因 / 资产类别 / 行业分组，看亏损是否
   集中在少数分组（集中 ⇒ 可定点处置；分散 ⇒ 属系统性，需改信号）。

另附**赔率结构**（胜率 / 平均盈 / 平均亏 / 期望值），用来区分「输多但小赢大亏」与
「输赢对称但整体偏负」。

**为什么要分「绝对」与「相对」两个口径**（真机教训）
----------------------------------------------------
近一年实测出现过这样的曲线：**绝对收益**在 10 日见顶后转负，而**超额**只在 40 日为正。
后者是**熊市相对防守**（基准跌得更多），拿它当「信号在长周期有效」去延长持有是**错的处方**。
所以本模块把两个口径**分开归属**：

- **边缘（有没有技能）** 用 **超额** ``meanExcess`` —— 回答「跑赢基准吗」；
- **持有期（拿在手里赚不赚）** 用 **绝对** ``meanReturn`` —— 回答「赚钱吗」。

设计要点
--------
- **同一信号源**：面板用的筛选（:func:`lvrev.score_lvrev` + :func:`gates.apply_entry_gates`）
  与生产 ``screener_entry_provider`` **同源**，不另起一套打分。
- **两个样本集**：``gated``（全部过闸标的，用于检验评分单调性）与 ``picks``
  （过闸 **且** ``composite_score >= score_floor``，即候选池）。
- **纯函数裁决**：:func:`diagnose` 只吃已经算好的几个块，不碰 pandas、不碰引擎，
  阈值**事前登记**（见 ``docs/contracts/attribution.md``），可被单测穷举。
- **样本不足不作结论**：每个 horizon 的样本量低于 ``MIN_MEANINGFUL_SAMPLE`` 时标
  ``adequate=False``，裁决只用达标 horizon。
- **只出归因，不改档**：本模块**绝不**修改生产默认档、不写 brief / picks；它产出的
  「候选方向」仍须走 ``Y1`` 闸门 + 人工签核。

只读、零网络、fail-closed（缺件标 ``None`` 而非编造）；SIMULATE。非投资建议。
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import pandas as pd

from .gates import EntryGateParams, apply_entry_gates
from .lvrev import score_lvrev
from .portfolio import norm_code

#: Default output directory (platform-owned ``data/``; never the engine DB).
DEFAULT_ATTRIBUTION_OUT_DIR = "data/strategy"

#: Forward-return horizons, in **trading days**, roughly spanning the platform's
#: decision windows (``A5`` 1 日 / ``A4`` 5 日 / 引擎最长持有 ~20–40 日）。
DEFAULT_HORIZONS: tuple[int, ...] = (1, 3, 5, 10, 20, 40)

DEFAULT_SCORE_BUCKETS = 5
DEFAULT_REFERENCE_HORIZON = 5
DEFAULT_SCORE_FLOOR = 0.80

#: 与 :data:`performance.MIN_MEANINGFUL_SAMPLE` 同口径：低于此样本量不做结论。
MIN_MEANINGFUL_SAMPLE = 20

BASIS_EXCESS = "excess"
BASIS_RAW = "raw"

#: ``book_replay`` 的成交 ``gross_ret`` / ``net_ret`` 以**百分数**为单位（``+5.0`` 即 +5%）。
#: 本模块内部统一用**小数**（``+0.05``），故所有成交读数先乘 :data:`TRADE_RET_SCALE`。
TRADE_RET_SCALE = 0.01

SET_PICKS = "picks"
SET_GATED = "gated"
SET_ZH: dict[str, str] = {
    SET_PICKS: "候选池（过闸且 ≥ 评分闸门）",
    SET_GATED: "全部过闸标的（不过评分闸门）",
}

#: 事前登记的原因码 —— 每一条都对应一个可处置动作。
#: ``edge*`` / ``signal*`` 走**超额**口径；``hold*`` 走**绝对**口径（见模块 docstring）。
CAUSE_SIGNAL_NO_EDGE = "signal_no_edge"
CAUSE_NO_ABSOLUTE_EDGE = "no_absolute_edge"
CAUSE_HOLD_TOO_LONG = "hold_too_long"
CAUSE_HOLD_TOO_SHORT = "hold_too_short"
CAUSE_EDGE_ONLY_LONG_HORIZON = "edge_only_long_horizon"
CAUSE_SCORE_NOT_MONOTONIC = "score_not_monotonic"
CAUSE_SCORE_WEAK = "score_weak"
CAUSE_COST_ERODES_EDGE = "cost_erodes_edge"
CAUSE_PAYOFF_UNFAVORABLE = "payoff_unfavorable"
CAUSE_CONCENTRATED_LOSS = "concentrated_loss"
CAUSE_NO_SINGLE_CAUSE = "no_single_cause"

SEVERITY_ALERT = "alert"
SEVERITY_WARN = "warn"
SEVERITY_INFO = "info"
SEVERITY_ZH: dict[str, str] = {
    SEVERITY_ALERT: "需处置",
    SEVERITY_WARN: "值得关注",
    SEVERITY_INFO: "信息",
}
_SEVERITY_WEIGHT = {SEVERITY_ALERT: 3, SEVERITY_WARN: 2, SEVERITY_INFO: 1}

#: 同严重度下的**决定性**排序（1 = 最先看），事前登记；impact 的量纲跨原因不可比，
#: 故用它而不是 impact 做二级排序键。
_CAUSE_RANK: dict[str, int] = {
    CAUSE_SIGNAL_NO_EDGE: 1,
    CAUSE_NO_ABSOLUTE_EDGE: 2,
    CAUSE_HOLD_TOO_LONG: 3,
    CAUSE_HOLD_TOO_SHORT: 4,
    CAUSE_EDGE_ONLY_LONG_HORIZON: 5,
    CAUSE_SCORE_NOT_MONOTONIC: 6,
    CAUSE_COST_ERODES_EDGE: 7,
    CAUSE_PAYOFF_UNFAVORABLE: 8,
    CAUSE_SCORE_WEAK: 9,
    CAUSE_CONCENTRATED_LOSS: 10,
    CAUSE_NO_SINGLE_CAUSE: 99,
}

#: 事前登记阈值（写进契约，改它必须先改契约）。
COST_SHARE_WARN = 0.30
LOSS_CONCENTRATION_WARN = 0.40
SPEARMAN_FLAT = 0.05
PAYOFF_RATIO_WARN = 1.0
WINRATE_WARN = 0.50

#: 分组维度（亏损集中度）。
CONCENTRATION_KEYS = ("month", "reason", "assetClass", "industry")
CONCENTRATION_ZH: dict[str, str] = {
    "month": "月份",
    "reason": "退出原因",
    "assetClass": "资产类别",
    "industry": "行业",
}


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _num(value: Any) -> float | None:
    """NaN-safe float coercion (``None`` for missing / non-numeric / NaN)."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out


def _mean(values: Sequence[float]) -> float | None:
    return (sum(values) / len(values)) if values else None


def _median(values: Sequence[float]) -> float | None:
    return float(pd.Series(list(values)).median()) if values else None


def _value_col(basis: str, horizon: int) -> str:
    prefix = "excess" if basis == BASIS_EXCESS else "fwd"
    return f"{prefix}_{int(horizon)}"


def _spearman(a: pd.Series, b: pd.Series) -> float | None:
    """Spearman rank correlation = Pearson on ranks.

    Implemented here rather than via ``Series.corr(method="spearman")`` because
    that path imports SciPy, and the ``research`` package depends on numpy/pandas
    only (see ``pyproject``).
    """
    try:
        if a.nunique() < 2 or b.nunique() < 2:
            return None  # zero variance → correlation undefined (avoids a 0/0 warn)
        return _num(a.rank().corr(b.rank()))
    except (ValueError, TypeError):  # pragma: no cover - degenerate input
        return None


# --------------------------------------------------------------------------- #
# forward returns + benchmark alignment
# --------------------------------------------------------------------------- #
def attach_forward_returns(feats: pd.DataFrame, *, horizons: Sequence[int] = DEFAULT_HORIZONS) -> pd.DataFrame:
    """Add ``fwd_{k}`` = 该 code 自本行起 ``k`` 个**交易日**的简单收益。

    必须在**全跨度**帧上调用（含窗口尾部），否则末端的 ``shift(-k)`` 会整段缺失。
    末 ``k`` 行自然为 ``NaN``（被截尾），调用方按 horizon 统计时应剔除而非补零。
    """
    if feats is None or feats.empty:
        return pd.DataFrame() if feats is None else feats.copy()
    out = feats.sort_values(["code", "trade_date"]).copy()
    grouped = out.groupby("code", sort=False)["close"]
    for k in horizons:
        k = int(k)
        out[f"fwd_{k}"] = grouped.shift(-k) / out["close"] - 1.0
    return out


def _bench_series(bench: Any) -> pd.Series | None:
    """Normalise a benchmark into a ``DatetimeIndex → close`` series (or ``None``)."""
    if bench is None:
        return None
    if isinstance(bench, pd.DataFrame):
        if bench.empty:
            return None
        dcol = "trade_date" if "trade_date" in bench.columns else ("date" if "date" in bench.columns else None)
        if dcol is None or "close" not in bench.columns:
            raise ValueError("benchmark frame needs a date/trade_date column and a close column")
        idx = pd.to_datetime(bench[dcol], errors="coerce").dt.normalize()
        vals = pd.to_numeric(bench["close"], errors="coerce")
        series = pd.Series(vals.to_numpy(), index=pd.DatetimeIndex(idx))
    elif isinstance(bench, pd.Series):
        series = pd.to_numeric(bench, errors="coerce").copy()
        series.index = pd.to_datetime(series.index, errors="coerce").normalize()
    else:  # pragma: no cover - defensive
        raise ValueError("benchmark must be a DataFrame (date+close) or a Series")
    series = series[~series.index.isna()]
    return series[~series.index.duplicated(keep="last")].sort_index()


def prepare_benchmark(bench: Any, calendar: Sequence[Any]) -> pd.Series | None:
    """Reindex the benchmark onto the trading calendar (``ffill`` for gaps).

    A missing benchmark day is carried forward rather than dropped, so the
    benchmark stays aligned with the bar calendar used for forward returns.
    """
    series = _bench_series(bench)
    if series is None or series.empty:
        return None
    cal = pd.DatetimeIndex(pd.to_datetime(list(calendar)).normalize().unique()).sort_values()
    if len(cal) == 0:
        return None
    return series.reindex(series.index.union(cal)).ffill().reindex(cal)


def _bench_forward(bench_series: pd.Series | None, horizons: Sequence[int]) -> pd.DataFrame | None:
    """``bench_fwd_{k}`` aligned to the benchmark's own calendar."""
    if bench_series is None or bench_series.empty:
        return None
    out = pd.DataFrame(index=bench_series.index)
    for k in horizons:
        k = int(k)
        out[f"bench_fwd_{k}"] = bench_series.shift(-k) / bench_series - 1.0
    out.index.name = "trade_date"
    return out.reset_index()


# --------------------------------------------------------------------------- #
# signal panel
# --------------------------------------------------------------------------- #
def build_signal_panel(
    feats: pd.DataFrame,
    *,
    benchmark: Any = None,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    score_floor: float = DEFAULT_SCORE_FLOOR,
    gate_params: EntryGateParams | None = None,
    neutralize: Any = None,
    weights: Mapping[str, float] | None = None,
    value_factor: bool = False,
) -> dict[str, Any]:
    """Scored + gated signal rows, each carrying its forward (excess) returns.

    Returns ``{"panel", "horizons", "basis", "benchmarkAvailable", "nGated",
    "nPicks", "nDays"}``. ``panel`` has one row per ``(code, signal_date)`` that
    passed the entry gates, with ``composite_score``, ``passesFloor``, ``fwd_{k}``
    and (when a benchmark is available) ``excess_{k}``.

    Scoring is **per session** on that session's cross-section — exactly how the
    production entry provider scores — so the panel cannot drift from the engine.
    """
    horizons = tuple(int(k) for k in horizons)
    empty = {
        "panel": pd.DataFrame(),
        "horizons": list(horizons),
        "basis": BASIS_RAW,
        "benchmarkAvailable": False,
        "nGated": 0,
        "nPicks": 0,
        "nDays": 0,
    }
    if feats is None or feats.empty:
        return empty

    forward = attach_forward_returns(feats, horizons=horizons)
    fwd_cols = [f"fwd_{k}" for k in horizons]

    blocks: list[pd.DataFrame] = []
    for _day, frame in feats.groupby("trade_date", sort=True):
        scored = score_lvrev(frame, value_factor=value_factor, weights=weights, neutralize=neutralize)
        mask = apply_entry_gates(scored, params=gate_params)
        elig = scored.loc[mask]
        if elig.empty:
            continue
        keep = ["code", "trade_date", "close", "composite_score"]
        blocks.append(elig.loc[:, [c for c in keep if c in elig.columns]].copy())

    if not blocks:
        return empty

    panel = pd.concat(blocks, ignore_index=True)
    panel = panel.merge(forward[["code", "trade_date", *fwd_cols]], on=["code", "trade_date"], how="left")
    panel["passesFloor"] = pd.to_numeric(panel["composite_score"], errors="coerce") >= float(score_floor)

    calendar = pd.Index(forward["trade_date"].dropna().unique()).sort_values()
    bench_series = prepare_benchmark(benchmark, calendar)
    bench_fwd = _bench_forward(bench_series, horizons)
    if bench_fwd is not None and not bench_fwd.empty:
        panel = panel.merge(bench_fwd, on="trade_date", how="left")
        for k in horizons:
            panel[f"excess_{k}"] = pd.to_numeric(panel[f"fwd_{k}"], errors="coerce") - pd.to_numeric(
                panel[f"bench_fwd_{k}"], errors="coerce"
            )
        basis = BASIS_EXCESS
    else:
        basis = BASIS_RAW

    return {
        "panel": panel,
        "horizons": list(horizons),
        "basis": basis,
        "benchmarkAvailable": bool(bench_fwd is not None and not bench_fwd.empty),
        "nGated": int(len(panel)),
        "nPicks": int(panel["passesFloor"].sum()),
        "nDays": int(pd.Index(panel["trade_date"]).nunique()),
    }


def select_set(panel: pd.DataFrame, which: str) -> pd.DataFrame:
    """``SET_GATED`` → every gated row; ``SET_PICKS`` → only those over the floor."""
    if panel is None or panel.empty:
        return pd.DataFrame() if panel is None else panel
    if which == SET_PICKS:
        return panel[panel["passesFloor"]]
    if which == SET_GATED:
        return panel
    raise ValueError(f"which must be {SET_PICKS!r} or {SET_GATED!r}, got {which!r}")


# --------------------------------------------------------------------------- #
# block 1/2 — horizon curve + score monotonicity
# --------------------------------------------------------------------------- #
def horizon_curve(
    panel: pd.DataFrame,
    *,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    basis: str = BASIS_EXCESS,
    which: str = SET_PICKS,
    min_sample: int = MIN_MEANINGFUL_SAMPLE,
) -> list[dict[str, Any]]:
    """Mean forward (or excess) return by holding horizon for one sample set.

    Each row carries **both** ``meanReturn`` (绝对) and ``meanExcess`` (相对) whenever
    they are computable — :func:`diagnose` attributes them to different questions.
    """
    sub = select_set(panel, which)
    rows: list[dict[str, Any]] = []
    for k in horizons:
        k = int(k)
        row: dict[str, Any] = {"horizon": k, "n": 0, "adequate": False}
        for name, col in (("meanReturn", f"fwd_{k}"), ("meanExcess", f"excess_{k}")):
            row[name] = None
            if not sub.empty and col in sub.columns:
                vals = pd.to_numeric(sub[col], errors="coerce").dropna()
                row[name] = float(vals.mean()) if len(vals) else None
        value_col = _value_col(basis, k)
        if not sub.empty and value_col in sub.columns:
            vals = pd.to_numeric(sub[value_col], errors="coerce").dropna()
            row["n"] = int(len(vals))
            row["adequate"] = bool(len(vals) >= int(min_sample))
            row["mean"] = float(vals.mean()) if len(vals) else None
            row["median"] = float(vals.median()) if len(vals) else None
            row["upRate"] = float((vals > 0).mean()) if len(vals) else None
            row["best"] = float(vals.max()) if len(vals) else None
            row["worst"] = float(vals.min()) if len(vals) else None
        else:
            row.update({"mean": None, "median": None, "upRate": None, "best": None, "worst": None})
        row["basis"] = basis
        row["which"] = which
        rows.append(row)
    return rows


def score_curve(
    panel: pd.DataFrame,
    *,
    horizon: int = DEFAULT_REFERENCE_HORIZON,
    buckets: int = DEFAULT_SCORE_BUCKETS,
    basis: str = BASIS_EXCESS,
    which: str = SET_GATED,
    min_sample: int = MIN_MEANINGFUL_SAMPLE,
) -> dict[str, Any]:
    """Excess return bucketed by ``composite_score`` + Spearman rank correlation.

    A **negative or flat** rank correlation means the score is not monotone —
    a higher score does *not* buy a better forward return, which would make the
    entry gate's direction (or the factor weights) the primary suspect.
    """
    out: dict[str, Any] = {
        "horizon": int(horizon),
        "basis": basis,
        "which": which,
        "n": 0,
        "spearman": None,
        "direction": "unknown",
        "topMinusBottom": None,
        "buckets": [],
        "adequate": False,
    }
    sub = select_set(panel, which)
    value_col = _value_col(basis, horizon)
    if sub is None or sub.empty or value_col not in sub.columns or "composite_score" not in sub.columns:
        return out

    df = pd.DataFrame(
        {
            "score": pd.to_numeric(sub["composite_score"], errors="coerce"),
            "value": pd.to_numeric(sub[value_col], errors="coerce"),
        }
    ).dropna()
    out["n"] = int(len(df))
    out["adequate"] = bool(len(df) >= int(min_sample))
    if len(df) < 2 or df["score"].nunique() < 2:
        return out

    out["spearman"] = _spearman(df["score"], df["value"])
    spearman = out["spearman"]
    if df["value"].nunique() < 2:
        # Zero variance on the value axis: the correlation is undefined, and a
        # flat forward-return profile is itself the answer.
        out["direction"] = "flat"
    elif spearman is None:
        out["direction"] = "unknown"
    elif spearman > SPEARMAN_FLAT:
        out["direction"] = "increasing"
    elif spearman < -SPEARMAN_FLAT:
        out["direction"] = "decreasing"
    else:
        out["direction"] = "flat"

    n_buckets = int(max(2, min(int(buckets), int(df["score"].nunique()))))
    try:
        cut = pd.qcut(df["score"], q=n_buckets, duplicates="drop")
    except (ValueError, IndexError):  # pragma: no cover - degenerate scores
        return out
    groups: list[dict[str, Any]] = []
    for interval, part in df.groupby(cut, observed=True):
        groups.append(
            {
                "lo": _num(getattr(interval, "left", None)),
                "hi": _num(getattr(interval, "right", None)),
                "n": int(len(part)),
                "mean": float(part["value"].mean()),
                "upRate": float((part["value"] > 0).mean()),
            }
        )
    groups.sort(key=lambda g: (g["lo"] if g["lo"] is not None else 0.0))
    out["buckets"] = groups
    out["topMinusBottom"] = float(groups[-1]["mean"] - groups[0]["mean"]) if len(groups) >= 2 else None
    return out


# --------------------------------------------------------------------------- #
# block 3/4 — cost drag + payoff profile
# --------------------------------------------------------------------------- #
def cost_drag(trades: Sequence[Mapping[str, Any]] | None) -> dict[str, Any]:
    """Gross vs net return on the **same** trades: how much the cost model eats.

    ``gross_ret`` / ``net_ret`` come from :func:`book_replay.replay_book` in
    **percentage points** and are normalised here to fractions
    (:data:`TRADE_RET_SCALE`).
    """
    rows = [
        t
        for t in (trades or [])
        if isinstance(t, Mapping)
        and _num(t.get("gross_ret")) is not None
        and _num(t.get("net_ret")) is not None
    ]
    out: dict[str, Any] = {
        "n": len(rows),
        "unit": "fraction",
        "meanGross": None,
        "meanNet": None,
        "meanCost": None,
        "costShare": None,
        "avgHoldDays": None,
        "grossPositive": None,
        "netPositive": None,
        "signFlipped": None,
    }
    if not rows:
        return out
    gross = [float(_num(t.get("gross_ret"))) * TRADE_RET_SCALE for t in rows]
    net = [float(_num(t.get("net_ret"))) * TRADE_RET_SCALE for t in rows]
    holds = [_num(t.get("held_days")) for t in rows]
    holds = [h for h in holds if h is not None]
    mean_gross = _mean(gross)
    mean_net = _mean(net)
    out["meanGross"] = mean_gross
    out["meanNet"] = mean_net
    out["meanCost"] = (mean_gross - mean_net) if (mean_gross is not None and mean_net is not None) else None
    if mean_gross not in (None, 0.0) and out["meanCost"] is not None:
        out["costShare"] = float(out["meanCost"] / abs(mean_gross))
    out["avgHoldDays"] = _mean(holds)
    out["grossPositive"] = bool(mean_gross is not None and mean_gross > 0)
    out["netPositive"] = bool(mean_net is not None and mean_net > 0)
    out["signFlipped"] = bool(out["grossPositive"] and not out["netPositive"])
    return out


def payoff_profile(trades: Sequence[Mapping[str, Any]] | None) -> dict[str, Any]:
    """Win rate / average win / average loss / payoff ratio / expectancy.

    ``net_ret`` is normalised from percentage points to fractions
    (:data:`TRADE_RET_SCALE`).
    """
    vals = [
        float(_num(t.get("net_ret"))) * TRADE_RET_SCALE
        for t in (trades or [])
        if _num(t.get("net_ret")) is not None
    ]
    out: dict[str, Any] = {
        "n": len(vals),
        "unit": "fraction",
        "winRate": None,
        "avgWin": None,
        "avgLoss": None,
        "payoffRatio": None,
        "expectancy": None,
        "best": None,
        "worst": None,
    }
    if not vals:
        return out
    wins = [v for v in vals if v > 0]
    losses = [v for v in vals if v <= 0]
    out["winRate"] = float(len(wins) / len(vals))
    out["avgWin"] = _mean(wins)
    out["avgLoss"] = _mean(losses)
    if out["avgWin"] is not None and out["avgLoss"] not in (None, 0.0):
        out["payoffRatio"] = float(out["avgWin"] / abs(out["avgLoss"]))
    out["expectancy"] = _mean(vals)
    out["best"] = max(vals)
    out["worst"] = min(vals)
    return out


# --------------------------------------------------------------------------- #
# block 5 — loss concentration
# --------------------------------------------------------------------------- #
def _group_of(trade: Mapping[str, Any], by: str, industry_map: Mapping[str, str] | None) -> str:
    if by == "month":
        return str(trade.get("exit_date") or "")[:7] or "—"
    if by == "reason":
        # ``book_replay`` reasons carry the realised level, e.g. ``stop_loss(-8.1%)``;
        # grouping on the raw string shatters one exit rule into dozens of buckets,
        # so bucket on the rule name (the text before the parenthesis).
        raw = str(trade.get("reason") or "—")
        return raw.split("(")[0].strip() or "—"
    if by == "assetClass":
        return str(trade.get("asset_class") or "—")
    if by == "industry":
        code = str(trade.get("code") or "")
        lookup = industry_map or {}
        return str(lookup.get(code) or lookup.get(norm_code(code)) or "—")
    raise ValueError(f"unknown concentration key {by!r}")


def concentration(
    trades: Sequence[Mapping[str, Any]] | None,
    *,
    by: str,
    industry_map: Mapping[str, str] | None = None,
    value_field: str = "net_ret",
    value_scale: float = TRADE_RET_SCALE,
) -> dict[str, Any]:
    """Group realised returns by ``by`` and measure how concentrated the loss is.

    ``lossShare`` is the share of all **negative** group totals a group carries —
    when one group carries ``>= LOSS_CONCENTRATION_WARN`` of the loss mass the
    loss is a *point problem*, not a systemic one.
    """
    buckets: dict[str, list[float]] = {}
    for t in trades or []:
        if not isinstance(t, Mapping):
            continue
        value = _num(t.get(value_field))
        if value is None:
            continue
        buckets.setdefault(_group_of(t, by, industry_map), []).append(float(value) * float(value_scale))

    groups: list[dict[str, Any]] = []
    for group, values in buckets.items():
        groups.append(
            {
                "group": group,
                "n": len(values),
                "mean": _mean(values),
                "median": _median(values),
                "total": float(sum(values)),
                "winRate": float(sum(1 for v in values if v > 0) / len(values)),
            }
        )
    groups.sort(key=lambda g: g["total"])

    neg_mass = {g["group"]: abs(g["total"]) for g in groups if g["total"] < 0}
    total_neg = sum(neg_mass.values())
    for g in groups:
        g["lossShare"] = (neg_mass.get(g["group"], 0.0) / total_neg) if total_neg > 0 else None

    max_share_group = None
    max_share = None
    if total_neg > 0:
        max_share_group = max(neg_mass, key=lambda k: neg_mass[k])
        max_share = neg_mass[max_share_group] / total_neg

    return {
        "by": by,
        "byZh": CONCENTRATION_ZH.get(by, by),
        "valueField": value_field,
        "valueScale": float(value_scale),
        "n": sum(g["n"] for g in groups),
        "groupCount": len(groups),
        "overallTotal": float(sum(g["total"] for g in groups)),
        "overallMean": _mean([v for vs in buckets.values() for v in vs]),
        "groups": groups,
        "worst": groups[0] if groups else None,
        "best": groups[-1] if groups else None,
        "maxLossShare": max_share,
        "maxLossGroup": max_share_group,
    }


# --------------------------------------------------------------------------- #
# pure diagnosis
# --------------------------------------------------------------------------- #
def _adequate(curve: Sequence[Mapping[str, Any]], key: str) -> list[Mapping[str, Any]]:
    """Adequately-sampled horizons carrying a usable ``key`` value, ascending."""
    rows = [r for r in (curve or []) if r.get("adequate") and r.get(key) is not None]
    return sorted(rows, key=lambda r: int(r.get("horizon") or 0))


def _cause(
    code: str,
    title: str,
    severity: str,
    impact: float | None,
    evidence: Mapping[str, Any],
    action: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "title": title,
        "severity": severity,
        "severityZh": SEVERITY_ZH.get(severity, severity),
        "rank": _CAUSE_RANK.get(code, 50),
        "impact": impact,
        "evidence": dict(evidence),
        "action": action,
    }


def diagnose(
    *,
    curve_picks: Sequence[Mapping[str, Any]] | None = None,
    curve_gated: Sequence[Mapping[str, Any]] | None = None,
    score: Mapping[str, Any] | None = None,
    cost: Mapping[str, Any] | None = None,
    payoff: Mapping[str, Any] | None = None,
    concentrations: Sequence[Mapping[str, Any]] | None = None,
    realized_hold_days: float | None = None,
    reference_horizon: int = DEFAULT_REFERENCE_HORIZON,
    min_sample: int = MIN_MEANINGFUL_SAMPLE,
) -> dict[str, Any]:
    """Pure cause ranking — no pandas, no engine, thresholds pre-registered.

    ``curve_picks`` is the sample set that matters (what the platform would
    actually buy); ``curve_gated`` is only consulted when ``picks`` is too thin
    to support a verdict. **Edge** rules read ``meanExcess``; **holding-period**
    rules read ``meanReturn`` (see the module docstring for why).
    """
    causes: list[dict[str, Any]] = []
    notes: list[str] = []

    rel = _adequate(curve_picks, "meanExcess")
    absolute = _adequate(curve_picks, "meanReturn")
    basis_set = SET_PICKS
    if not rel and not absolute:
        rel_g = _adequate(curve_gated, "meanExcess")
        abs_g = _adequate(curve_gated, "meanReturn")
        if rel_g or abs_g:
            rel, absolute, basis_set = rel_g, abs_g, SET_GATED
            notes.append("picks 样本不足，退用全部过闸标的（gated）出结论。")
    if not rel and not absolute:
        notes.append(
            "没有任何 horizon 达到样本门槛（%d），不做归因结论。" % int(min_sample)
        )

    # --- edge (超额口径) ---------------------------------------------------- #
    if rel:
        excess = [float(r["meanExcess"]) for r in rel]
        horizons = [int(r["horizon"]) for r in rel]
        if all(v <= 0 for v in excess):
            causes.append(
                _cause(
                    CAUSE_SIGNAL_NO_EDGE,
                    "信号无 edge：所有持有期都跑输基准",
                    SEVERITY_ALERT,
                    abs(min(excess)),
                    {"set": basis_set, "perHorizon": dict(zip(horizons, excess))},
                    "信号本身需重做：先查因子方向/权重，再考虑换因子（改动仍须过 Y1 闸门）。",
                )
            )
        else:
            ref_idx = min(range(len(horizons)), key=lambda i: abs(horizons[i] - int(reference_horizon)))
            ref_h, ref_v = horizons[ref_idx], excess[ref_idx]
            long_h, long_v = horizons[-1], excess[-1]
            if long_h > ref_h and ref_v <= 0 < long_v:
                causes.append(
                    _cause(
                        CAUSE_EDGE_ONLY_LONG_HORIZON,
                        f"实战窗口无超额：{ref_h} 日超额 {ref_v:+.2%}、仅 {long_h} 日转正 {long_v:+.2%}",
                        SEVERITY_WARN,
                        abs(long_v - ref_v),
                        {
                            "set": basis_set,
                            "referenceHorizon": ref_h,
                            "referenceMeanExcess": ref_v,
                            "longHorizon": long_h,
                            "longMeanExcess": long_v,
                        },
                        "长周期相对为正多为熊市防守，**不要**据此延长持有；先在实战窗口内做出正超额。",
                    )
                )

    # --- holding period (绝对口径) ------------------------------------------ #
    if absolute:
        rets = [float(r["meanReturn"]) for r in absolute]
        horizons = [int(r["horizon"]) for r in absolute]
        peak_idx = max(range(len(rets)), key=lambda i: rets[i])
        peak_h, peak_v = horizons[peak_idx], rets[peak_idx]
        long_h, long_v = horizons[-1], rets[-1]
        short_h, short_v = horizons[0], rets[0]
        hold_txt = f"，实际平均持有 {realized_hold_days:.1f} 天" if realized_hold_days else ""
        if all(v <= 0 for v in rets):
            causes.append(
                _cause(
                    CAUSE_NO_ABSOLUTE_EDGE,
                    "绝对收益全为负：任何持有期都亏",
                    SEVERITY_ALERT,
                    abs(max(rets)),
                    {"set": basis_set, "perHorizon": dict(zip(horizons, rets)), "realizedHoldDays": realized_hold_days},
                    "任何持有期都亏 ⇒ 先解决绝对收益（信号/择时），再谈持有期优化。",
                )
            )
        elif peak_v > 0 and long_v < 0 and peak_h < long_h:
            causes.append(
                _cause(
                    CAUSE_HOLD_TOO_LONG,
                    f"持有过久：绝对收益在 {peak_h} 日见顶（{peak_v:+.2%}）后转负"
                    f"（{long_h} 日 {long_v:+.2%}）{hold_txt}",
                    SEVERITY_WARN,
                    abs(long_v - peak_v),
                    {
                        "set": basis_set,
                        "peakHorizon": peak_h,
                        "peakMean": peak_v,
                        "longHorizon": long_h,
                        "longMean": long_v,
                        "realizedHoldDays": realized_hold_days,
                    },
                    "缩短持有窗 / 收紧止盈——把出场移向绝对收益峰值附近（可作 Y1 候选档）。",
                )
            )
        elif peak_v > 0 and short_v < 0 and peak_h == long_h:
            causes.append(
                _cause(
                    CAUSE_HOLD_TOO_SHORT,
                    f"持有过短：绝对收益要到 {peak_h} 日才转正（{peak_v:+.2%}）{hold_txt}",
                    SEVERITY_WARN,
                    abs(peak_v - short_v),
                    {
                        "set": basis_set,
                        "shortHorizon": short_h,
                        "shortMean": short_v,
                        "peakHorizon": peak_h,
                        "peakMean": peak_v,
                        "realizedHoldDays": realized_hold_days,
                    },
                    "延长持有窗（放宽最长持有）——收益尚未走到（可作 Y1 候选档）。",
                )
            )

    # --- score ------------------------------------------------------------- #
    if score and score.get("n"):
        spearman = _num(score.get("spearman"))
        top_minus_bottom = _num(score.get("topMinusBottom"))
        if spearman is not None and spearman <= -SPEARMAN_FLAT:
            causes.append(
                _cause(
                    CAUSE_SCORE_NOT_MONOTONIC,
                    f"评分反向：高分反而更差（Spearman={spearman:+.3f}）",
                    SEVERITY_ALERT,
                    abs(spearman),
                    {
                        "horizon": score.get("horizon"),
                        "spearman": spearman,
                        "topMinusBottom": top_minus_bottom,
                        "direction": score.get("direction"),
                    },
                    "复核闸门方向与因子权重（评分是否在筛掉好票），再验证是否应下调门槛。",
                )
            )
        elif spearman is not None and abs(spearman) <= SPEARMAN_FLAT:
            causes.append(
                _cause(
                    CAUSE_SCORE_WEAK,
                    f"评分区分度弱：Spearman={spearman:+.3f}（接近无关联）",
                    SEVERITY_WARN,
                    abs(spearman),
                    {
                        "horizon": score.get("horizon"),
                        "spearman": spearman,
                        "topMinusBottom": top_minus_bottom,
                        "n": score.get("n"),
                    },
                    "评分对前瞻收益解释力弱：优先补强因子，而非继续调闸门。",
                )
            )

    # --- cost -------------------------------------------------------------- #
    if cost and cost.get("meanGross") is not None and cost.get("meanNet") is not None:
        mean_gross = float(cost["meanGross"])
        mean_net = float(cost["meanNet"])
        cost_share = _num(cost.get("costShare"))
        if mean_gross > 0 and mean_net <= 0:
            causes.append(
                _cause(
                    CAUSE_COST_ERODES_EDGE,
                    "成本吃掉全部 edge：毛收益为正、净收益为负",
                    SEVERITY_ALERT,
                    abs(mean_net - mean_gross),
                    {
                        "meanGross": mean_gross,
                        "meanNet": mean_net,
                        "meanCost": cost.get("meanCost"),
                        "avgHoldDays": cost.get("avgHoldDays"),
                        "n": cost.get("n"),
                    },
                    "降换手：抬高评分闸门 / 减少交易笔数，或拉长持有（成本按笔摊薄）。",
                )
            )
        elif mean_gross > 0 and cost_share is not None and cost_share >= COST_SHARE_WARN:
            causes.append(
                _cause(
                    CAUSE_COST_ERODES_EDGE,
                    f"成本拖累显著：吃掉毛收益的 {cost_share:.0%}",
                    SEVERITY_WARN,
                    cost_share,
                    {
                        "meanGross": mean_gross,
                        "meanNet": mean_net,
                        "costShare": cost_share,
                        "avgHoldDays": cost.get("avgHoldDays"),
                    },
                    "评估降低换手（合并信号 / 提高闸门）是否把净收益抬回正区。",
                )
            )

    # --- payoff ------------------------------------------------------------ #
    if payoff and payoff.get("winRate") is not None and payoff.get("payoffRatio") is not None:
        win_rate = float(payoff["winRate"])
        ratio = float(payoff["payoffRatio"])
        if win_rate < WINRATE_WARN and ratio < PAYOFF_RATIO_WARN:
            causes.append(
                _cause(
                    CAUSE_PAYOFF_UNFAVORABLE,
                    f"赔率结构不利：胜率 {win_rate:.0%} 且盈亏比 {ratio:.2f}",
                    SEVERITY_WARN,
                    abs(1.0 - ratio),
                    {
                        "winRate": win_rate,
                        "avgWin": payoff.get("avgWin"),
                        "avgLoss": payoff.get("avgLoss"),
                        "payoffRatio": ratio,
                        "expectancy": payoff.get("expectancy"),
                    },
                    "小赢大亏：收紧止损（截断长尾亏损）或让盈利单多跑。",
                )
            )

    # --- concentration ----------------------------------------------------- #
    for block in concentrations or []:
        share = _num(block.get("maxLossShare"))
        overall_mean = _num(block.get("overallMean"))
        groups = block.get("groups") or []
        # A single group carries 100% of everything by construction — that is not
        # a concentration finding (真机教训: ``assetClass=stock`` 恒 100%）。
        if len(groups) < 2 or int(block.get("n") or 0) < int(min_sample):
            continue
        if share is not None and share >= LOSS_CONCENTRATION_WARN and (overall_mean is None or overall_mean < 0):
            causes.append(
                _cause(
                    CAUSE_CONCENTRATED_LOSS,
                    f"亏损集中于「{block.get('maxLossGroup')}」（{block.get('byZh')}，占亏损 {share:.0%}）",
                    SEVERITY_WARN,
                    share,
                    {
                        "by": block.get("by"),
                        "group": block.get("maxLossGroup"),
                        "lossShare": share,
                        "overallMean": overall_mean,
                        "groupCount": len(groups),
                    },
                    f"定点排查该{block.get('byZh')}的暴露/事件，必要时加暴露上限（可作 Y1 候选档）。",
                )
            )

    if not causes:
        causes.append(
            _cause(
                CAUSE_NO_SINGLE_CAUSE,
                "未发现单点主因：损失近似均匀分布",
                SEVERITY_INFO,
                None,
                {"set": basis_set},
                "非单点问题：按「信号边缘弱 + 成本/赔率」组合改善，逐项过 Y1 闸门验证。",
            )
        )

    causes.sort(
        key=lambda c: (
            _SEVERITY_WEIGHT.get(str(c["severity"]), 0),
            -int(c.get("rank") or 50),
            abs(float(c["impact"] or 0.0)),
        ),
        reverse=True,
    )
    severity_counts = {
        sev: sum(1 for c in causes if c["severity"] == sev)
        for sev in (SEVERITY_ALERT, SEVERITY_WARN, SEVERITY_INFO)
    }
    top = causes[0]
    headline = str(top["title"]) + (f"（另有 {len(causes) - 1} 项）" if len(causes) > 1 else "")

    return {
        "verdict": (
            CAUSE_NO_SINGLE_CAUSE
            if severity_counts[SEVERITY_ALERT] == 0 and severity_counts[SEVERITY_WARN] == 0
            else "attributed"
        ),
        "headline": headline,
        "basisSet": basis_set,
        "causes": causes,
        "severityCounts": severity_counts,
        "notes": notes,
        "thresholds": {
            "costShareWarn": COST_SHARE_WARN,
            "lossConcentrationWarn": LOSS_CONCENTRATION_WARN,
            "spearmanFlat": SPEARMAN_FLAT,
            "payoffRatioWarn": PAYOFF_RATIO_WARN,
            "winRateWarn": WINRATE_WARN,
            "minSample": int(min_sample),
            "referenceHorizon": int(reference_horizon),
        },
    }


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def _fmt_pct(value: Any, *, digits: int = 2) -> str:
    num = _num(value)
    return "—" if num is None else f"{num * 100:.{digits}f}%"


def _fmt_signed_pct(value: Any, *, digits: int = 2) -> str:
    num = _num(value)
    return "—" if num is None else f"{num * 100:+.{digits}f}%"


def _fmt_num(value: Any, *, digits: int = 3) -> str:
    num = _num(value)
    return "—" if num is None else f"{num:.{digits}f}"


def _curve_table(curve: Sequence[Mapping[str, Any]], title: str) -> list[str]:
    lines = [
        f"**{title}**",
        "",
        "| 持有(交易日) | 样本 | 平均超额 | 平均收益 | 中位超额 | 跑赢率 | 样本足 |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in curve or []:
        lines.append(
            f"| {row.get('horizon')} | {row.get('n')} | {_fmt_signed_pct(row.get('meanExcess'))} | "
            f"{_fmt_signed_pct(row.get('meanReturn'))} | {_fmt_signed_pct(row.get('median'))} | "
            f"{_fmt_pct(row.get('upRate'), digits=1)} | {'✅' if row.get('adequate') else '❌'} |"
        )
    lines.append("")
    return lines


def render_attribution_markdown(payload: Mapping[str, Any]) -> str:
    """Markdown report for the attribution diagnosis (``JSON`` is the contract)."""
    if not payload.get("ok"):
        return f"# 收益归因诊断\n\n无可用数据：{payload.get('reason')}\n"

    diag = payload.get("diagnosis") or {}
    lines: list[str] = ["# 收益归因 / 负收益根因诊断", ""]
    if payload.get("generatedAt"):
        lines.append(f"- 生成时间：{payload['generatedAt']}")
    lines += [
        f"- 窗口：`{payload.get('start')}` ~ `{payload.get('end')}`（共 {payload.get('nDays')} 个交易日）",
        f"- 基准：`{payload.get('benchmarkSymbol') or '—'}`"
        f"（{'可用' if payload.get('benchmarkAvailable') else '不可用 → 退用裸收益'}）",
        f"- 评分闸门：`composite_score >= {payload.get('scoreFloor')}`"
        f" · 过闸 {payload.get('nGated')} 行 / 候选池 {payload.get('nPicks')} 行",
        f"- 环境：{payload.get('environment')} · liveTradingEnabled={payload.get('liveTradingEnabled')}",
        "",
        f"> **根因裁决：{diag.get('headline')}**",
        "",
    ]

    lines += ["## 一、信号有效性曲线", ""]
    lines += _curve_table(payload.get("curvePicks") or [], SET_ZH[SET_PICKS])
    lines += _curve_table(payload.get("curveGated") or [], SET_ZH[SET_GATED])
    lines += [
        "> **口径**：「平均超额」= 相对基准（衡量信号技能）；「平均收益」= 绝对（衡量拿在手里赚不赚）。",
        "> 超额全负 ⇒ 信号无技能；绝对收益见顶转负 ⇒ 持有过久；绝对收益仅在最长周期为正 ⇒ 持有过短。",
        "> **注意**：超额在长周期为正而绝对收益为负，多为熊市相对防守，**不是**延长持有的理由。",
        "",
    ]

    score = payload.get("score")
    lines += ["## 二、评分单调性", ""]
    if score:
        lines += [
            f"- 参照持有期：{score.get('horizon')} 交易日 · 样本 {score.get('n')}"
            f"（{'达标' if score.get('adequate') else '未达标'}）",
            f"- Spearman：**{_fmt_num(score.get('spearman'))}**（方向：{score.get('direction')}）"
            f" · 最高分位 − 最低分位：{_fmt_signed_pct(score.get('topMinusBottom'))}",
            "",
            "| 分数区间 | 样本 | 平均超额 | 跑赢率 |",
            "|---|---|---|---|",
        ]
        for bucket in score.get("buckets") or []:
            lines.append(
                f"| [{_fmt_num(bucket.get('lo'), digits=2)}, {_fmt_num(bucket.get('hi'), digits=2)}] | "
                f"{bucket.get('n')} | {_fmt_signed_pct(bucket.get('mean'))} | "
                f"{_fmt_pct(bucket.get('upRate'), digits=1)} |"
            )
    else:
        lines.append("（无评分数据）")
    lines.append("")

    cost = payload.get("cost") or {}
    lines += [
        "## 三、成本拖累（毛 vs 净，同一批成交）",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 成交笔数 | {cost.get('n')} |",
        f"| 平均毛收益 | {_fmt_signed_pct(cost.get('meanGross'))} |",
        f"| 平均净收益 | {_fmt_signed_pct(cost.get('meanNet'))} |",
        f"| 平均成本 | {_fmt_signed_pct(cost.get('meanCost'))} |",
        f"| 成本占毛收益 | {_fmt_pct(cost.get('costShare'), digits=1)} |",
        f"| 平均持有（天） | {_fmt_num(cost.get('avgHoldDays'), digits=1)} |",
        f"| 符号翻转（毛正净负） | {'是' if cost.get('signFlipped') else '否'} |",
        "",
    ]

    payoff = payload.get("payoff") or {}
    lines += [
        "## 四、赔率结构",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 胜率 | {_fmt_pct(payoff.get('winRate'), digits=1)} |",
        f"| 平均盈利 | {_fmt_signed_pct(payoff.get('avgWin'))} |",
        f"| 平均亏损 | {_fmt_signed_pct(payoff.get('avgLoss'))} |",
        f"| 盈亏比 | {_fmt_num(payoff.get('payoffRatio'))} |",
        f"| 期望值 | {_fmt_signed_pct(payoff.get('expectancy'))} |",
        f"| 最佳 / 最差 | {_fmt_signed_pct(payoff.get('best'))} / {_fmt_signed_pct(payoff.get('worst'))} |",
        "",
    ]

    lines += ["## 五、亏损集中度", ""]
    for block in payload.get("concentrations") or []:
        lines += [f"**按{block.get('byZh')}**（合计 {_fmt_signed_pct(block.get('overallTotal'))}）", ""]
        lines += ["| 分组 | 笔数 | 平均 | 合计 | 占亏损 |", "|---|---|---|---|---|"]
        for group in (block.get("groups") or [])[:6]:
            lines.append(
                f"| {group.get('group')} | {group.get('n')} | {_fmt_signed_pct(group.get('mean'))} | "
                f"{_fmt_signed_pct(group.get('total'))} | {_fmt_pct(group.get('lossShare'), digits=1)} |"
            )
        lines.append("")

    lines += ["## 六、根因裁决", ""]
    for idx, cause in enumerate(diag.get("causes") or [], start=1):
        lines += [
            f"### {idx}. {cause.get('title')}　`{cause.get('severityZh')}`",
            "",
            f"- 原因码：`{cause.get('code')}`",
            f"- 证据：`{cause.get('evidence')}`",
            f"- 建议动作：{cause.get('action')}",
            "",
        ]
    if diag.get("notes"):
        lines += ["备注："] + [f"- {n}" for n in diag["notes"]] + [""]
    lines += [
        "> 本报告只出**归因**：不修改任何生产默认档、不写 brief / picks。"
        "候选方向仍须过 `Y1` 采纳闸门 + 人工签核。",
        "",
        f"> {payload.get('disclaimer', '')}",
        "",
    ]
    return "\n".join(lines)


__all__ = [
    "BASIS_EXCESS",
    "BASIS_RAW",
    "CAUSE_CONCENTRATED_LOSS",
    "CAUSE_COST_ERODES_EDGE",
    "CAUSE_EDGE_ONLY_LONG_HORIZON",
    "CAUSE_HOLD_TOO_LONG",
    "CAUSE_HOLD_TOO_SHORT",
    "CAUSE_NO_ABSOLUTE_EDGE",
    "CAUSE_NO_SINGLE_CAUSE",
    "CAUSE_PAYOFF_UNFAVORABLE",
    "CAUSE_SCORE_NOT_MONOTONIC",
    "CAUSE_SCORE_WEAK",
    "CAUSE_SIGNAL_NO_EDGE",
    "CONCENTRATION_KEYS",
    "CONCENTRATION_ZH",
    "COST_SHARE_WARN",
    "DEFAULT_ATTRIBUTION_OUT_DIR",
    "DEFAULT_HORIZONS",
    "DEFAULT_REFERENCE_HORIZON",
    "DEFAULT_SCORE_BUCKETS",
    "DEFAULT_SCORE_FLOOR",
    "LOSS_CONCENTRATION_WARN",
    "MIN_MEANINGFUL_SAMPLE",
    "PAYOFF_RATIO_WARN",
    "SEVERITY_ALERT",
    "SEVERITY_INFO",
    "SEVERITY_WARN",
    "SEVERITY_ZH",
    "SET_GATED",
    "SET_PICKS",
    "SET_ZH",
    "SPEARMAN_FLAT",
    "TRADE_RET_SCALE",
    "WINRATE_WARN",
    "attach_forward_returns",
    "build_signal_panel",
    "concentration",
    "cost_drag",
    "diagnose",
    "horizon_curve",
    "payoff_profile",
    "prepare_benchmark",
    "render_attribution_markdown",
    "score_curve",
    "select_set",
]
