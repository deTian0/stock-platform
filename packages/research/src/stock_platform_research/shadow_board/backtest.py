"""Walk-forward backtest of the multi-strategy shadow Final Board (ADR 0093 增补).

Why
---
The shadow board had a forward ledger but no history: nobody could say whether
the five-school arbitration beats the ``lvrev`` baseline. This module replays the
Final Board through the **same** loop the production backtest uses
(:func:`book_replay.replay_book`, the ``X4`` single definition), so T+1 entry at
the reference close, limit-up / limit-down seals, cooldown, lot rounding and the
:class:`portfolio.CostModel` are byte-identical between the two arms.

Only the **entry provider** differs: each session's cross-section (rows up to
that day only — ``compute_features`` is PIT-safe) is converted to the shadow
universe shape and fed to :func:`schools.run_round1` →
:func:`round2.apply_round2_set_a` — the very functions the daily hook calls.
No second copy of the school or gate logic exists.

Known limits (stated, not hidden)
---------------------------------
* ``name`` (ST filter) and ``industry`` (concentration cap) come from the current
  ``fundamentals`` snapshot, not PIT — the same limitation the ``S4`` neutralized
  baseline already carries.
* S2 (theme/event) has no historical DI payload → empty pool every day; S5 runs
  on its amount/illiq liquidity thin rule (no historical fund flow). This is the
  "题材数据缺失先接受" choice; the report records it in ``schoolCoverage``.
* Set B / LLM never enter (``excludedFromPerformance``); only Set A is replayed.

SIMULATE only; not investment advice. Pure: no I/O, no DB.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

import pandas as pd

from ..backtest import UNIVERSES, compute_features
from ..book_replay import EntryContext, EntryProvider, ReplayParams, replay_book
from ..neutralization import attach_industry
from ..portfolio import compute_metrics, is_etf, is_fund, norm_code
from ..secondary_pick import AMOUNT_MIN
from ..strategy_ab import AB_METRIC_KEYS, _delta_metrics, _review_block
from .round2 import DEFAULT_ARBITRATION, DEFAULT_MIN_SEATS, apply_round2_set_a
from .schools import SCHOOL_IDS, run_round1

#: Columns the shadow schools read from a cross-section row.
_ROW_FIELDS = ("close", "amount", "vol20", "rev_chg", "ma20", "ma60", "rs20", "pct_chg")


def prepare_shadow_frame(
    bars: pd.DataFrame,
    *,
    universe: str = "stock",
    start: str | None = None,
    end: str | None = None,
    industry_map: Mapping[str, str] | None = None,
    pct_scale: str = "auto",
) -> pd.DataFrame:
    """``bars`` (needs ``amount``) → feature frame + ``amount`` + ``rs20``.

    Same steps as :func:`backtest.prepare_book_frame` (features → universe →
    window → industry), plus the ``amount`` raw column carried through and
    ``rs20 = (close / ma20 − 1) × 100`` (the PIT panel definition in ``panel.py``).
    The lvrev arm can consume this frame unchanged (extra columns are ignored).
    """
    universe = str(universe).strip().lower()
    if universe not in UNIVERSES:
        raise ValueError(f"universe must be one of {UNIVERSES}, got {universe!r}")
    keep = ("amount",) if "amount" in bars.columns else ()
    feats = compute_features(bars, pct_scale=pct_scale, keep_extra=keep)
    if universe == "stock":
        feats = feats[~feats["code"].map(is_fund)]
    elif universe == "etf":
        feats = feats[feats["code"].map(is_etf)]
    if start is not None:
        feats = feats[feats["trade_date"] >= pd.Timestamp(start)]
    if end is not None:
        feats = feats[feats["trade_date"] <= pd.Timestamp(end)]
    if industry_map is not None:
        feats = attach_industry(feats, industry_map)
    feats = feats.copy()
    ma20 = feats["ma20"].astype("float64")
    feats["rs20"] = ((feats["close"].astype("float64") / ma20 - 1.0) * 100.0).where(ma20 > 0)
    return feats.reset_index(drop=True)


def _clean(value: Any) -> Any:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return value
    return None if math.isnan(f) else f


def frame_to_universe(
    frame: pd.DataFrame,
    *,
    name_map: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """One session's cross-section → shadow universe rows (liquidity pre-filtered).

    Rows below ``AMOUNT_MIN`` are dropped up front: every school and the Set A
    gate reject them anyway, so this only saves time — it never admits a row.
    ``name`` missing → ``""`` so ``secondary_pick`` rejects it (fail-closed).
    """
    if frame is None or frame.empty:
        return []
    sub = frame
    if "amount" in sub.columns:
        sub = sub[sub["amount"].astype("float64") >= AMOUNT_MIN]
    names = {norm_code(k): str(v) for k, v in (name_map or {}).items() if v}
    cols = [c for c in _ROW_FIELDS if c in sub.columns]
    has_ind = "industry" in sub.columns
    out: list[dict[str, Any]] = []
    for rec in sub[["code", *cols, *(["industry"] if has_ind else [])]].to_dict("records"):
        raw = str(rec["code"])
        code = norm_code(raw)
        row: dict[str, Any] = {"code": code, "symbol": raw}
        for key in cols:
            row[key] = _clean(rec.get(key))
        if row.get("close") is not None and row.get("ma20") is not None:
            row["trend_up"] = bool(row["close"] >= row["ma20"])
        row["name"] = names.get(code, "")
        ind = rec.get("industry") if has_ind else None
        if ind and str(ind) != "_unknown":
            row["industry"] = str(ind)
        out.append(row)
    return out


def shadow_board_for_frame(
    frame: pd.DataFrame,
    *,
    day: str,
    name_map: Mapping[str, str] | None = None,
    top_k: int = 8,
    regime: Mapping[str, bool] | None = None,
    arbitration: str = DEFAULT_ARBITRATION,
    min_seats: int = DEFAULT_MIN_SEATS,
) -> dict[str, Any]:
    """Round1 → Round2 Set A for one session (the daily hook's exact functions).

    ``arbitration`` / ``min_seats`` are the offline experiment knob of
    :func:`round2.apply_round2_set_a`; the default ``"d"`` is the factory rule.
    """
    universe = frame_to_universe(frame, name_map=name_map)
    schools = run_round1(universe, top_k=top_k, asof=day, regime=regime)
    if arbitration == DEFAULT_ARBITRATION:
        round2 = apply_round2_set_a(schools)
    else:
        round2 = apply_round2_set_a(schools, arbitration=arbitration, min_seats=min_seats)
    return {"schools": schools, "round2": round2, "universeSize": len(universe)}


def shadow_entry_provider(
    *,
    name_map: Mapping[str, str] | None = None,
    top_k: int = 8,
    regime: Mapping[str, bool] | None = None,
    stats: dict[str, Any] | None = None,
    arbitration: str = DEFAULT_ARBITRATION,
    min_seats: int = DEFAULT_MIN_SEATS,
) -> EntryProvider:
    """Entry provider that opens the day's shadow Final Board (Set A order).

    ``stats`` (optional, mutated) collects empty-board days and per-school
    coverage for the report. The loop still applies max_positions / held-code /
    max_picks_per_day / limit-up / cooldown — the provider cannot bypass them.
    ``stats["entrySchool"]`` maps ``(day_index, raw_code) → school`` so the caller
    can attribute the fills the loop actually made back to a school.
    """
    acc = stats if stats is not None else {}
    acc.setdefault("days", 0)
    acc.setdefault("emptyBoardDays", 0)
    acc.setdefault("boardSizeSum", 0)
    acc.setdefault("schoolNonEmptyDays", {sid: 0 for sid in SCHOOL_IDS})
    acc.setdefault("schoolSeats", {sid: 0 for sid in SCHOOL_IDS})
    acc.setdefault("entrySchool", {})

    def _provider(ctx: EntryContext) -> list[dict[str, Any]]:
        result = shadow_board_for_frame(
            ctx.frame,
            day=ctx.day,
            name_map=name_map,
            top_k=top_k,
            regime=regime,
            arbitration=arbitration,
            min_seats=min_seats,
        )
        passed = result["round2"].get("passed") or []
        acc["days"] += 1
        acc["boardSizeSum"] += len(passed)
        if not passed:
            acc["emptyBoardDays"] += 1
        for sid, pool in result["schools"].items():
            if (pool or {}).get("candidates"):
                acc["schoolNonEmptyDays"][sid] = acc["schoolNonEmptyDays"].get(sid, 0) + 1
        for row in passed:
            sid = str(row.get("school"))
            acc["schoolSeats"][sid] = acc["schoolSeats"].get(sid, 0) + 1
        if not passed:
            return []
        by_code = {norm_code(c): (c, px, pc) for c, px, pc in zip(
            ctx.frame["code"], ctx.frame["close"],
            ctx.frame["pct_chg"] if "pct_chg" in ctx.frame.columns else [None] * len(ctx.frame),
        )}
        out: list[dict[str, Any]] = []
        for row in passed:
            hit = by_code.get(str(row.get("code")))
            if hit is None:
                continue
            raw_code, px, pct = hit
            out.append({"code": str(raw_code), "close": float(px), "pct_chg": pct,
                        "school": row.get("school")})
            acc["entrySchool"].setdefault((ctx.day_index, str(raw_code)), row.get("school"))
        return out

    return _provider


def _arm(loop: Mapping[str, Any], initial: float) -> dict[str, Any]:
    metrics = compute_metrics(loop["equity_curve"], loop["trades"], initial_capital=initial)
    return {
        "finalEquity": loop["final_equity"],
        "tradeCount": len(loop.get("trades") or []),
        "nDays": loop["n_days"],
        "metrics": metrics,
        "review": _review_block(loop["trades"], loop.get("open_positions")),
    }


def _shadow_stats_block(stats: Mapping[str, Any]) -> dict[str, Any]:
    days = int(stats.get("days") or 0)
    empty = int(stats.get("emptyBoardDays") or 0)
    return {
        "evaluatedDays": days,
        "emptyBoardDays": empty,
        "emptyBoardRatio": (empty / days) if days else None,
        "avgBoardSize": (float(stats.get("boardSizeSum") or 0) / days) if days else None,
        "schoolCoverage": {
            sid: {
                "nonEmptyDays": int((stats.get("schoolNonEmptyDays") or {}).get(sid, 0)),
                "seats": int((stats.get("schoolSeats") or {}).get(sid, 0)),
            }
            for sid in SCHOOL_IDS
        },
        "note": (
            "evaluatedDays 只计引擎调用 provider 的交易日（满仓 / regime 关闭日不调用）；"
            "空榜为 fail-closed 合法态，不补位。"
        ),
    }


def _school_fills(
    loop: Mapping[str, Any], entry_school: Mapping[tuple[int, str], Any]
) -> dict[str, Any]:
    """Attribute the loop's actual fills (closed trades + still-open) to a school.

    Board seats ≠ fills: the loop only buys the head of the board and only while
    slots are free, so a school can hold seats yet never be bought. This block
    reports what was really traded; unattributable fills land in ``_unknown``.
    """
    out: dict[str, dict[str, Any]] = {}

    def _slot(sid: str) -> dict[str, Any]:
        return out.setdefault(sid, {"fills": 0, "closed": 0, "open": 0, "wins": 0, "netRetSum": 0.0})

    for t in loop.get("trades") or []:
        sid = str(entry_school.get((int(t["entry_idx"]), str(t["code"]))) or "_unknown")
        s = _slot(sid)
        s["fills"] += 1
        s["closed"] += 1
        r = float(t.get("net_ret") or 0.0)
        s["netRetSum"] += r
        if r > 0:
            s["wins"] += 1
    for pos in loop.get("open_positions") or []:
        sid = str(entry_school.get((int(pos["entry_idx"]), str(pos["code"]))) or "_unknown")
        s = _slot(sid)
        s["fills"] += 1
        s["open"] += 1
    block: dict[str, Any] = {}
    for sid in [*SCHOOL_IDS, *sorted(k for k in out if k not in SCHOOL_IDS)]:
        s = out.get(sid) or {"fills": 0, "closed": 0, "open": 0, "wins": 0, "netRetSum": 0.0}
        closed = s["closed"]
        block[sid] = {
            "fills": s["fills"],
            "closed": closed,
            "open": s["open"],
            "winRate": (s["wins"] / closed) if closed else None,
            "avgNetRetPct": (s["netRetSum"] / closed) if closed else None,
        }
    return block


def run_shadow_book(
    feats: pd.DataFrame,
    *,
    name_map: Mapping[str, str] | None = None,
    params: ReplayParams | None = None,
    top_k: int = 8,
    arbitration: str = DEFAULT_ARBITRATION,
    min_seats: int = DEFAULT_MIN_SEATS,
) -> dict[str, Any]:
    """Replay the shadow Final Board alone through the shared loop."""
    p = params or ReplayParams()
    stats: dict[str, Any] = {}
    loop = replay_book(
        feats,
        entry_provider=shadow_entry_provider(
            name_map=name_map,
            top_k=top_k,
            regime=p.regime,
            stats=stats,
            arbitration=arbitration,
            min_seats=min_seats,
        ),
        params=p,
    )
    out = _arm(loop, p.initial_capital)
    out["shadow"] = _shadow_stats_block(stats)
    out["shadow"]["schoolFills"] = _school_fills(loop, stats.get("entrySchool") or {})
    out["shadow"]["arbitration"] = arbitration
    if arbitration == "b":
        out["shadow"]["minSeats"] = int(min_seats)
    out["trades"] = loop["trades"]
    out["equityCurve"] = loop["equity_curve"]
    return out


def _benchmark_return(curve: list[Mapping[str, Any]], index_close: Mapping[str, float] | None) -> float | None:
    if not curve or not index_close:
        return None
    first = index_close.get(str(curve[0]["date"]))
    last = index_close.get(str(curve[-1]["date"]))
    if not first or not last:
        return None
    return float(last) / float(first) - 1.0


def compare_shadow_vs_lvrev(
    feats: pd.DataFrame,
    *,
    name_map: Mapping[str, str] | None = None,
    params: ReplayParams | None = None,
    top_k: int = 8,
    index_close: Mapping[str, float] | None = None,
    arbitration: str = DEFAULT_ARBITRATION,
    min_seats: int = DEFAULT_MIN_SEATS,
) -> dict[str, Any]:
    """lvrev 出厂基线 vs 影子 Final Board on one frame, one engine.

    ``delta = shadow − lvrev``. ``index_close`` (optional ``date → close``)
    adds an excess-return line; missing → ``None`` (never fabricated).
    ``arbitration`` is the offline seat-allocation experiment knob (default
    ``"d"`` = factory); the lvrev arm is untouched by it, so the baseline column
    stays comparable across runs.
    """
    from ..book_replay import screener_entry_provider

    p = params or ReplayParams()
    if feats is None or feats.empty:
        return {
            "ok": False,
            "reason": "empty feature frame",
            "environment": "SIMULATE",
            "liveTradingEnabled": False,
        }
    base_loop = replay_book(feats, entry_provider=screener_entry_provider(), params=p)
    base = _arm(base_loop, p.initial_capital)
    shadow = run_shadow_book(
        feats,
        name_map=name_map,
        params=p,
        top_k=top_k,
        arbitration=arbitration,
        min_seats=min_seats,
    )
    bench = _benchmark_return(base_loop["equity_curve"], index_close)
    for arm in (base, shadow):
        tr = (arm["metrics"] or {}).get("total_return")
        arm["benchmarkReturn"] = bench
        arm["excessReturn"] = (float(tr) - bench) if (tr is not None and bench is not None) else None
    shadow_public = {k: v for k, v in shadow.items() if k not in ("trades", "equityCurve")}
    return {
        "ok": True,
        "start": base_loop["equity_curve"][0]["date"] if base_loop["equity_curve"] else None,
        "end": base_loop["equity_curve"][-1]["date"] if base_loop["equity_curve"] else None,
        "lvrev": base,
        "shadow": shadow_public,
        "delta": _delta_metrics(base["metrics"] or {}, shadow["metrics"] or {}),
        "metricKeys": list(AB_METRIC_KEYS),
        "sameEngine": True,
        "excludedFromPerformance": True,
        "shadowOnly": True,
        "replacesPicks": False,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "limitations": [
            "name/industry 取 fundamentals 当前快照（非 PIT），与 S4 中性化基线同口径限制",
            "S2 无历史题材/事件 DI → 历史回测恒空池；S5 走 amount/illiq 流动性薄规则",
            "仅回放集 A（确定性仲裁）；集 B / LLM 不进回测",
        ],
        "disclaimer": "影子终榜历史回测（研究指标）；非投资建议；SIMULATE；不替换主路径 picks。",
    }


def _pct(v: Any) -> str:
    try:
        return f"{float(v) * 100:.2f}%"
    except (TypeError, ValueError):
        return "-"


def _num(v: Any, d: int = 3) -> str:
    try:
        return f"{float(v):.{d}f}"
    except (TypeError, ValueError):
        return "-"


def render_shadow_backtest_markdown(payload: Mapping[str, Any]) -> str:
    """Markdown side-by-side report (JSON is the machine contract)."""
    if not payload.get("ok"):
        return f"# 影子终榜回测\n\n无可用数据：{payload.get('reason')}\n"
    b = payload["lvrev"]
    s = payload["shadow"]
    bm, sm = b.get("metrics") or {}, s.get("metrics") or {}
    rows = [
        ("总收益", _pct(bm.get("total_return")), _pct(sm.get("total_return"))),
        ("年化", _pct(bm.get("cagr")), _pct(sm.get("cagr"))),
        ("基准收益", _pct(b.get("benchmarkReturn")), _pct(s.get("benchmarkReturn"))),
        ("超额", _pct(b.get("excessReturn")), _pct(s.get("excessReturn"))),
        ("最大回撤", _pct(bm.get("max_drawdown")), _pct(sm.get("max_drawdown"))),
        ("夏普", _num(bm.get("sharpe")), _num(sm.get("sharpe"))),
        ("胜率", _pct(bm.get("win_rate")), _pct(sm.get("win_rate"))),
        ("成交笔数", str(bm.get("n_trades")), str(sm.get("n_trades"))),
        ("平均持有日", _num(bm.get("avg_hold_days"), 1), _num(sm.get("avg_hold_days"), 1)),
        ("年换手(次)", _num(bm.get("turnover_per_year"), 2), _num(sm.get("turnover_per_year"), 2)),
        ("平均仓位", _pct(bm.get("avg_invested_ratio")), _pct(sm.get("avg_invested_ratio"))),
    ]
    sh = s.get("shadow") or {}
    lines = [
        "# 影子终榜 vs lvrev 基线（同一引擎回测）",
        "",
        f"- 区间：{payload.get('start')} ~ {payload.get('end')}",
        "- 引擎：book_replay.replay_book（T+1 / 涨跌停 / 成本与主回测同源）",
        f"- 仲裁模式：`{sh.get('arbitration') or DEFAULT_ARBITRATION}`"
        + (f"（min_seats={sh.get('minSeats')}）" if sh.get("minSeats") is not None else "")
        + ("（出厂默认）" if (sh.get("arbitration") or DEFAULT_ARBITRATION) == DEFAULT_ARBITRATION else "（离线实验，非出厂）"),
        f"- 影子空榜比例：{_pct(sh.get('emptyBoardRatio'))}"
        f"（{sh.get('emptyBoardDays')}/{sh.get('evaluatedDays')} 个评估日），"
        f"平均席位 {_num(sh.get('avgBoardSize'), 2)}",
        "",
        "| 指标 | lvrev 基线 | 影子终榜 |",
        "|------|-----------|----------|",
        *[f"| {k} | {a} | {c} |" for k, a, c in rows],
        "",
        "## 学校覆盖",
        "",
        "| 学校 | 非空池日 | 入终榜席位 | 实际成交 | 已平仓胜率 | 已平仓均净收益 |",
        "|------|----------|------------|----------|------------|----------------|",
    ]
    fills = sh.get("schoolFills") or {}
    for sid, cov in (sh.get("schoolCoverage") or {}).items():
        f = fills.get(sid) or {}
        avg = f.get("avgNetRetPct")
        lines.append(
            f"| {sid} | {cov.get('nonEmptyDays')} | {cov.get('seats')} | {f.get('fills', '-')} | "
            f"{_pct(f.get('winRate'))} | {(f'{float(avg):.2f}%') if avg is not None else '-'} |"
        )
    unk = fills.get("_unknown")
    if unk and unk.get("fills"):
        lines.append(f"| _unknown | - | - | {unk.get('fills')} | - | - |")
    lines += ["", "## 已知限制", ""]
    lines += [f"- {x}" for x in payload.get("limitations") or []]
    lines += ["", f"> {payload.get('disclaimer')}", ""]
    return "\n".join(lines)


__all__ = [
    "compare_shadow_vs_lvrev",
    "frame_to_universe",
    "prepare_shadow_frame",
    "render_shadow_backtest_markdown",
    "run_shadow_book",
    "shadow_board_for_frame",
    "shadow_entry_provider",
]
