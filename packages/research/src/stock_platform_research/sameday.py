"""当日战绩：**归档 brief 的真实选股** → 次日收盘的平均收益概览。

与 ``performance``（5 日持有闭环）互补：这里是 **1 日窗口**，回答「今天选的这批，
到收盘为止赚了多少」，也就是用户最直观的「当日平均收益」。

口径（与平台既有定义完全一致，见 ``brief_review._trading_closes_tplus``）::

    entry = asof 当根 K 线收盘（选股所用的收盘价）
    exit  = 紧随其后的第 1 个交易日收盘     （``holding="1d"``）
    raw   = exit / entry − 1
    alpha = raw − 基准（默认中证500 000905）在同一窗口的收益

数据源是 **归档 brief**（`daily_briefs`，即当日真正选出来的票），不是重算 ——
所以「当日选股」与盘前实际下发的榜单一致。缺后续行情 → ``pending``，不填 0。

SIMULATE only. Not investment advice.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable, Mapping, Sequence

from .brief_review import review_stored_brief, window_return
from .performance import format_pct, parse_holding_days, resolve_benchmark_symbol

GetDaily = Callable[..., list[dict[str, Any]]]

# 样本量阈值：低于此值只报趋势，不下结论（与 performance.MIN_MEANINGFUL_SAMPLE 对齐）。
MIN_MEANINGFUL_SAMPLE = 20


def _mean(values: Sequence[float]) -> float | None:
    """样本均值；空样本 → ``None``（不填 0，不假装有结论）。"""
    return sum(values) / len(values) if values else None


def _rate(values: Sequence[float]) -> float | None:
    """为正的比例；空样本 → ``None``。"""
    return (sum(1 for v in values if v > 0) / len(values)) if values else None


def summarize_sameday(
    records: Sequence[Mapping[str, Any]],
    *,
    get_daily: GetDaily,
    benchmark_get_daily: GetDaily | None = None,
    benchmark_symbol: str | None = None,
    with_benchmark: bool = True,
    holding: str = "1d",
) -> dict[str, Any]:
    """把若干归档 brief 按 ``holding`` 窗口结算，聚合成「当日战绩」payload。

    ``records`` 每项需含 ``asof`` 与 ``picks``（``BriefRecord.to_dict()`` 即满足）。
    ``benchmark_get_daily=None`` 表示**复用** ``get_daily`` 取基准；
    ``with_benchmark=False`` 则完全不算 alpha（``avgAlpha`` 为 ``None``）。
    """
    holding_days = parse_holding_days(holding) or 1
    bench_symbol = benchmark_symbol or resolve_benchmark_symbol()
    bench_source: GetDaily | None = None
    if with_benchmark:
        bench_source = benchmark_get_daily if benchmark_get_daily is not None else get_daily

    days: list[dict[str, Any]] = []
    all_raws: list[float] = []
    all_alphas: list[float] = []
    settled_total = 0
    pending_total = 0
    pick_total = 0

    for record in records:
        asof = str(record.get("asof") or "")[:10]
        if not asof:
            continue
        try:
            review = review_stored_brief(record, get_daily=get_daily, holding=holding)
        except Exception as exc:  # noqa: BLE001 — 单日失败不拖垮整表
            days.append({"asof": asof, "error": f"{type(exc).__name__}"})
            continue

        raws: list[float] = []
        for row in review.get("rows") or []:
            if row.get("pending"):
                continue
            value = row.get("rawReturnFloat")
            if isinstance(value, (int, float)):
                raws.append(float(value))

        bench_raw: float | None = None
        if bench_source is not None:
            try:
                end = _parse(asof) + timedelta(days=max(holding_days * 4, 20))
                bars = list(bench_source([bench_symbol], start=_parse(asof), end=end) or [])
                bench_raw = window_return(bars, start=_parse(asof), holding_days=holding_days)
            except Exception:  # noqa: BLE001 — 基准缺失 → alpha 置空
                bench_raw = None
        alphas = [r - bench_raw for r in raws] if bench_raw is not None else []

        settled = int(review.get("settledCount") or 0)
        pending = int(review.get("pendingCount") or 0)
        settled_total += settled
        pending_total += pending
        pick_total += int(review.get("pickCount") or 0)
        all_raws.extend(raws)
        all_alphas.extend(alphas)

        days.append(
            {
                "asof": asof,
                "pickCount": int(review.get("pickCount") or 0),
                "settledCount": settled,
                "pendingCount": pending,
                "avgRawReturn": _mean(raws),
                "upRate": _rate(raws),
                "best": max(raws) if raws else None,
                "worst": min(raws) if raws else None,
                "benchmarkRawReturn": bench_raw,
                "avgAlpha": _mean(alphas),
                "beatBenchmarkRate": _rate(alphas),
            }
        )

    sample = settled_total
    return {
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "holding": f"{holding_days}d",
        "benchmarkSymbol": bench_symbol,
        "asofFirst": days[0]["asof"] if days else None,
        "asofLast": days[-1]["asof"] if days else None,
        "dayCount": len(days),
        "pickCount": pick_total,
        "settledCount": settled_total,
        "pendingCount": pending_total,
        "sampleCount": sample,
        "avgRawReturn": _mean(all_raws),
        "upRate": _rate(all_raws),
        "best": max(all_raws) if all_raws else None,
        "worst": min(all_raws) if all_raws else None,
        "avgAlpha": _mean(all_alphas),
        "beatBenchmarkRate": _rate(all_alphas),
        "benchmarkSampleCount": len(all_alphas),
        "sampleNote": (
            f"sample_size={sample} < {MIN_MEANINGFUL_SAMPLE}; "
            "ratios are noisy — do not over-interpret"
            if sample < MIN_MEANINGFUL_SAMPLE
            else None
        ),
        "days": days,
        "disclaimer": (
            "研究指标；entry=asof 收盘、exit=下一交易日收盘（holding=1d）；"
            "重叠窗口、不含成本；非投资建议。"
        ),
    }


def _parse(value: str):
    from datetime import date

    return date.fromisoformat(value[:10])


def _pct(value: Any) -> str:
    return format_pct(float(value)) if isinstance(value, (int, float)) else "—"


def _rate_pct(value: Any) -> str:
    """比率百分比：**不带**正号（``25.00%``，不是 ``+25.00%``）。"""
    return f"{float(value) * 100.0:.2f}%" if isinstance(value, (int, float)) else "—"


def render_sameday_markdown(payload: Mapping[str, Any]) -> str:
    """人读版「当日战绩」（结论先行、表格分层）。"""
    holding = payload.get("holding")
    lines = [
        f"# 当日战绩（选股 → 次日收盘 · {holding}）",
        "",
        f"- 区间：`{payload.get('asofFirst')}` → `{payload.get('asofLast')}`"
        f"（{payload.get('dayCount')} 个交易日）",
        "- 环境：SIMULATE（`liveTradingEnabled=false`）",
        "- 口径：`entry` = asof 当日收盘，`exit` = 紧随其后的第 1 个交易日收盘；"
        f"`alpha` = raw − 基准（`{payload.get('benchmarkSymbol')}`）同窗口",
        "- 数据源：归档 brief（当日实际下发的榜单）",
        "",
        "## 汇总",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 选股数（累计） | {payload.get('pickCount')} |",
        f"| 已结算样本 | **{payload.get('settledCount')}** |",
        f"| 待结算（行情未到） | {payload.get('pendingCount')} |",
        f"| 平均收益 avgReturn | **{_pct(payload.get('avgRawReturn'))}** |",
        f"| 胜率 upRate | {_rate_pct(payload.get('upRate'))} |",
        f"| avgAlpha | {_pct(payload.get('avgAlpha'))} |",
        f"| 跑赢基准率 | {_rate_pct(payload.get('beatBenchmarkRate'))} |",
        f"| 最好 / 最差 | **{_pct(payload.get('best'))}** / **{_pct(payload.get('worst'))}** |",
        "",
    ]
    if payload.get("sampleNote"):
        lines.append(f"> ⚠️ {payload['sampleNote']}")
        lines.append("")

    lines += [
        "## 分日明细",
        "",
        "| asof | 选股 | 已结算 | 待结算 | 平均收益 | 胜率 | avgAlpha | 跑赢率 | 最好 | 最差 | 基准 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for day in payload.get("days") or []:
        if day.get("error"):
            lines.append(f"| {day.get('asof')} | — | — | — | 结算失败（{day['error']}） | — | — | — | — | — | — |")
            continue
        lines.append(
            "| {d} | {p} | {s} | {q} | {avg} | {up} | {a} | {b} | {best} | {worst} | {bench} |".format(
                d=day.get("asof"),
                p=day.get("pickCount"),
                s=day.get("settledCount"),
                q=day.get("pendingCount"),
                avg=_pct(day.get("avgRawReturn")),
                up=_rate_pct(day.get("upRate")),
                a=_pct(day.get("avgAlpha")),
                b=_rate_pct(day.get("beatBenchmarkRate")),
                best=_pct(day.get("best")),
                worst=_pct(day.get("worst")),
                bench=_pct(day.get("benchmarkRawReturn")),
            )
        )
    lines += [
        "",
        "> 说明：**当日战绩 ≠ 命中追踪**；命中追踪只统计重复被选中的次数。",
        "> 样本不足时只看趋势、不看结论。",
        "",
    ]
    return "\n".join(lines) + "\n"


__all__ = [
    "MIN_MEANINGFUL_SAMPLE",
    "render_sameday_markdown",
    "summarize_sameday",
]
