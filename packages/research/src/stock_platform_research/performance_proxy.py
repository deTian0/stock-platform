"""绩效代理台账（Performance Proxy Ledger）——里程碑 ``R4``。

为什么存在
----------
真实台账 ``data/recommend_decisions.jsonl`` 是**实时**决策记录：每个交易日最多 N 条 brief
TopN，且必须等持有窗口（默认 ``5d``）走完才能结算。样本增长被日历硬约束——真机长期只有
个位数 settled，恰好落进 :data:`performance.MIN_MEANINGFUL_SAMPLE` (20) 的**噪音区**，
于是「这套选股逻辑到底赚不赚钱」这个问题一直**没有可读的样本量**。

本模块把**回测引擎自己的成交**（:func:`book_replay.replay_book` 出来的 ``trades``）转成与
真实台账**逐字段同形状**的决策行，形成「**代理台账**」。一个 ≥1 年的长窗回测即可产出
几十上百条 settled 样本，把该问题第一次抬到门槛之上。

代理 ≠ 真实（口径刻意不同，故**禁止混算**）
------------------------------------------
========================  ==========================  ==============================
维度                      真实台账                    代理台账
========================  ==========================  ==============================
信号源                    brief 的 ``asof``（实时）    回测建仓日（历史回放）
出场                      T+N 固定持有（默认 ``5d``）  引擎退出规则（止损/止盈/趋势/最长持有）
收益口径                  ``raw`` 裸收益（**不含成本**） ``net_ret`` 扣费净收益（**含成本**）
窗口关系                  决策间**重叠**               单账户序列（仓位上限 + 现金约束）
========================  ==========================  ==============================

因此 :func:`build_proxy_view` **只做并排呈现**（各自打 ``ledgerKind`` 标签）、
**绝不产出任何合计字段**——两者相加 / 取平均 / 相减都会产生无意义数字。
代理行一律带 ``source="backtest_proxy"``，从数据层面杜绝被误当真实决策。

只读、零网络、fail-closed（缺件标注而非编造）；不写库；SIMULATE。非投资建议。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .performance import (
    MIN_MEANINGFUL_SAMPLE,
    format_pct,
    load_jsonl,
    performance_summary,
    rewrite_jsonl,
)

# 代理行的 ``source`` 标记：读到它就知道这不是真实决策。
PROXY_SOURCE = "backtest_proxy"

PROXY_LEDGER_FILENAME = "performance_proxy.jsonl"
ENV_PROXY_LOG = "STOCK_PLATFORM_PERFORMANCE_PROXY_LOG"
DEFAULT_PROXY_OUT_DIR = "data/performance"

# ``build_proxy_view`` 的固定不可比说明（也写进契约 docs/contracts/performance-proxy.md）。
COMPARABILITY_NOTE = (
    "真实台账与代理台账口径**刻意不同**（信号源 / 出场规则 / 成本 / 窗口），"
    "任何合计、平均或相减都会产生无意义数字——两者只能并排陈列，禁止混算。"
)

# 两侧各自的口径自述（进 payload，供 UI / 报告直接展示）。
REAL_SCALE = {
    "ledgerKind": "real",
    "signalSource": "brief.asof（实时盘前简报 TopN）",
    "exit": "T+N 固定持有（默认 5d）",
    "returnBasis": "裸收益 raw（不含成本）",
    "windows": "决策间重叠（非组合曲线）",
}
PROXY_SCALE = {
    "ledgerKind": "proxy",
    "signalSource": "回测建仓日（历史回放）",
    "exit": "引擎退出规则（止损/止盈/趋势/最长持有）",
    "returnBasis": "扣费净收益 net_ret（含佣金/印花税/滑点）",
    "windows": "单账户序列（仓位上限 + 现金约束）",
}


def _as_float(value: Any) -> float | None:
    """NaN-safe float coercion (``None`` for missing / non-numeric / NaN)."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out


def default_proxy_log_path() -> Path:
    """代理台账默认路径：环境变量覆盖，否则 ``./data/performance_proxy.jsonl``。"""
    import os

    env = str(os.environ.get(ENV_PROXY_LOG) or "").strip()
    if env:
        return Path(env)
    return Path.cwd() / "data" / PROXY_LEDGER_FILENAME


def trades_to_decision_rows(
    trades: Sequence[Mapping[str, Any]] | None,
    *,
    equity_curve: Sequence[Mapping[str, Any]] | None = None,
    source: str = PROXY_SOURCE,
    rating: str = "Buy",
    use_net: bool = True,
) -> list[dict[str, Any]]:
    """把回测成交转成与真实台账**同形状**的决策行（全部 ``pending=False``）。

    ``date`` 取建仓日（``equity_curve[entry_idx].date``），``symbol`` = ``code``，
    ``raw`` = 扣费净收益（``net_ret``，百分数 → ``"+x.xx%"``）。``alpha`` 恒为 ``None``
    ——代理侧没有同窗口基准超额，**不编造**。

    额外保留的 provenance 键（``exitReason`` / ``exitDate`` / ``grossRetPct`` /
    ``netRetPct`` / ``assetClass`` / ``ledgerKind``）不影响既有读取器
    （:func:`performance.settled_records` 只读它认识的键），只用于审计与展示。
    """
    dates = [str(p.get("date") or "")[:10] for p in (equity_curve or [])]
    rows: list[dict[str, Any]] = []
    for t in trades or []:
        if not isinstance(t, Mapping):
            continue
        code = str(t.get("code") or "").strip()
        if not code:
            continue
        ret_pct = _as_float(t.get("net_ret") if use_net else t.get("gross_ret"))
        if ret_pct is None:
            continue
        idx = t.get("entry_idx")
        signal_date = ""
        if isinstance(idx, int) and 0 <= idx < len(dates):
            signal_date = dates[idx]
        held = _as_float(t.get("held_days"))
        rows.append(
            {
                "date": signal_date,
                "symbol": code,
                "rating": rating,
                "raw": format_pct(ret_pct / 100.0),
                "alpha": None,
                "holding": f"{int(held)}d" if held is not None else None,
                "pending": False,
                "source": source,
                "ledgerKind": "proxy",
                "exitDate": str(t.get("exit_date") or "")[:10] or None,
                "exitReason": t.get("reason"),
                "grossRetPct": _as_float(t.get("gross_ret")),
                "netRetPct": _as_float(t.get("net_ret")),
                "assetClass": t.get("asset_class"),
            }
        )
    return rows


def write_proxy_ledger(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> Path:
    """把代理台账整表写入 ``path``（**覆盖**，非追加）。

    代理台账是「一次回测的完整派生」，每次运行都从零重算，故用覆盖写保证幂等
    （追加会让同一窗口的样本重复计数）。
    """
    return rewrite_jsonl(path, rows)


def load_proxy_ledger(path: str | Path) -> list[dict[str, Any]]:
    """读取代理台账（JSONL）。缺失文件返回空表（fail-closed，不抛）。"""
    return load_jsonl(path)


def build_proxy_view(
    *,
    real_path: str | Path | None = None,
    proxy_path: str | Path | None = None,
    real_entries: Sequence[Mapping[str, Any]] | None = None,
    proxy_entries: Sequence[Mapping[str, Any]] | None = None,
    proxy_meta: Mapping[str, Any] | None = None,
    recent_days: int = 5,
    threshold: int = MIN_MEANINGFUL_SAMPLE,
) -> dict[str, Any]:
    """真实台账 vs 代理台账**并排视图**（口径复用 :func:`performance.performance_summary`）。

    两侧**共用同一套汇总算术**（``performance_summary`` → ``compute_performance``），
    但**分别**汇总、**分别**标注 ``ledgerKind``——视图里不存在任何跨侧合并字段。
    """
    real_stats = performance_summary(
        real_path if real_entries is None else None,
        entries=real_entries,
        recent_days=recent_days,
    )
    real_stats["ledgerKind"] = "real"
    real_stats["ledgerPath"] = str(real_path) if real_path else None
    real_stats["scale"] = REAL_SCALE

    proxy_stats = performance_summary(
        proxy_path if proxy_entries is None else None,
        entries=proxy_entries,
        recent_days=recent_days,
    )
    proxy_stats["ledgerKind"] = "proxy"
    proxy_stats["ledgerPath"] = str(proxy_path) if proxy_path else None
    proxy_stats["scale"] = PROXY_SCALE
    if proxy_meta:
        proxy_stats["provenance"] = dict(proxy_meta)

    real_settled = int(real_stats.get("settledCount") or 0)
    proxy_settled = int(proxy_stats.get("settledCount") or 0)
    note_bits: list[str] = []
    if real_settled < threshold:
        note_bits.append(f"真实 settled={real_settled} < {threshold}（噪音区，勿过度解读）")
    if proxy_settled < threshold:
        note_bits.append(f"代理 settled={proxy_settled} < {threshold}（长窗仍不足）")
    if not note_bits:
        note_bits.append(f"两侧 settled 均 ≥ {threshold}")

    return {
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "ledgerKind": "proxy_vs_real",
        "threshold": int(threshold),
        "real": real_stats,
        "proxy": proxy_stats,
        "sampleAdequacy": {
            "realSettled": real_settled,
            "proxySettled": proxy_settled,
            "threshold": int(threshold),
            "realAdequate": real_settled >= threshold,
            "proxyAdequate": proxy_settled >= threshold,
            "note": "；".join(note_bits),
        },
        "comparability": {
            "combinable": False,
            "reason": COMPARABILITY_NOTE,
            "realScale": REAL_SCALE,
            "proxyScale": PROXY_SCALE,
            "singlePoint": "performance.performance_summary",
            "sharedArithmetic": ["performance.performance_summary", "performance.compute_performance"],
        },
        "disclaimer": (
            "研究口径、SIMULATE；真实与代理台账口径不同、禁止混算；非投资建议。"
        ),
    }


def _fmt(value: Any, *, pct: bool = False, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        if pct:
            return format_pct(float(value))
        return f"{float(value):.{digits}f}"
    return str(value)


def _metrics_table(stats: Mapping[str, Any]) -> str:
    m = stats.get("metrics") or {}
    a = stats.get("attribution") or {}
    lines = [
        "| 指标 | 值 |",
        "|---|---|",
        f"| 台账条目 totalEntries | {_fmt(stats.get('totalEntries'), digits=0)} |",
        f"| 已结算 settled | {_fmt(stats.get('settledCount'), digits=0)} |",
        f"| 未结算 pending | {_fmt(stats.get('pendingCount'), digits=0)} |",
        f"| 平均持有（天） | {_fmt(stats.get('avgHoldingDays'), digits=1)} |",
        f"| 胜率 winRate（raw>0） | {_fmt(a.get('winRate'))} |",
        f"| 平均收益 avgReturn | {_fmt(m.get('avg_return'), pct=True)} |",
        f"| 中位收益 medianReturn | {_fmt(m.get('median_return'), pct=True)} |",
        f"| 超额均值 avgAlpha | {_fmt(m.get('avg_alpha'), pct=True)} |",
        f"| 跑赢基准率 beatBenchmarkRate | {_fmt(a.get('beatBenchmarkRate'))} |",
        f"| 方向准确率 directionAccuracy | {_fmt(m.get('direction_accuracy'))} |",
        f"| 最佳 best | {_fmt(m.get('best'), pct=True)} |",
        f"| 最差 worst | {_fmt(m.get('worst'), pct=True)} |",
    ]
    return "\n".join(lines)


def render_proxy_markdown(view: Mapping[str, Any]) -> str:
    """把 :func:`build_proxy_view` 的视图渲染成 Markdown（分栏 + 口径差异表）。"""
    real = view.get("real") or {}
    proxy = view.get("proxy") or {}
    adeq = view.get("sampleAdequacy") or {}
    thr = int(view.get("threshold") or MIN_MEANINGFUL_SAMPLE)

    def _mark(ok: Any) -> str:
        return "✅" if ok else "❌"

    out: list[str] = []
    out.append("# 绩效代理台账（代理 vs 真实）\n")
    out.append(
        "> **代理与真实台账分栏陈列、禁止混算。** 真实 = 实时 brief 决策"
        "（T+N 固定持有、不含成本）；代理 = 长窗回测成交（引擎退出规则、扣费净收益）。\n"
    )
    out.append(f"- 生成时间：`{view.get('generatedAt')}`")
    out.append(f"- 样本门槛 `MIN_MEANINGFUL_SAMPLE` = **{thr}**")
    out.append(f"- 环境：`{view.get('environment')}` · liveTradingEnabled=`{view.get('liveTradingEnabled')}`\n")

    out.append("## 一、样本充分性\n")
    out.append("| 台账 | settled | 门槛 | 达标 |")
    out.append("|---|---|---|---|")
    out.append(
        f"| 真实（real） | {adeq.get('realSettled')} | {thr} | {_mark(adeq.get('realAdequate'))} |"
    )
    out.append(
        f"| 代理（proxy） | {adeq.get('proxySettled')} | {thr} | {_mark(adeq.get('proxyAdequate'))} |\n"
    )
    out.append(f"> {adeq.get('note')}\n")

    out.append("## 二、真实台账（实时 brief · T+N 固定持有 · 不含成本）\n")
    out.append(f"路径：`{real.get('ledgerPath')}`\n")
    out.append(_metrics_table(real) + "\n")

    out.append("## 三、代理台账（长窗回测 · 引擎退出 · 扣费净收益）\n")
    out.append(f"路径：`{proxy.get('ledgerPath')}`\n")
    prov = proxy.get("provenance") or {}
    if prov:
        bits = " · ".join(f"{k}=`{v}`" for k, v in prov.items() if v is not None)
        if bits:
            out.append(f"回测来源：{bits}\n")
    out.append(_metrics_table(proxy) + "\n")

    out.append("## 四、口径差异（为何禁止混算）\n")
    out.append("| 维度 | 真实（real） | 代理（proxy） |")
    out.append("|---|---|---|")
    rs = real.get("scale") or REAL_SCALE
    ps = proxy.get("scale") or PROXY_SCALE
    for key, label in (
        ("signalSource", "信号源"),
        ("exit", "出场"),
        ("returnBasis", "收益口径"),
        ("windows", "窗口关系"),
    ):
        out.append(f"| {label} | {rs.get(key, '—')} | {ps.get(key, '—')} |")
    out.append("")
    out.append(f"> {(view.get('comparability') or {}).get('reason')}\n")

    out.append("## 五、免责\n")
    out.append(str(view.get("disclaimer") or ""))
    out.append("")
    return "\n".join(out)


__all__ = [
    "COMPARABILITY_NOTE",
    "DEFAULT_PROXY_OUT_DIR",
    "ENV_PROXY_LOG",
    "PROXY_LEDGER_FILENAME",
    "PROXY_SCALE",
    "PROXY_SOURCE",
    "REAL_SCALE",
    "build_proxy_view",
    "default_proxy_log_path",
    "load_proxy_ledger",
    "render_proxy_markdown",
    "trades_to_decision_rows",
    "write_proxy_ledger",
]
