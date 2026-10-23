"""盘后当日行情台账：开 / 收 / 涨跌 + **量化归因**。

回答四个问题（按 asof 当日单根 K 线）::

    open / high / low / close   当日四价
    pct                         close / prev_close − 1      （涨跌情况）
    gap                         open  / prev_close − 1      （缺口/情绪起点）
    intraday                    close / open − 1            （日内多空）
    amplitude                   (high − low) / prev_close   （波动）
    volRatio                    vol / 前 20 日均量           （量能）
    vsMa20                      close / ma20 − 1            （位置）
    dayAlpha                    pct − 基准当日 pct          （相对大盘）

**「涨跌原因」的口径是量化归因，不是消息面归因**：本平台没有新闻/公告/龙虎榜
数据源，任何「因为某消息」的说法都是编造。这里只把「分时形态 + 量能 + 相对大盘 +
均线位置」四轴拼成一句可复算的解释，并显式标注 ``attributionKind="quantitative"``。

数据口径两条硬约束：

1. **涨跌幅一律由 ``close`` 序列自算**，不读 ``daily_price.pct_chg``。该列在引擎
   库里是混合尺度（股票多为小数、ETF 多为百分点，见 :mod:`pct_scale`），
   自算 close/prev−1 天然跨资产一致，也让 gap / intraday / amplitude 共用同一分母。
2. **开/高/低不在引擎库里**（``daily_price`` 只有 close/pct_chg/vol/amount）。
   缺失时该列输出 ``—``、归因降级为「量能 + 相对大盘 + 位置」，绝不补零、绝不猜。

SIMULATE only. Not investment advice.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Sequence

# 量能分档（vol / 前 20 日均量）
VOL_HEAVY = 1.5
VOL_LIGHT = 0.7

# 归因阈值（百分点）
GAP_MATERIAL = 0.8  # |gap| >= 0.8% 才算有意义的缺口
INTRADAY_MATERIAL = 0.8
BAND_FLAT = 0.5  # |pct| < 0.5% 视为窄幅
ALPHA_MATERIAL = 1.0  # |dayAlpha| >= 1.0pct 才算强/弱于大盘

MA_WINDOW = 20
VOL_WINDOW = 20

# 四价来源标记
OHLC_PROVIDER = "provider"
OHLC_CACHE = "cache"
OHLC_MISSING = "missing"

ATTRIBUTION_KIND = "quantitative"

__all__ = [
    "ATTRIBUTION_KIND",
    "OHLC_CACHE",
    "OHLC_MISSING",
    "OHLC_PROVIDER",
    "build_day_quote",
    "classify_row",
    "explain_row",
    "render_day_quote_markdown",
]


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def _num(value: Any) -> float | None:
    """容错转 float；``None``/``""``/非数值 → ``None``（不补零）。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None  # 剔 NaN


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _ratio(num: float | None, den: float | None) -> float | None:
    """``num / den − 1``；任一侧缺失或分母为 0 → ``None``。"""
    if num is None or den is None or den == 0:
        return None
    return num / den - 1.0


def _pct_text(value: Any, *, digits: int = 2, sign: bool = True) -> str:
    num = _num(value)
    if num is None:
        return "—"
    return f"{num * 100.0:+.{digits}f}%" if sign else f"{num * 100.0:.{digits}f}%"


def _price_text(value: Any) -> str:
    num = _num(value)
    return "—" if num is None else f"{num:.2f}"


def _vol_of(bar: Mapping[str, Any]) -> float | None:
    """成交量：provider 归一化后是 ``volume``，引擎库原始列名是 ``vol``，两者都认。"""
    for key in ("volume", "vol"):
        value = _num(bar.get(key))
        if value is not None:
            return value
    return None


# --------------------------------------------------------------------------- #
# 单标的四价 + 派生指标
# --------------------------------------------------------------------------- #
def _quote_row(
    target: Mapping[str, Any],
    bars: Sequence[Mapping[str, Any]],
    *,
    asof: str,
    bench_pct: float | None,
    ohlc: Mapping[str, Any] | None,
    ohlc_source: str,
) -> dict[str, Any]:
    """把一只标的的日线序列压成台账一行。``bars`` 需按日期升序。"""
    history = [b for b in bars if str(b.get("date") or "")[:10] <= asof]
    history.sort(key=lambda b: str(b.get("date") or ""))

    row: dict[str, Any] = {
        "bucket": str(target.get("bucket") or ""),
        "symbol": str(target.get("symbol") or ""),
        "name": str(target.get("name") or ""),
        "prevClose": None,
        "open": None,
        "high": None,
        "low": None,
        "close": None,
        "pct": None,
        "gap": None,
        "intraday": None,
        "amplitude": None,
        "volRatio": None,
        "ma20": None,
        "vsMa20": None,
        "dayAlpha": None,
        "barDate": None,
        "staleBars": 0,
        "ohlcSource": OHLC_MISSING,
        "tags": [],
        "reason": "无当日行情（停牌/未入库），不计涨跌",
    }
    if not history:
        return row

    last = history[-1]
    last_date = str(last.get("date") or "")[:10]
    row["barDate"] = last_date
    close = _num(last.get("close"))
    row["close"] = close

    # 缺口/前收盘：只认「紧邻的上一根」，跨多日则把天数标出来（停牌不伪装成单日）
    prior = None
    if len(history) >= 2:
        prior = history[-2]
    if prior is not None:
        row["prevClose"] = _num(prior.get("close"))
    prev_close = row["prevClose"]
    row["pct"] = _ratio(close, prev_close)
    if last_date != asof:
        row["staleBars"] = 1  # 当日无 K 线（停牌/数据未到）
    # 量能：当日 vol / 前 20 日均量（**不含**当日，避免自己摊薄自己）
    vol = _vol_of(last)
    prior_vols = [_vol_of(b) for b in history[-(VOL_WINDOW + 1):-1]]
    vols = [v for v in prior_vols if v is not None and v > 0]
    if vol is not None and vols:
        base = _mean(vols)
        row["volRatio"] = (vol / base) if base else None

    # 位置：收盘 vs 20 日均线
    closes = [c for c in (_num(b.get("close")) for b in history[-MA_WINDOW:]) if c is not None]
    if len(closes) >= MA_WINDOW:
        ma20 = _mean(closes)
        row["ma20"] = ma20
        row["vsMa20"] = _ratio(close, ma20)

    # 四价：优先当日 OHLC 源；缺失时只有 close 可用
    if ohlc is not None:
        o = _num(ohlc.get("open"))
        h = _num(ohlc.get("high"))
        lo = _num(ohlc.get("low"))
        if o is not None:
            row["open"] = o
            row["ohlcSource"] = ohlc_source
        if h is not None:
            row["high"] = h
        if lo is not None:
            row["low"] = lo
        oc = _num(ohlc.get("close"))
        if oc is not None and close is None:
            row["close"] = oc
            close = oc
            row["pct"] = _ratio(close, prev_close)

    if row["open"] is not None and row["ohlcSource"] != OHLC_MISSING:
        row["gap"] = _ratio(row["open"], prev_close)
        row["intraday"] = _ratio(close, row["open"])
        if row["high"] is not None and row["low"] is not None and prev_close:
            row["amplitude"] = (row["high"] - row["low"]) / prev_close

    # 相对大盘：只对非基准行有意义
    if bench_pct is not None and row["pct"] is not None and row["bucket"] != "benchmark":
        row["dayAlpha"] = row["pct"] - bench_pct

    row["tags"] = (["当日无K线"] if row["staleBars"] else []) + classify_row(row)
    row["reason"] = explain_row(row)
    return row


# --------------------------------------------------------------------------- #
# 归因：四轴 → 标签 → 一句人话
# --------------------------------------------------------------------------- #
def classify_row(row: Mapping[str, Any]) -> list[str]:
    """四轴归因标签。顺序固定：形态 → 量价 → 相对大盘 → 位置。"""
    tags: list[str] = []
    pct = _num(row.get("pct"))
    gap = _num(row.get("gap"))
    intra = _num(row.get("intraday"))
    high = _num(row.get("high"))
    low = _num(row.get("low"))
    close = _num(row.get("close"))
    prev = _num(row.get("prevClose"))
    vr = _num(row.get("volRatio"))
    alpha = _num(row.get("dayAlpha"))
    vs_ma = _num(row.get("vsMa20"))

    # 1) 分时形态（需要 open；有 high/low 才能判冲高回落 / 探底回升）
    shape = ""
    if gap is not None and intra is not None:
        if gap >= GAP_MATERIAL / 100 and intra <= -INTRADAY_MATERIAL / 100:
            shape = "高开低走"
        elif gap <= -GAP_MATERIAL / 100 and intra >= INTRADAY_MATERIAL / 100:
            shape = "低开高走"
    if not shape and high is not None and low is not None and close is not None and prev:
        span = high - low
        if span > 0:
            pos = (close - low) / span  # 收盘在全天区间的位置
            up_wick = (high - max(close, prev)) / prev
            dn_wick = (min(close, prev) - low) / prev
            if up_wick >= 0.01 and pos <= 0.35:
                shape = "冲高回落"
            elif dn_wick >= 0.01 and pos >= 0.65:
                shape = "探底回升"
    if not shape and pct is not None:
        if abs(pct) * 100 < BAND_FLAT:
            shape = "窄幅整理"
        elif pct > 0:
            shape = "单边走强"
        else:
            shape = "单边走弱"
    if shape:
        tags.append(shape)

    # 2) 量价配合
    if vr is not None:
        heavy = vr >= VOL_HEAVY
        light = vr <= VOL_LIGHT
        if heavy and pct is not None:
            tags.append("放量上涨" if pct > 0 else "放量下跌" if pct < 0 else "放量滞涨")
        elif light and pct is not None:
            tags.append("缩量上涨" if pct > 0 else "缩量下跌" if pct < 0 else "缩量整理")
        elif heavy:
            tags.append("放量")
        elif light:
            tags.append("缩量")
        else:
            tags.append("量能常态")

    # 3) 相对大盘
    if alpha is not None:
        if alpha * 100 >= ALPHA_MATERIAL:
            tags.append("强于基准")
        elif alpha * 100 <= -ALPHA_MATERIAL:
            tags.append("弱于基准")
        else:
            tags.append("随基准")

    # 4) 位置
    if vs_ma is not None:
        tags.append("站上20日线" if vs_ma >= 0 else "20日线下方")

    return tags


def explain_row(row: Mapping[str, Any]) -> str:
    """把标签拼成一句可读原因（量化归因，不含消息面）。"""
    if row.get("close") is None:
        return "无当日行情（停牌/未入库），不计涨跌"
    parts: list[str] = []
    pct = _num(row.get("pct"))
    gap = _num(row.get("gap"))
    intra = _num(row.get("intraday"))
    vr = _num(row.get("volRatio"))
    alpha = _num(row.get("dayAlpha"))
    tags = list(row.get("tags") or [])

    if pct is None:
        parts.append("无前收盘，涨跌幅不可算")
    else:
        verb = "上涨" if pct > 0 else "下跌" if pct < 0 else "平盘"
        parts.append(f"{verb} {abs(pct) * 100:.2f}%")

    if gap is not None and intra is not None:
        parts.append(f"（开盘 {_pct_text(gap)} → 日内 {_pct_text(intra)}）")
    elif row.get("open") is None:
        parts.append("（开/高/低缺失，仅按收盘口径）")

    shape = [t for t in tags if t in {"高开低走", "低开高走", "冲高回落", "探底回升", "窄幅整理", "单边走强", "单边走弱"}]
    if shape:
        parts.append("形态：" + shape[0])

    if vr is not None:
        parts.append(f"量能 {vr:.2f}×20日均量")

    if alpha is not None:
        parts.append(f"相对基准 {alpha * 100:+.2f}pct")

    vs_ma = _num(row.get("vsMa20"))
    if vs_ma is not None:
        parts.append(f"位置 {_pct_text(vs_ma)} vs MA20")

    # 结论从句：把「量价 + 相对」合成驱动判断
    driver = ""
    if pct is not None and vr is not None:
        if pct > 0 and vr >= VOL_HEAVY:
            driver = "放量上行，买盘主动"
        elif pct > 0 and vr <= VOL_LIGHT:
            driver = "缩量上行，抛压不重但承接有限"
        elif pct < 0 and vr >= VOL_HEAVY:
            driver = "放量下行，抛压主导"
        elif pct < 0 and vr <= VOL_LIGHT:
            driver = "缩量下行，杀跌意愿不强"
    if not driver and alpha is not None:
        if alpha * 100 >= ALPHA_MATERIAL:
            driver = "跑赢基准，独立于大盘"
        elif alpha * 100 <= -ALPHA_MATERIAL:
            driver = "跑输基准，弱于大盘"
    text = "；".join(parts)
    return f"{text} ⇒ {driver}" if driver else text


# --------------------------------------------------------------------------- #
# 汇总
# --------------------------------------------------------------------------- #
def _summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    live = [r for r in rows if _num(r.get("pct")) is not None and r.get("bucket") != "benchmark"]
    pcts = [float(r["pct"]) for r in live]
    up = [r for r in live if float(r["pct"]) > 0]
    down = [r for r in live if float(r["pct"]) < 0]
    flat = [r for r in live if float(r["pct"]) == 0]
    tag_counts: dict[str, int] = {}
    for r in live:
        for t in r.get("tags") or []:
            tag_counts[t] = tag_counts.get(t, 0) + 1
    best = max(live, key=lambda r: float(r["pct"])) if live else None
    worst = min(live, key=lambda r: float(r["pct"])) if live else None
    return {
        "counted": len(live),
        "upCount": len(up),
        "downCount": len(down),
        "flatCount": len(flat),
        "avgPct": _mean(pcts),
        "medianPct": (sorted(pcts)[len(pcts) // 2] if pcts else None),
        "best": {"symbol": best.get("symbol"), "name": best.get("name"), "pct": best.get("pct")} if best else None,
        "worst": {"symbol": worst.get("symbol"), "name": worst.get("name"), "pct": worst.get("pct")} if worst else None,
        "tagCounts": dict(sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "missingOhlc": sum(1 for r in live if r.get("ohlcSource") == OHLC_MISSING),
    }


def build_day_quote(
    targets: Iterable[Mapping[str, Any]],
    *,
    asof: str,
    bars_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    benchmark_symbol: str,
    benchmark_bars: Sequence[Mapping[str, Any]] = (),
    ohlc_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
    ohlc_sources: Mapping[str, str] | None = None,
    ohlc_status: Mapping[str, Any] | None = None,
    benchmark_name: str | None = None,
    benchmark_warning: str | None = None,
) -> dict[str, Any]:
    """组装当日行情台账 payload。

    ``targets`` 每项需 ``symbol`` + ``name`` + ``bucket``（``pick`` / ``holding``）。
    基准由 ``benchmark_symbol`` 单独算，不进涨跌家数统计。
    """
    ohlc_map = dict(ohlc_by_symbol or {})
    src_map = dict(ohlc_sources or {})

    bench_row = _quote_row(
        {"symbol": benchmark_symbol, "name": benchmark_name or f"基准 {benchmark_symbol}", "bucket": "benchmark"},
        benchmark_bars,
        asof=asof,
        bench_pct=None,
        ohlc=ohlc_map.get(benchmark_symbol),
        ohlc_source=src_map.get(benchmark_symbol, OHLC_MISSING),
    )
    bench_pct = _num(bench_row.get("pct"))

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for target in targets:
        symbol = str(target.get("symbol") or "").strip()
        bucket = str(target.get("bucket") or "")
        if not symbol or (symbol, bucket) in seen:
            continue
        seen.add((symbol, bucket))
        rows.append(
            _quote_row(
                target,
                bars_by_symbol.get(symbol) or [],
                asof=asof,
                bench_pct=bench_pct,
                ohlc=ohlc_map.get(symbol),
                ohlc_source=src_map.get(symbol, OHLC_MISSING),
            )
        )

    status = dict(ohlc_status or {})
    return {
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "asof": asof,
        "benchmarkSymbol": benchmark_symbol,
        "benchmarkName": benchmark_name,
        "benchmarkWarning": benchmark_warning,
        "benchmark": bench_row,
        "attributionKind": ATTRIBUTION_KIND,
        "summary": _summarize(rows),
        "ohlc": status,
        "rows": rows,
        "note": (
            "「涨跌原因」为**量化归因**（分时形态 + 量能 + 相对基准 + 均线位置）的机械组合，"
            "平台无新闻/公告源，故不含且不编造消息面原因。"
        ),
        "disclaimer": (
            "研究指标；当日单根 K 线口径；开/高/低来自外部源（引擎库只有收盘）；"
            "缺失即 —，不补零；非投资建议。"
        ),
    }


# --------------------------------------------------------------------------- #
# markdown
# --------------------------------------------------------------------------- #
_BUCKET_LABEL = {"pick": "当日选股", "holding": "持仓", "benchmark": "基准"}


def _fmt_row(r: Mapping[str, Any]) -> str:
    return "| {b} | {c} | {n} | {o} | {h} | {l} | {cl} | {p} | {g} | {t} | {vr} | {a} | {m} |".format(
        b=_BUCKET_LABEL.get(str(r.get("bucket")), str(r.get("bucket") or "—")),
        c=r.get("symbol"),
        n=r.get("name") or "—",
        o=_price_text(r.get("open")),
        h=_price_text(r.get("high")),
        l=_price_text(r.get("low")),
        cl=_price_text(r.get("close")),
        p=_pct_text(r.get("pct")),
        g=_pct_text(r.get("gap")),
        t=_pct_text(r.get("intraday")),
        vr=f"{_num(r.get('volRatio')):.2f}×" if _num(r.get("volRatio")) is not None else "—",
        a=f"{_num(r.get('dayAlpha')) * 100:+.2f}pct" if _num(r.get("dayAlpha")) is not None else "—",
        m=_pct_text(r.get("vsMa20")),
    )


def render_day_quote_markdown(payload: Mapping[str, Any]) -> str:
    """人读版「当日行情与涨跌归因」（结论先行、表格分层）。"""
    asof = payload.get("asof")
    bench = payload.get("benchmark") or {}
    summary = payload.get("summary") or {}
    ohlc = payload.get("ohlc") or {}

    lines: list[str] = [
        f"# 当日行情与涨跌归因（{asof}）",
        "",
        f"- 环境：SIMULATE（`liveTradingEnabled=false`）",
        f"- 口径：**当日单根 K 线**（asof = `{asof}`）；涨跌幅 = `close / prev_close − 1`（自算，不读库内混合尺度 `pct_chg`）",
        f"- 归因类型：**{payload.get('attributionKind')}**（分时形态 / 量能 / 相对基准 / 均线位置 四轴）",
        f"- 覆盖：当日选股 {payload.get('pickCount')} 只 + 持仓 {payload.get('holdingCount')} 只",
        "",
        *(
            [f"> ⚠️ **基准提醒**：{payload['benchmarkWarning']}", ""]
            if payload.get("benchmarkWarning")
            else []
        ),
        "## 基准背景（平台既有基准）",
        "",
        "| 基准 | 名称 | 开盘 | 最高 | 最低 | 收盘 | 涨跌 | 缺口 | 日内 | 量能 | 位置 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
        "| {c} | {n} | {o} | {h} | {l} | {cl} | {p} | {g} | {t} | {vr} | {m} |".format(
            c=bench.get("symbol"),
            n=bench.get("name") or "—",
            o=_price_text(bench.get("open")),
            h=_price_text(bench.get("high")),
            l=_price_text(bench.get("low")),
            cl=_price_text(bench.get("close")),
            p=_pct_text(bench.get("pct")),
            g=_pct_text(bench.get("gap")),
            t=_pct_text(bench.get("intraday")),
            vr=f"{_num(bench.get('volRatio')):.2f}×" if _num(bench.get("volRatio")) is not None else "—",
            m=_pct_text(bench.get("vsMa20")),
        ),
        "",
        "## 涨跌概况",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 计涨跌标的 | {summary.get('counted')} |",
        f"| 上涨 / 下跌 / 平盘 | **{summary.get('upCount')}** / **{summary.get('downCount')}** / {summary.get('flatCount')} |",
        f"| 平均涨跌 | **{_pct_text(summary.get('avgPct'))}** |",
        f"| 中位涨跌 | {_pct_text(summary.get('medianPct'))} |",
        f"| 基准当日 | {_pct_text(bench.get('pct'))} |",
    ]
    best = summary.get("best") or {}
    worst = summary.get("worst") or {}
    lines += [
        f"| 最强 | {best.get('symbol') or '—'} {best.get('name') or ''} {_pct_text(best.get('pct'))} |",
        f"| 最弱 | {worst.get('symbol') or '—'} {worst.get('name') or ''} {_pct_text(worst.get('pct'))} |",
        "",
    ]

    tags = summary.get("tagCounts") or {}
    if tags:
        lines += [
            "## 原因分布（标签频次）",
            "",
            "| 标签 | 只数 |",
            "|---|---|",
        ]
        lines += [f"| {k} | {v} |" for k, v in tags.items()]
        lines.append("")

    lines += [
        "## 逐只明细（开 / 收 / 涨跌 / 原因）",
        "",
        "| 类别 | 代码 | 名称 | 开盘 | 最高 | 最低 | 收盘 | 涨跌 | 缺口 | 日内 | 量能 | 相对基准 | 位置 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in payload.get("rows") or []:
        lines.append(_fmt_row(row))
    lines.append("")

    reasons = [r for r in (payload.get("rows") or []) if r.get("reason")]
    if reasons:
        lines += ["## 涨跌原因（逐只一句话）", ""]
        for r in reasons:
            lines.append(f"- **{r.get('symbol')} {r.get('name') or ''}**：{r.get('reason')}")
        lines.append("")

    missing = int(summary.get("missingOhlc") or 0)
    if missing:
        lines += [
            f"> ⚠️ 有 **{missing}** 只缺开盘价（引擎库 `daily_price` 只有收盘价），"
            "归因已降级为「量能 + 相对基准 + 位置」，形态判断不参与。",
            "",
        ]
    if ohlc.get("degraded"):
        lines += [f"> ⚠️ OHLC 补充降级：{ohlc.get('degraded')}（该列显示 —，不补零）", ""]

    if payload.get("note"):
        lines += [f"> {payload['note']}", ""]
    if payload.get("disclaimer"):
        lines += [f"> {payload['disclaimer']}", ""]
    return "\n".join(lines) + "\n"
