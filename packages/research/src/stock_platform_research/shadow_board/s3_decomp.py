"""Read-only alpha / beta decomposition of the S3 quality school.

Plan: ``docs/plans/shadow-s3-decomposition.md`` (pre-registered, judgement fixed).

* Y_t: equal-weight ``close[t+1] / close[t] - 1`` over the S3 Round1 pool
  (``school_s3_quality``, ``top_k=8``; no Round2, no seats, no exit rules).
* X_t: CSI 300 / CSI 500 / CSI 1000 next-session price returns, read **only**
  through :func:`stock_platform_research.benchmark.load_benchmark_closes`
  (market.db identity check, then the verified aux store, ADR 0095).
* OLS with Newey-West (Bartlett kernel, ``L = floor(4 * (T/100) ** (2/9))``).
  The judgement uses model M3 only; M1 / M2 are descriptive.

SIMULATE / research only. ``market.db`` is read-only. Does not change any school,
arbitration, sizing, exit or default. Pure functions + a ``main`` that writes
under ``local/shadow/diagnostics/s3_decomp/``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from ..portfolio import norm_code
from .diagnostics import add_forward_returns
from .schools import school_s3_quality

TRADING_DAYS = 252
TOP_K = 8
#: Benchmark key → index symbol (bare code). ``r300`` / ``r500`` / ``r1000``.
BENCH_SYMBOLS: dict[str, str] = {"r300": "000300", "r500": "000905", "r1000": "000852"}
#: Judgement threshold on the full-sample NW t of alpha (pre-registered).
ALPHA_T_MIN = 1.5
DEFAULT_OUT_DIR = Path("local/shadow/diagnostics/s3_decomp")

SEG_A = ("段A 2021-23", "2021-01-04", "2023-12-31")
SEG_B = ("段B 2024-26", "2024-01-01", "2026-11-05")
SEG_FULL = ("全区间", "2021-01-04", "2026-11-05")
YEAR_BOUNDS: tuple[tuple[str, str, str], ...] = tuple(
    (str(y), f"{y}-01-01", f"{y}-12-31") for y in range(2021, 2027)
)

#: name → regressors (intercept always included). M3 is the judgement model.
MODELS: dict[str, tuple[str, ...]] = {
    "M3": ("r300", "r500", "r1000"),
    "M1": ("r500",),
    "M2": ("r300", "spread"),
}


def nw_lag(T: int) -> int:
    """Newey-West lag ``floor(4 * (T / 100) ** (2 / 9))`` (pre-registered)."""
    return int(math.floor(4.0 * (T / 100.0) ** (2.0 / 9.0)))


def ols_nw(
    y: Sequence[float] | np.ndarray,
    X: np.ndarray,
    names: Sequence[str],
    lag: int | None = None,
) -> dict[str, Any] | None:
    """OLS coefficients with Newey-West (Bartlett) standard errors.

    ``X`` must already contain the intercept column. Returns ``None`` when the
    design matrix is singular or there are too few rows.
    """
    yv = np.asarray(y, dtype="float64")
    Xv = np.asarray(X, dtype="float64")
    T, k = Xv.shape
    if T <= k + 2:
        return None
    try:
        xtx_inv = np.linalg.inv(Xv.T @ Xv)
    except np.linalg.LinAlgError:
        return None
    b = xtx_inv @ Xv.T @ yv
    u = yv - Xv @ b
    L = nw_lag(T) if lag is None else int(lag)
    Xu = Xv * u[:, None]
    S = Xu.T @ Xu
    for l in range(1, min(L, T - 1) + 1):
        w = 1.0 - l / (L + 1.0)
        G = Xu[l:].T @ Xu[:-l]
        S = S + w * (G + G.T)
    V = xtx_inv @ S @ xtx_inv
    se = np.sqrt(np.clip(np.diag(V), 0.0, None))
    ss_tot = float(((yv - yv.mean()) ** 2).sum())
    r2 = 1.0 - float(u @ u) / ss_tot if ss_tot > 0 else float("nan")
    with np.errstate(divide="ignore", invalid="ignore"):
        t = b / se
    return {
        "n": int(T),
        "lag": int(L),
        "coef": {n: float(v) for n, v in zip(names, b)},
        "nwT": {n: float(v) for n, v in zip(names, t)},
        "r2": r2,
    }


def s3_daily_pool(
    fwd: pd.DataFrame,
    *,
    name_map: Mapping[str, str] | None,
    top_k: int = TOP_K,
    pool_fn: Callable[..., Mapping[str, Any]] = school_s3_quality,
) -> pd.DataFrame:
    """Daily equal-weight next-session return of the S3 Round1 pool.

    ``fwd`` comes from :func:`diagnostics.add_forward_returns` (needs ``fwd_1``).
    Members without a next-session close are excluded from the mean; a day whose
    pool has no valid member is dropped entirely. ``pool_fn`` is injectable for
    tests only (default = the production S3 school).
    """
    from .backtest import frame_to_universe

    rows: list[dict[str, Any]] = []
    for day, frame in fwd.groupby("trade_date", sort=True):
        universe = frame_to_universe(frame, name_map=name_map)
        if not universe:
            continue
        pool = pool_fn(universe, top_k=top_k)
        members = [str(c["code"]) for c in pool.get("candidates") or []]
        fmap = {norm_code(str(c)): float(v) for c, v in zip(frame["code"], frame["fwd_1"])}
        vals = [fmap[c] for c in members if c in fmap and math.isfinite(fmap[c])]
        if not vals:
            continue
        rows.append(
            {
                "date": pd.Timestamp(day).date().isoformat(),
                "y": float(np.mean(vals)),
                "n": len(vals),
            }
        )
    return pd.DataFrame(rows, columns=["date", "y", "n"])


def index_next_returns(
    closes: Mapping[str, Mapping[str, float]], calendar: Sequence[str]
) -> pd.DataFrame:
    """``r_t = close[t+1] / close[t] - 1`` on the session calendar (ISO dates).

    A missing close on either side yields NaN for that day (dropped by the regression).
    """
    rows: list[dict[str, Any]] = []
    for i in range(len(calendar) - 1):
        t, t1 = calendar[i], calendar[i + 1]
        rec: dict[str, Any] = {"date": t}
        for key, cl in closes.items():
            a, b = cl.get(t), cl.get(t1)
            rec[key] = (float(b) / float(a) - 1.0) if a and b else float("nan")
        rows.append(rec)
    return pd.DataFrame(rows)


def _seg(reg: pd.DataFrame, lo: str, hi: str) -> pd.DataFrame:
    return reg[(reg["date"] >= lo) & (reg["date"] <= hi)]


def _block(df: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {"n": int(len(df)), "models": {}, "corr": {}}
    if df.empty:
        return out
    out["yMeanAnn"] = float(df["y"].mean()) * TRADING_DAYS
    out["idxMeanAnn"] = {k: float(df[k].mean()) * TRADING_DAYS for k in BENCH_SYMBOLS}
    for name, cols in MODELS.items():
        d = df.dropna(subset=["y", *cols])
        X = np.column_stack([np.ones(len(d)), d[list(cols)].to_numpy(dtype="float64")])
        res = ols_nw(d["y"].to_numpy(dtype="float64"), X, ["alpha", *cols])
        if res is None:
            out["models"][name] = None
            continue
        out["models"][name] = {
            "n": res["n"],
            "lag": res["lag"],
            "r2": res["r2"],
            "alphaDaily": res["coef"]["alpha"],
            "alphaAnn": res["coef"]["alpha"] * TRADING_DAYS,
            "alphaT": res["nwT"]["alpha"],
            "beta": {c: res["coef"][c] for c in cols},
            "betaT": {c: res["nwT"][c] for c in cols},
        }
    c = df[list(BENCH_SYMBOLS)].dropna()
    if len(c) > 2:
        cm = c.corr()
        out["corr"] = {f"{a}~{b}": float(cm.loc[a, b]) for a, b in (("r300", "r500"), ("r500", "r1000"), ("r300", "r1000"))}
    return out


def _alpha_ann(block: Mapping[str, Any] | None) -> float | None:
    m = ((block or {}).get("models") or {}).get("M3")
    return None if not m else m["alphaAnn"]


def _alpha_t(block: Mapping[str, Any] | None) -> float | None:
    m = ((block or {}).get("models") or {}).get("M3")
    return None if not m else m["alphaT"]


def verdict(segments: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Pre-registered rule (M3 only): A α>0, B α>0, full NW t(α) > 1.5."""
    a = _alpha_ann(segments.get("A"))
    b = _alpha_ann(segments.get("B"))
    t = _alpha_t(segments.get("full"))
    checks = {
        "segA_alpha_ann_gt_0": a is not None and a > 0,
        "segB_alpha_ann_gt_0": b is not None and b > 0,
        "full_alpha_nw_t_gt_1_5": t is not None and t > ALPHA_T_MIN,
    }
    passed = all(checks.values())
    return {
        "passed": bool(passed),
        "checks": checks,
        "label": "在本口径下有选股 alpha" if passed else "未证明选股 alpha",
    }


def summarize(reg: pd.DataFrame) -> dict[str, Any]:
    """``reg``: columns ``date`` (ISO), ``y``, ``r300``, ``r500``, ``r1000``."""
    reg = reg.copy()
    reg["spread"] = reg["r1000"] - reg["r300"]
    segments = {
        "A": _block(_seg(reg, SEG_A[1], SEG_A[2])),
        "B": _block(_seg(reg, SEG_B[1], SEG_B[2])),
        "full": _block(_seg(reg, SEG_FULL[1], SEG_FULL[2])),
    }
    years = {y: _block(_seg(reg, lo, hi)) for y, lo, hi in YEAR_BOUNDS}
    return {
        "segments": segments,
        "years": years,
        "verdict": verdict(segments),
    }


def load_index_closes(
    db: str, start: str, end: str, names: Mapping[str, str] | None
) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    """Index closes through the single benchmark point. Fail-closed if any is empty."""
    from ..benchmark import load_benchmark_closes

    closes: dict[str, dict[str, float]] = {}
    blocks: dict[str, Any] = {}
    for key, sym in BENCH_SYMBOLS.items():
        series, block = load_benchmark_closes(db, start, end, names=dict(names or {}), symbol=sym)
        blocks[key] = block
        if not series:
            raise ValueError(f"基准 {sym} 不可用：{block.get('reason') or block.get('marketDbReason')}")
        closes[key] = series
    return closes, blocks


def _fmt_pct(v: Any, d: int = 2) -> str:
    return "—" if v is None or (isinstance(v, float) and not math.isfinite(v)) else f"{float(v) * 100:+.{d}f}%"


def _fmt_num(v: Any, d: int = 2) -> str:
    return "—" if v is None or (isinstance(v, float) and not math.isfinite(v)) else f"{float(v):.{d}f}"


def _row(label: str, blk: Mapping[str, Any]) -> str:
    m = (blk.get("models") or {}).get("M3") or {}
    beta = m.get("beta") or {}
    bt = m.get("betaT") or {}
    return (
        f"| {label} | {blk.get('n', 0)} | {_fmt_pct(m.get('alphaAnn'))} | {_fmt_num(m.get('alphaT'))} | "
        f"{_fmt_num(beta.get('r300'))} ({_fmt_num(bt.get('r300'))}) | "
        f"{_fmt_num(beta.get('r500'))} ({_fmt_num(bt.get('r500'))}) | "
        f"{_fmt_num(beta.get('r1000'))} ({_fmt_num(bt.get('r1000'))}) | "
        f"{_fmt_num(m.get('r2'), 3)} | {_fmt_pct(blk.get('yMeanAnn'))} | "
        f"{_fmt_pct((blk.get('idxMeanAnn') or {}).get('r500'))} |"
    )


def render_markdown(summary: Mapping[str, Any], meta: Mapping[str, Any] | None = None) -> str:
    v = summary["verdict"]
    lines = [
        "# S3 alpha / beta 拆解（M3 为判定模型）",
        "",
        "> 只读研究，SIMULATE；不改任何默认。口径见 `docs/plans/shadow-s3-decomposition.md`。",
        "",
        f"判定：**{v['label']}**（段A α>0：{v['checks']['segA_alpha_ann_gt_0']}；"
        f"段B α>0：{v['checks']['segB_alpha_ann_gt_0']}；全区间 NW t>1.5：{v['checks']['full_alpha_nw_t_gt_1_5']}）",
        "",
        "| 段 | N | α 年化 | α NW t | β 沪深300 (t) | β 中证500 (t) | β 中证1000 (t) | R² | Y 年化均值 | 中证500 年化均值 |",
        "|----|---|--------|--------|---------------|---------------|----------------|----|------------|------------------|",
        _row(SEG_A[0], summary["segments"]["A"]),
        _row(SEG_B[0], summary["segments"]["B"]),
        _row(SEG_FULL[0], summary["segments"]["full"]),
        "",
        "## 分年（M3，描述）",
        "",
        "| 年 | N | α 年化 | α NW t | β 沪深300 (t) | β 中证500 (t) | β 中证1000 (t) | R² | Y 年化均值 | 中证500 年化均值 |",
        "|----|---|--------|--------|---------------|---------------|----------------|----|------------|------------------|",
    ]
    for y, _, _ in YEAR_BOUNDS:
        lines.append(_row(y, summary["years"][y]))
    lines += ["", "## 稳健性（全区间，描述）", ""]
    full = summary["segments"]["full"]
    for name in ("M1", "M2"):
        m = (full.get("models") or {}).get(name) or {}
        lines.append(
            f"- {name}：α 年化 {_fmt_pct(m.get('alphaAnn'))}，NW t {_fmt_num(m.get('alphaT'))}，"
            f"R² {_fmt_num(m.get('r2'), 3)}，β {json.dumps({k: round(x, 3) for k, x in (m.get('beta') or {}).items()}, ensure_ascii=False)}"
        )
    lines += ["", "## 共线性（全区间 相关系数）", ""]
    lines += [f"- {k}：{_fmt_num(x, 3)}" for k, x in (full.get("corr") or {}).items()]
    if meta:
        lines += ["", "## 元信息", ""]
        lines += [f"- {k}：{v}" for k, v in meta.items()]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    from ..backtest_cli import ENV_DB, filter_universe, load_engine_bars, load_engine_industry, load_engine_names
    from .backtest import prepare_shadow_frame
    from datetime import date, timedelta

    ap = argparse.ArgumentParser(description="影子 S3 学派 alpha/beta 拆解（只读 market.db + 补充库指数）")
    ap.add_argument("--db", default=None)
    ap.add_argument("--start", default="2021-01-04")
    ap.add_argument("--end", default="2026-11-05")
    ap.add_argument("--top-k", type=int, default=TOP_K)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args(argv)

    db = (args.db or os.environ.get(ENV_DB, "")).strip()
    if not db or not Path(db).is_file():
        print(f"[fail] market.db 不可用：{db or '未设置 ' + ENV_DB}", file=sys.stderr)
        return 2
    load_start = (date.fromisoformat(args.start) - timedelta(days=180)).isoformat()
    bars = filter_universe(load_engine_bars(db, start=load_start, end=args.end, with_amount=True))
    if bars.empty:
        print("[fail] 区间内无行情", file=sys.stderr)
        return 2
    try:
        industry = load_engine_industry(db)
    except KeyError:
        industry = None
    names = load_engine_names(db)
    feats = prepare_shadow_frame(bars, start=args.start, end=args.end, industry_map=industry)
    fwd = add_forward_returns(feats)
    calendar = sorted(pd.Timestamp(x).date().isoformat() for x in feats["trade_date"].unique())
    daily = s3_daily_pool(fwd, name_map=names, top_k=args.top_k)
    closes, bench_blocks = load_index_closes(db, args.start, args.end, names)
    idx = index_next_returns(closes, calendar)
    reg = daily.merge(idx, on="date", how="inner").dropna(subset=["y", *BENCH_SYMBOLS])
    summary = summarize(reg)
    meta = {
        "区间": f"{args.start} ~ {args.end}",
        "S3 池": f"school_s3_quality, top_k={args.top_k}",
        "日样本数（Y 与三指数齐全）": len(reg),
        "池日数（含缺次日收盘的剔除）": len(daily),
        "指数来源": json.dumps(
            {k: {"source": b.get("source") or "market.db", "symbol": b.get("symbol")} for k, b in bench_blocks.items()},
            ensure_ascii=False,
        ),
    }
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "s3_decomp.json").write_text(
        json.dumps({"summary": summary, "meta": meta, "benchmarks": bench_blocks}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    md = render_markdown(summary, meta)
    (out / "s3_decomp.md").write_text(md, encoding="utf-8")
    reg.to_csv(out / "s3_daily.csv.gz", index=False, compression="gzip")
    print(md)
    print(f"[write] {out}", file=sys.stderr)
    return 0


__all__ = [
    "ALPHA_T_MIN",
    "BENCH_SYMBOLS",
    "index_next_returns",
    "load_index_closes",
    "nw_lag",
    "ols_nw",
    "render_markdown",
    "s3_daily_pool",
    "summarize",
    "verdict",
]


if __name__ == "__main__":
    raise SystemExit(main())
