"""Set B: Beta-prior school sizing (docs/plans/multi-strategy-final-board.md §11.9).

Experiment knob, default **off**, offline backtest only.

A school's per-slot budget is multiplied by ``mult_s`` derived from the posterior
expectation of its recent closed trades. The update is point-in-time: a trade
counts only when ``exit_idx < signal_day`` (strictly closed before the signal
session). Board membership, order, hard gates, seats and ``max_positions`` are
untouched; the multiplier only changes how much cash a board row may use.

Pure functions here; no I/O, no DB. SIMULATE only. Not investment advice.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

#: Prior: ``p ~ Beta(PRIOR_ALPHA, PRIOR_BETA)`` (2 pseudo-wins, 2 pseudo-losses).
PRIOR_ALPHA = 2.0
PRIOR_BETA = 2.0
#: Pseudo win / loss magnitude in percent points (``net_ret`` units): ±5%.
PRIOR_R = 5.0
#: Rolling window: most recent closed trades per school.
WINDOW = 60
#: Multiplier clip bounds.
MULT_LO = 0.5
MULT_HI = 1.5


def posterior_expected_return(rets: Sequence[float]) -> float:
    """Posterior expected single-trade net return (percent points) for one school.

    ``rets`` are closed-trade ``net_ret`` values, oldest first. Empty input gives
    ``E = 0`` (the prior alone is symmetric: p̂ = 0.5, avg_win = avg_loss = R0).
    """
    n = len(rets)
    w = sum(1 for r in rets if r > 0)
    l = n - w
    p_hat = (PRIOR_ALPHA + w) / (PRIOR_ALPHA + PRIOR_BETA + n)
    sum_win = sum(r for r in rets if r > 0)
    sum_loss = sum(-r for r in rets if r <= 0)
    avg_win = (sum_win + PRIOR_ALPHA * PRIOR_R) / (w + PRIOR_ALPHA)
    avg_loss = (sum_loss + PRIOR_BETA * PRIOR_R) / (l + PRIOR_BETA)
    return p_hat * avg_win - (1.0 - p_hat) * avg_loss


def slot_multiplier(rets: Sequence[float]) -> float:
    """``clip(1 + E / R0, 0.5, 1.5)``; zero sample → exactly 1.0."""
    e = posterior_expected_return(list(rets)[-WINDOW:])
    return min(max(1.0 + e / PRIOR_R, MULT_LO), MULT_HI)


def bayes_school_mults(
    trades: Sequence[Mapping[str, Any]],
    entry_school: Mapping[tuple[int, str], Any],
    day_index: int,
) -> dict[str, float]:
    """PIT per-school multipliers for the signal session ``day_index``.

    Only trades with ``exit_idx < day_index`` are visible. Attribution follows the
    loop's entry record ``(entry_idx, code) → school``. Schools without a visible
    closed trade are absent from the result (caller defaults them to 1.0).
    """
    by_school: dict[str, list[float]] = {}
    for t in trades:
        if int(t["exit_idx"]) >= day_index:
            continue
        sid = entry_school.get((int(t["entry_idx"]), str(t["code"])))
        if sid is None:
            continue
        by_school.setdefault(str(sid), []).append(float(t.get("net_ret") or 0.0))
    return {sid: slot_multiplier(rets) for sid, rets in by_school.items()}


def evaluate_bayes_criteria(
    d_arm: Mapping[str, Any],
    b_arm: Mapping[str, Any],
    d_years: Mapping[str, Mapping[str, Any]],
    b_years: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Pre-registered four criteria (plan §11.9). All four must pass."""
    dm, bm = d_arm.get("metrics") or {}, b_arm.get("metrics") or {}
    d_tr, b_tr = dm.get("total_return"), bm.get("total_return")
    d_sh, b_sh = dm.get("sharpe"), bm.get("sharpe")
    d_mdd, b_mdd = dm.get("max_drawdown"), bm.get("max_drawdown")

    c1_ok = (
        d_tr is not None and b_tr is not None and d_sh is not None and b_sh is not None
        and float(b_tr) > float(d_tr) and float(b_sh) > float(d_sh)
    )
    c2_ok = d_mdd is not None and b_mdd is not None and float(b_mdd) >= float(d_mdd) - 0.02

    years = sorted(set(d_years) & set(b_years), key=int)
    sharpe_wins = 0
    excesses: list[float] = []
    year_rows: list[dict[str, Any]] = []
    for y in years:
        ds, bs = d_years[y].get("sharpe"), b_years[y].get("sharpe")
        if ds is not None and bs is not None and float(bs) >= float(ds):
            sharpe_wins += 1
        dr, br = d_years[y].get("total_return"), b_years[y].get("total_return")
        ex = float(br) - float(dr) if dr is not None and br is not None else 0.0
        excesses.append(ex)
        year_rows.append({"year": int(y), "d": d_years[y], "b": b_years[y], "excess": ex})
    c3_ok = sharpe_wins >= 4

    total_ex = sum(excesses)
    max_contrib: float | None = None
    if total_ex <= 0:
        c4_ok = False
    else:
        contribs = [e / total_ex for e in excesses]
        max_contrib = max(contribs)
        c4_ok = max_contrib <= 0.60
        for row, c in zip(year_rows, contribs):
            row["excess_contribution"] = c

    return {
        "passed": bool(c1_ok and c2_ok and c3_ok and c4_ok),
        "c1": {"ok": c1_ok, "d_total_return": d_tr, "b_total_return": b_tr,
               "d_sharpe": d_sh, "b_sharpe": b_sh},
        "c2": {"ok": c2_ok, "d_max_drawdown": d_mdd, "b_max_drawdown": b_mdd,
               "limit": (float(d_mdd) - 0.02) if d_mdd is not None else None},
        "c3": {"ok": c3_ok, "sharpe_wins": sharpe_wins, "needed": 4, "years": len(years)},
        "c4": {"ok": c4_ok, "total_excess": total_ex, "max_contribution": max_contrib},
        "by_year": year_rows,
    }


def compare_bayes_vs_d(
    feats: Any,
    *,
    name_map: Mapping[str, str] | None = None,
    params: Any = None,
    top_k: int = 8,
    index_close: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Factory Final Board (D) vs Set B on one frame, one engine, one full-span replay.

    Years are slices of the same equity curve (plan §11.7 口径, no cold start).
    ``index_close`` only fills a report column; it never enters the criteria.
    """
    from ..lvrev_enhancement import year_slice_metrics
    from ..book_replay import ReplayParams
    from .backtest import run_shadow_book

    p = params or ReplayParams()
    d = run_shadow_book(feats, name_map=name_map, params=p, top_k=top_k)
    b = run_shadow_book(feats, name_map=name_map, params=p, top_k=top_k, bayes_sizing=True)
    d_years = year_slice_metrics(d["equityCurve"], d["trades"], initial_capital=p.initial_capital)
    b_years = year_slice_metrics(b["equityCurve"], b["trades"], initial_capital=p.initial_capital)
    years = sorted(set(d_years) & set(b_years), key=int)
    d_years = {y: d_years[y] for y in years}
    b_years = {y: b_years[y] for y in years}
    criteria = evaluate_bayes_criteria(d, b, d_years, b_years)

    bench: float | None = None
    if index_close and d["equityCurve"]:
        first = index_close.get(str(d["equityCurve"][0]["date"]))
        last = index_close.get(str(d["equityCurve"][-1]["date"]))
        if first and last:
            bench = float(last) / float(first) - 1.0

    def _arm_out(arm: Mapping[str, Any]) -> dict[str, Any]:
        tr = (arm["metrics"] or {}).get("total_return")
        return {
            "metrics": arm["metrics"],
            "tradeCount": len(arm.get("trades") or []),
            "excessReturn": (float(tr) - bench) if (tr is not None and bench is not None) else None,
            "shadow": arm.get("shadow"),
        }

    return {
        "ok": True,
        "start": d["equityCurve"][0]["date"] if d["equityCurve"] else None,
        "end": d["equityCurve"][-1]["date"] if d["equityCurve"] else None,
        "d": _arm_out(d),
        "b": _arm_out(b),
        "years": {"d": d_years, "b": b_years},
        "benchmarkReturn": bench,
        "criteria": criteria,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "excludedFromPerformance": True,
        "shadowOnly": True,
        "disclaimer": "Set B 离线对照（研究指标）；非投资建议；SIMULATE；不改出厂默认。",
        "limitations": [
            "name/industry 取 fundamentals 当前快照（非 PIT）",
            "S2 无历史 DI → 恒空池；S4/S5 已下线",
            "Set B 只改已入榜票的买入预算，不改榜单成员与顺序",
            "超额仅报告列，不进判定",
        ],
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


def render_bayes_markdown(payload: Mapping[str, Any]) -> str:
    """Markdown side-by-side report for the Set B comparison (JSON is the contract)."""
    if not payload.get("ok"):
        return "# Set B 贝叶斯先验仓位对照\n\n无可用数据\n"
    dm = (payload["d"].get("metrics") or {})
    bm = (payload["b"].get("metrics") or {})
    de = payload["d"].get("excessReturn")
    be = payload["b"].get("excessReturn")
    rows = [
        ("总收益", _pct(dm.get("total_return")), _pct(bm.get("total_return"))),
        ("年化", _pct(dm.get("cagr")), _pct(bm.get("cagr"))),
        ("超额（报告列，不进判定）",
         "不可用" if de is None else _pct(de), "不可用" if be is None else _pct(be)),
        ("最大回撤", _pct(dm.get("max_drawdown")), _pct(bm.get("max_drawdown"))),
        ("夏普", _num(dm.get("sharpe")), _num(bm.get("sharpe"))),
        ("胜率", _pct(dm.get("win_rate")), _pct(bm.get("win_rate"))),
        ("成交笔数", str(dm.get("n_trades")), str(bm.get("n_trades"))),
        ("平均持有日", _num(dm.get("avg_hold_days"), 1), _num(bm.get("avg_hold_days"), 1)),
    ]
    crit = payload.get("criteria") or {}
    c1, c2, c3, c4 = (crit.get(k) or {} for k in ("c1", "c2", "c3", "c4"))

    def _mark(c: Mapping[str, Any]) -> str:
        return "通过" if c.get("ok") else "**不通过**"

    lines = [
        "# Set B 贝叶斯先验仓位 vs D（同一引擎，离线对照）",
        "",
        f"- 区间：{payload.get('start')} ~ {payload.get('end')}",
        "- 口径：docs/plans/multi-strategy-final-board.md §11.9（事先登记，未改标准）",
        "- 先验：Beta(2,2)，R0=5%，滚动窗口 60 笔，仓位乘数 clip [0.5, 1.5]，PIT（exit_idx < 信号日）",
        "- 实验开关：默认关；出厂 D 不变，通过也不改默认",
        "",
        "| 指标 | D（现状） | Set B |",
        "|------|-----------|-------|",
        *[f"| {k} | {a} | {b} |" for k, a, b in rows],
        "",
        "## 分年（同一条全区间权益曲线切片）",
        "",
        "| 年份 | D 收益 | Set B 收益 | D 夏普 | Set B 夏普 | 年超额 |",
        "|------|--------|------------|--------|------------|--------|",
    ]
    for y in sorted(payload["years"]["d"], key=int):
        dy, by = payload["years"]["d"][y], payload["years"]["b"][y]
        ex = (float(by["total_return"]) - float(dy["total_return"])
              if by.get("total_return") is not None and dy.get("total_return") is not None else None)
        lines.append(
            f"| {y} | {_pct(dy.get('total_return'))} | {_pct(by.get('total_return'))} | "
            f"{_num(dy.get('sharpe'))} | {_num(by.get('sharpe'))} | "
            f"{'-' if ex is None else _pct(ex)} |"
        )
    lines += [
        "",
        "## 判定（四条全过才通过）",
        "",
        f"- C1 总收益与夏普均高于 D：{_mark(c1)}",
        f"- C2 最大回撤不深于 D 超过 2pp：{_mark(c2)}",
        f"- C3 六年中 ≥4 年 Set B 夏普 ≥ D：{_mark(c3)}（{c3.get('sharpe_wins')}/{c3.get('years')}）",
        f"- C4 年超额之和 > 0 且单年贡献 ≤ 60%：{_mark(c4)}"
        + (f"（最大单年贡献 {_pct(c4.get('max_contribution'))}）" if c4.get("max_contribution") is not None else ""),
        "",
        f"**总判：{'通过' if crit.get('passed') else '不通过'}**",
        "",
        "## 已知限制",
        "",
    ]
    lines += [f"- {x}" for x in payload.get("limitations") or []]
    lines += ["", f"> {payload.get('disclaimer')}", ""]
    return "\n".join(lines)


__all__ = [
    "MULT_HI",
    "MULT_LO",
    "PRIOR_ALPHA",
    "PRIOR_BETA",
    "PRIOR_R",
    "WINDOW",
    "bayes_school_mults",
    "compare_bayes_vs_d",
    "evaluate_bayes_criteria",
    "posterior_expected_return",
    "render_bayes_markdown",
    "slot_multiplier",
]
