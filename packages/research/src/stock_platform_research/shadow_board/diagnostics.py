"""Read-only diagnostics: why do shadow schools S4 / S5 pick badly?

Independent of Round2 arbitration and of the book-replay slot logic: for every
session the **Round1 pool** of S3 / S4 / S5 is rebuilt with the very school
functions the daily hook calls (``schools.school_s*``) over the same
``frame_to_universe`` cross-section the walk-forward backtest uses, and each
pool member is scored against its **forward** close-to-close returns.

Controls (diagnostic pseudo-pools, never shipped as schools):

* ``S4inv``  — bottom ``top_k`` of the full S4 ``short`` composite (S4 reversed).
* ``S5amt``  — top ``top_k`` by raw ``amount`` (what S5 would pick without the
  ``min(amount/1e9, 0.8)`` score saturation and its code-order tie-break).
* ``RANDOM`` — ``top_k`` names drawn uniformly (fixed seed) from the eligible set.

Benchmark: ``market.db`` has no CSI 500 / CSI 300 index rows (``000905.SZ`` is a
stock), so excess return is measured against the **equal-weight mean of the
eligible universe** (liquid, named, non-ST) on the same day.

Entry convention mirrors the engine (buy at the signal day's close; no
open/high/low in ``daily_price``). ``fwdd_*`` is the one-session-delayed variant
(buy at T+1 close). ``simulate_exits`` replays the engine's exit rule
(:func:`rules.evaluate_exit`, default :class:`rules.ExitPolicy`) per candidate,
ignoring slot competition.

SIMULATE / research only. Pure functions + a ``main`` that only *reads*
``market.db`` and writes under ``local/shadow/diagnostics/``.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from ..portfolio import CostModel, norm_code
from ..rules import ExitPolicy, advance_peak, evaluate_exit, is_limit_down, is_limit_up
from ..secondary_pick import AMOUNT_MIN, select_secondary
from .backtest import frame_to_universe
from .schools import s1_regime_state, school_s3_quality, school_s4_short, school_s5_flow

HORIZONS: tuple[int, ...] = (1, 3, 5, 10, 20)
IC_HORIZONS: tuple[int, ...] = (1, 5, 10)
POOL_K = 8
RANDOM_SEED = 20261106
POOLS: tuple[str, ...] = ("S3", "S4", "S5", "S4inv", "S5amt", "RANDOM")
#: S5 thin-rule score saturates at this amount (``min(amount / 1e9, 0.8)``).
S5_SATURATION_AMOUNT = 8e8
DEFAULT_OUT_DIR = Path("local/shadow/diagnostics")

_RUNNERS = {"S3": school_s3_quality, "S4": school_s4_short, "S5": school_s5_flow}


def _is_st(name: Any) -> bool:
    return "ST" in str(name or "").upper()


def add_forward_returns(feats: pd.DataFrame, horizons: Sequence[int] = HORIZONS) -> pd.DataFrame:
    """Sorted copy of ``feats`` + forward returns and limit-up flags (per-code sessions).

    ``fwd_h``  = close[t+h] / close[t] − 1 (engine entry at signal-day close).
    ``fwdd_h`` = close[t+1+h] / close[t+1] − 1 (entry delayed one session).
    ``_lu`` signal-day sealed limit-up (main ±10 % / 30·68 ±20 %, ST ignored),
    ``_lu5`` any seal in the last 5 sessions incl. today, ``_lu_next`` seal at T+1.
    These columns are **outcomes**; ``frame_to_universe`` never forwards them to a
    school, so the pools stay PIT.
    """
    df = feats.sort_values(["code", "trade_date"]).reset_index(drop=True).copy()
    g = df.groupby("code", sort=False)["close"]
    close = df["close"].astype("float64")
    nxt = g.shift(-1).astype("float64")
    for h in horizons:
        df[f"fwd_{h}"] = g.shift(-h).astype("float64") / close - 1.0
        df[f"fwdd_{h}"] = g.shift(-(h + 1)).astype("float64") / nxt - 1.0
    code6 = df["code"].astype(str).str.replace(".", "", regex=False).str[:6]
    lim = np.where(code6.str.startswith(("30", "68")), 20.0, 10.0)
    pct = pd.to_numeric(df.get("pct_chg"), errors="coerce").astype("float64")
    df["_lu"] = (pct >= lim - 0.01).fillna(False).astype(bool)
    lu = df["_lu"].astype(float)
    df["_lu5"] = (
        lu.groupby(df["code"], sort=False).rolling(5, min_periods=1).max().reset_index(level=0, drop=True)
        > 0
    )
    df["_lu_next"] = lu.groupby(df["code"], sort=False).shift(-1).fillna(0.0) > 0
    return df


def _spearman(a: Sequence[float], b: Sequence[float], *, min_n: int = 20) -> float | None:
    s = pd.DataFrame({"a": np.asarray(a, dtype="float64"), "b": np.asarray(b, dtype="float64")}).dropna()
    if len(s) < min_n:
        return None
    v = s["a"].rank().corr(s["b"].rank())
    return None if pd.isna(v) else float(v)


def _full_rank(universe: list[dict[str, Any]], profile: str) -> list[dict[str, Any]]:
    return select_secondary(universe, profile=profile, top_k=len(universe))["selected"]  # type: ignore[arg-type]


def collect_pools(
    fwd: pd.DataFrame,
    *,
    name_map: Mapping[str, str] | None,
    top_k: int = POOL_K,
    seed: int = RANDOM_SEED,
    every: int = 1,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-session pools + per-session IC rows. ``fwd`` from :func:`add_forward_returns`.

    Returns ``(cands, days)``: one row per (day, pool, member) carrying ``fwd`` /
    ``fwdd`` / market means, and one row per day with ICs and quintile spreads.
    """
    rng = np.random.default_rng(seed)
    cand_rows: list[dict[str, Any]] = []
    day_rows: list[dict[str, Any]] = []
    for di, (day, frame) in enumerate(fwd.groupby("trade_date", sort=True)):
        if every > 1 and di % every:
            continue
        universe = frame_to_universe(frame, name_map=name_map)
        if not universe:
            continue
        day_s = pd.Timestamp(day).date().isoformat()
        idx_by_code = {norm_code(c): i for c, i in zip(frame["code"], frame.index)}
        regime = s1_regime_state(universe)["state"]
        eligible = [r["code"] for r in universe if r.get("name") and not _is_st(r["name"])]
        elig_idx = [idx_by_code[c] for c in eligible if c in idx_by_code]
        elig = frame.loc[elig_idx]
        mkt = {h: float(elig[f"fwd_{h}"].mean()) if len(elig) else math.nan for h in HORIZONS}
        mktd = {h: float(elig[f"fwdd_{h}"].mean()) if len(elig) else math.nan for h in HORIZONS}

        pools: dict[str, list[tuple[str, float]]] = {}
        for sid, fn in _RUNNERS.items():
            pool = fn(universe, top_k=top_k)
            pools[sid] = [(str(c["code"]), float(c["score"])) for c in pool.get("candidates") or []]
        s4_full = _full_rank(universe, "short")
        s3_full = _full_rank(universe, "quality")
        if len(s4_full) >= 2 * top_k:
            pools["S4inv"] = [(str(r["code"]), float(r["secondaryScore"])) for r in s4_full[-top_k:]]
        by_amt = sorted(
            ((r["code"], float(r["amount"])) for r in universe if r.get("amount") is not None),
            key=lambda t: (-t[1], t[0]),
        )
        pools["S5amt"] = by_amt[:top_k]
        draw = rng.permutation(len(eligible))[:top_k] if len(eligible) >= top_k else []
        pools["RANDOM"] = [(eligible[int(i)], 0.0) for i in draw]

        names = {r["code"]: r.get("name") or "" for r in universe}
        for pid, members in pools.items():
            for rank, (code, score) in enumerate(members, start=1):
                i = idx_by_code.get(code)
                if i is None:
                    continue
                row = frame.loc[i]
                rec: dict[str, Any] = {
                    "date": day_s,
                    "pool": pid,
                    "rank": rank,
                    "code": code,
                    "row": int(i),
                    "score": score,
                    "regime": regime,
                    "pct_chg": float(row.get("pct_chg")) if pd.notna(row.get("pct_chg")) else math.nan,
                    "amount": float(row.get("amount")) if pd.notna(row.get("amount")) else math.nan,
                    "rev_chg": float(row.get("rev_chg")) if pd.notna(row.get("rev_chg")) else math.nan,
                    "vol20": float(row.get("vol20")) if pd.notna(row.get("vol20")) else math.nan,
                    "lu": bool(row["_lu"]),
                    "lu5": bool(row["_lu5"]),
                    "lu_next": bool(row["_lu_next"]),
                    "st_or_noname": (not names.get(code)) or _is_st(names.get(code)),
                }
                for h in HORIZONS:
                    rec[f"fwd_{h}"] = float(row[f"fwd_{h}"])
                    rec[f"fwdd_{h}"] = float(row[f"fwdd_{h}"])
                    rec[f"mkt_{h}"] = mkt[h]
                    rec[f"mktd_{h}"] = mktd[h]
                cand_rows.append(rec)

        drow: dict[str, Any] = {"date": day_s, "regime": regime, "eligible": len(elig_idx)}
        for label, full in (("s4", s4_full), ("s3", s3_full)):
            ids = [idx_by_code.get(str(r["code"])) for r in full]
            keep = [(r, i) for r, i in zip(full, ids) if i is not None]
            if not keep:
                continue
            scores = [float(r["secondaryScore"]) for r, _ in keep]
            sub = frame.loc[[i for _, i in keep]]
            for h in IC_HORIZONS:
                drow[f"ic_{label}_{h}"] = _spearman(scores, sub[f"fwd_{h}"].to_numpy())
            if label == "s4" and len(keep) >= 50:
                q = pd.qcut(pd.Series(scores).rank(method="first"), 5, labels=False)
                ex = sub["fwd_5"].to_numpy() - mkt[5]
                for k in range(5):
                    m = ex[q.to_numpy() == k]
                    drow[f"s4q{k + 1}_5"] = float(np.nanmean(m)) if np.isfinite(m).any() else None
        for col in ("rev_chg", "vol20", "amount"):
            if col in elig.columns:
                for h in (1, 5):
                    drow[f"ic_{col}_{h}"] = _spearman(elig[col].to_numpy(), elig[f"fwd_{h}"].to_numpy())
        day_rows.append(drow)
    return pd.DataFrame(cand_rows), pd.DataFrame(day_rows)


def simulate_exits(
    fwd: pd.DataFrame,
    cands: pd.DataFrame,
    *,
    policy: ExitPolicy | None = None,
    cost: CostModel | None = None,
) -> pd.DataFrame:
    """Engine exit rule per candidate (entry = signal close; no slot competition).

    Adds ``ex_net`` (net of :class:`CostModel`), ``ex_held`` (sessions),
    ``ex_reason`` (``stop_loss`` / ``target`` / ... / ``open``).
    """
    p = policy or ExitPolicy()
    cm = cost or CostModel()
    codes = fwd["code"].astype(str).to_numpy()
    close = fwd["close"].astype("float64").to_numpy()
    pct = pd.to_numeric(fwd.get("pct_chg"), errors="coerce").astype("float64").to_numpy()
    ma20 = fwd["ma20"].astype("float64").to_numpy()
    ma60 = fwd["ma60"].astype("float64").to_numpy()
    n = len(fwd)
    nets: list[float] = []
    helds: list[int] = []
    reasons: list[str] = []
    for i in cands["row"].astype(int).to_numpy():
        code = codes[i]
        entry = float(close[i])
        target = p.target_price(entry)
        peak = entry
        reason = "open"
        px = entry
        held = 0
        j = 0
        while True:
            j += 1
            k = i + j
            if k >= n or codes[k] != code:
                break
            px = float(close[k])
            held = j
            if is_limit_down(code, pct[k]):
                continue
            peak = advance_peak(peak, px)
            d = evaluate_exit(
                px=px, entry_price=entry, target=target, peak=peak, held_days=j,
                ma20=ma20[k], ma60=ma60[k], policy=p,
            )
            if d is not None:
                reason = d.reason.split("(")[0]
                break
        buy = entry * (1.0 + cm.trade_cost(code, is_buy=True))
        sell = px * (1.0 - cm.trade_cost(code, is_buy=False))
        nets.append(sell / buy - 1.0 if buy > 0 else math.nan)
        helds.append(held)
        reasons.append(reason)
    out = cands.copy()
    out["ex_net"] = nets
    out["ex_held"] = helds
    out["ex_reason"] = reasons
    return out


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def _tstat_daily(df: pd.DataFrame, col: str, h: int) -> float | None:
    """t of the daily-mean series, deflated by ``sqrt(h)`` for overlapping windows."""
    s = df.groupby("date")[col].mean().dropna()
    if len(s) < 10 or s.std(ddof=1) == 0:
        return None
    return float(s.mean() / s.std(ddof=1) * math.sqrt(len(s) / max(h, 1)))


def summarize(cands: pd.DataFrame, days: pd.DataFrame) -> dict[str, Any]:
    """Machine summary (fractions, not percent) of the pool study."""
    c = cands.copy()
    for h in HORIZONS:
        c[f"ex_{h}"] = c[f"fwd_{h}"] - c[f"mkt_{h}"]
        c[f"exd_{h}"] = c[f"fwdd_{h}"] - c[f"mktd_{h}"]
    c["year"] = c["date"].str[:4]
    out: dict[str, Any] = {"pools": {}, "ic": {}, "quintileS4Excess5": {}}
    for pid in POOLS:
        sub = c[c["pool"] == pid]
        if sub.empty:
            continue
        blk: dict[str, Any] = {"n": int(len(sub)), "days": int(sub["date"].nunique()), "horizons": {}}
        for h in HORIZONS:
            ok = sub[f"fwd_{h}"].notna()
            s = sub[ok]
            blk["horizons"][str(h)] = {
                "n": int(len(s)),
                "meanFwd": _f(s[f"fwd_{h}"].mean()),
                "meanExcess": _f(s[f"ex_{h}"].mean()),
                "winRate": _f((s[f"fwd_{h}"] > 0).mean()),
                "excessWinRate": _f((s[f"ex_{h}"] > 0).mean()),
                "tExcess": _tstat_daily(s, f"ex_{h}", h),
                "meanExcessDelayed": _f(sub[f"exd_{h}"].mean()),
            }
        blk["byRegime5"] = {
            str(k): {"n": int(len(g)), "meanExcess": _f(g["ex_5"].mean()), "winRate": _f((g["fwd_5"] > 0).mean())}
            for k, g in sub[sub["fwd_5"].notna()].groupby("regime")
        }
        blk["byYear5"] = {
            str(k): _f(g["ex_5"].mean()) for k, g in sub[sub["fwd_5"].notna()].groupby("year")
        }
        blk["entry"] = {
            "signalLimitUp": _f(sub["lu"].mean()),
            "limitUpLast5": _f(sub["lu5"].mean()),
            "nextDayLimitUp": _f(sub["lu_next"].mean()),
            "meanSignalPct": _f(sub["pct_chg"].mean()),
            "meanRev20": _f(sub["rev_chg"].mean()),
            "meanVol20": _f(sub["vol20"].mean()),
            "medianAmount": _f(sub["amount"].median()),
            "stOrNoName": _f(sub["st_or_noname"].mean()),
        }
        if "ex_net" in sub.columns:
            closed = sub[sub["ex_reason"] != "open"]
            blk["exitSim"] = {
                "closed": int(len(closed)),
                "winRate": _f((closed["ex_net"] > 0).mean()),
                "meanNet": _f(closed["ex_net"].mean()),
                "meanHeld": _f(closed["ex_held"].mean()),
                "reasons": {str(k): _f(v) for k, v in closed["ex_reason"].value_counts(normalize=True).items()},
                "stopMeanHeld": _f(closed.loc[closed["ex_reason"] == "stop_loss", "ex_held"].mean()),
            }
        if pid in ("S5", "S5amt"):
            blk["concentration"] = {
                "uniqueCodes": int(sub["code"].nunique()),
                "saturatedShare": _f((sub["amount"] >= S5_SATURATION_AMOUNT).mean()),
                "codePrefix000Share": _f(sub["code"].str.startswith("000").mean()),
                "topCodes": {str(k): int(v) for k, v in sub["code"].value_counts().head(10).items()},
            }
        out["pools"][pid] = blk
    for col in [x for x in days.columns if x.startswith("ic_")]:
        s = pd.to_numeric(days[col], errors="coerce").dropna()
        if s.empty:
            continue
        out["ic"][col] = {
            "mean": _f(s.mean()),
            "ir": _f(s.mean() / s.std(ddof=1)) if len(s) > 1 and s.std(ddof=1) > 0 else None,
            "positiveShare": _f((s > 0).mean()),
            "days": int(len(s)),
        }
    for k in range(1, 6):
        col = f"s4q{k}_5"
        if col in days.columns:
            out["quintileS4Excess5"][f"Q{k}"] = _f(pd.to_numeric(days[col], errors="coerce").mean())
    out["regimeDays"] = {str(k): int(v) for k, v in days["regime"].value_counts().items()} if "regime" in days else {}
    return out


def _pct(v: Any, d: int = 2) -> str:
    x = _f(v)
    return "-" if x is None else f"{x * 100:.{d}f}%"


def _n(v: Any, d: int = 3) -> str:
    x = _f(v)
    return "-" if x is None else f"{x:.{d}f}"


def render_markdown(summary: Mapping[str, Any], meta: Mapping[str, Any] | None = None) -> str:
    pools = summary.get("pools") or {}
    lines = ["# 影子 S4 / S5 选股质量诊断（Round1 候选池前向收益）", ""]
    for k, v in (meta or {}).items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## 前向收益（信号日收盘买入；超额 = 减当日合格宇宙等权均值）", ""]
    lines.append("| 池 | h | n | 均收益 | 均超额 | 胜率 | 超额胜率 | t(超额) | 延迟1日均超额 |")
    lines.append("|----|---|---|--------|--------|------|----------|---------|---------------|")
    for pid, blk in pools.items():
        for h, r in blk["horizons"].items():
            lines.append(
                f"| {pid} | {h} | {r['n']} | {_pct(r['meanFwd'])} | {_pct(r['meanExcess'])} | "
                f"{_pct(r['winRate'], 1)} | {_pct(r['excessWinRate'], 1)} | {_n(r['tExcess'], 2)} | "
                f"{_pct(r['meanExcessDelayed'])} |"
            )
    lines += ["", "## 按 regime（h=5 均超额 / 胜率）", ""]
    for pid, blk in pools.items():
        parts = [f"{k}: {_pct(v['meanExcess'])} / {_pct(v['winRate'], 1)} (n={v['n']})" for k, v in blk["byRegime5"].items()]
        lines.append(f"- {pid}: " + "；".join(parts))
    lines += ["", "## 按年（h=5 均超额）", ""]
    for pid, blk in pools.items():
        lines.append(f"- {pid}: " + "；".join(f"{k} {_pct(v)}" for k, v in blk["byYear5"].items()))
    lines += ["", "## 入场特征", ""]
    lines.append("| 池 | 信号日涨停 | 近5日有涨停 | 次日涨停 | 信号日涨幅(点) | 20日收益 | vol20 | 成交额中位 | ST/无名 |")
    lines.append("|----|-----------|-------------|----------|----------------|----------|-------|------------|---------|")
    for pid, blk in pools.items():
        e = blk["entry"]
        lines.append(
            f"| {pid} | {_pct(e['signalLimitUp'], 1)} | {_pct(e['limitUpLast5'], 1)} | {_pct(e['nextDayLimitUp'], 1)} | "
            f"{_n(e['meanSignalPct'], 2)} | {_pct(e['meanRev20'], 1)} | {_pct(e['meanVol20'], 2)} | "
            f"{_n((e['medianAmount'] or 0) / 1e8, 2)} 亿 | {_pct(e['stOrNoName'], 1)} |"
        )
    lines += ["", "## 引擎退出规则逐票模拟（无席位竞争）", ""]
    lines.append("| 池 | 已平仓 | 胜率 | 均净收益 | 均持有 | 止损占比 | 止损均持有 |")
    lines.append("|----|--------|------|----------|--------|----------|------------|")
    for pid, blk in pools.items():
        x = blk.get("exitSim")
        if not x:
            continue
        lines.append(
            f"| {pid} | {x['closed']} | {_pct(x['winRate'], 1)} | {_pct(x['meanNet'])} | {_n(x['meanHeld'], 1)} | "
            f"{_pct((x['reasons'] or {}).get('stop_loss'), 1)} | {_n(x['stopMeanHeld'], 1)} |"
        )
    lines += ["", "## IC（日度 Spearman）", "", "| 列 | 均值 | IR | 正值占比 | 天数 |", "|----|------|----|----------|------|"]
    for col, r in (summary.get("ic") or {}).items():
        lines.append(f"| {col} | {_n(r['mean'], 4)} | {_n(r['ir'], 3)} | {_pct(r['positiveShare'], 1)} | {r['days']} |")
    q = summary.get("quintileS4Excess5") or {}
    if q:
        lines += ["", "S4 综合分五分位 h=5 均超额（Q5=最高分）：" + "；".join(f"{k} {_pct(v, 3)}" for k, v in q.items())]
    for pid in ("S5", "S5amt"):
        conc = (pools.get(pid) or {}).get("concentration")
        if conc:
            lines += ["", f"{pid} 集中度：唯一代码 {conc['uniqueCodes']}，分数饱和（成交额≥8 亿）占比 "
                      f"{_pct(conc['saturatedShare'], 1)}，000 开头占比 {_pct(conc['codePrefix000Share'], 1)}；"
                      f"最常入池 {conc['topCodes']}"]
    lines += ["", "> 诊断产物（研究指标）；SIMULATE；不替换主路径 picks。", ""]
    return "\n".join(lines)


def _data_checks(db: str, bars: pd.DataFrame, feats: pd.DataFrame) -> dict[str, Any]:
    import sqlite3

    from ..pct_scale import SCALE_POINTS, detect_pct_scale
    from ..portfolio import asset_class

    uri = "file:%s?mode=ro" % str(db).replace("\\", "/")
    con = sqlite3.connect(uri, uri=True)
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(daily_price)")]
        idx = con.execute(
            "SELECT code, COUNT(*) FROM daily_price WHERE code IN "
            "('000300.SH','000905.SH','000852.SH','399905.SZ','000905.SZ') GROUP BY code"
        ).fetchall()
    finally:
        con.close()
    scales = detect_pct_scale(bars)
    stock = [c for c in scales.index if asset_class(c) == "stock"]
    pts = sum(1 for c in stock if scales[c] == SCALE_POINTS)
    pct = pd.to_numeric(feats["pct_chg"], errors="coerce")
    code6 = feats["code"].astype(str).str[:6]
    lim = np.where(code6.str.startswith(("30", "68")), 20.0, 10.0)
    lu_per_day = (pct >= lim - 0.01).groupby(feats["trade_date"]).sum()
    return {
        "dailyPriceColumns": cols,
        "indexLikeRows": {str(c): int(n) for c, n in idx},
        "stockCodes": len(stock),
        "stockCodesOnPointsScale": pts,
        "medianLimitUpPerDay": _f(lu_per_day.median()),
        "maxAbsPctPoints": _f(pct.abs().max()),
        "medianAmountYuan": _f(pd.to_numeric(feats.get("amount"), errors="coerce").median()),
    }


def main(argv: list[str] | None = None) -> int:
    import os

    from ..backtest_cli import ENV_DB, filter_universe, load_engine_bars, load_engine_industry, load_engine_names
    from .backtest import prepare_shadow_frame

    ap = argparse.ArgumentParser(description="影子 S4/S5 候选池前向收益诊断（只读 market.db）")
    ap.add_argument("--db", default=None)
    ap.add_argument("--start", default="2021-01-04")
    ap.add_argument("--end", default=None)
    ap.add_argument("--top-k", type=int, default=POOL_K)
    ap.add_argument("--every", type=int, default=1, help="每 N 个交易日取一次截面（默认 1=每日）")
    ap.add_argument("--seed", type=int, default=RANDOM_SEED)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args(argv)

    db = (args.db or os.environ.get(ENV_DB, "")).strip()
    if not db or not Path(db).is_file():
        print(f"[fail] market.db 不可用：{db or '未设置 ' + ENV_DB}", file=sys.stderr)
        return 2
    from datetime import date, timedelta

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
    checks = _data_checks(db, bars, feats)
    print(f"[load] rows={len(feats)} checks={checks}", file=sys.stderr)
    fwd = add_forward_returns(feats)
    cands, days = collect_pools(fwd, name_map=names, top_k=args.top_k, seed=args.seed, every=args.every)
    cands = simulate_exits(fwd, cands)
    summary = summarize(cands, days)
    summary["dataChecks"] = checks
    meta = {
        "区间": f"{feats['trade_date'].min().date()} ~ {feats['trade_date'].max().date()}",
        "截面步长": args.every,
        "top_k": args.top_k,
        "seed": args.seed,
        "数据检查": json.dumps(checks, ensure_ascii=False),
        "regime 天数": summary.get("regimeDays"),
    }
    summary["meta"] = {k: str(v) for k, v in meta.items()}
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "s4_s5_diagnosis.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    md = render_markdown(summary, meta)
    (out / "s4_s5_diagnosis.md").write_text(md, encoding="utf-8")
    cands.to_csv(out / "s4_s5_candidates.csv.gz", index=False, compression="gzip")
    days.to_csv(out / "s4_s5_days.csv.gz", index=False, compression="gzip")
    print(md)
    print(f"[write] {out}", file=sys.stderr)
    return 0


__all__ = [
    "HORIZONS",
    "POOLS",
    "add_forward_returns",
    "collect_pools",
    "render_markdown",
    "simulate_exits",
    "summarize",
]


if __name__ == "__main__":
    raise SystemExit(main())
