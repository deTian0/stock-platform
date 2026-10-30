"""User-readable daily digest (markdown) rendered from the brief archive.

The pipeline's outputs (brief.json / SQLite / JSONL) are machine-first. This
module answers the "人能一眼看懂" gap: one markdown file per asof, rendered
from the **authoritative SQLite brief repository** (ADR 0049) — never from a
parallel parse of JSON exports.

Data sources, all read-only:
  - brief:      ``SqliteBriefRepository`` (latest or by asof)
  - hit tracking: ``format_hit_report`` (X3 single point)
  - performance: pending/settled counts from the recommendations JSONL

Outputs ``{out_dir}/{asof}-{session}.md`` (and ``.html``), copies that render to
``{asof}.md`` / ``latest.md`` / ``latest-{session}.md``, and keeps the other
session's file. Fail-closed: no brief found → a stub that says so (never
fabricated numbers). The stub title stays ``# 每日简报 · {asof}`` when there
is no session to name.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from .hit_tracking import format_hit_report, open_hit_repository
from .performance import build_attribution, format_pct, settled_records
from .persistence import BriefRecord, open_brief_repository
from .report_html import render_report_html

ENV_PERF_LOG = "STOCK_PLATFORM_PERFORMANCE_LOG"
DEFAULT_PERF_LOG = "./data/recommend_decisions.jsonl"
DEFAULT_OUT_DIR = "./data/digests"

_DISCLAIMER = "研究简报，非投资建议；环境 SIMULATE，liveTradingEnabled 恒为 false。"

# 同花顺手机版一次导入上限 = 5 只；digest 的「同花顺导入」块据此分组（超出须分批粘贴）。
THS_IMPORT_PER_LINE = 5

# 同花顺「导入自选」txt 落盘目录（每行 1 个 6 位码）。默认与 data/digests 同级。
DEFAULT_THS_DIR = "./data/ths_import"


def _perf_log_path() -> Path:
    raw = (os.environ.get(ENV_PERF_LOG) or DEFAULT_PERF_LOG).strip()
    return Path(raw)


def performance_summary(asof: str | None = None) -> dict[str, Any]:
    """Count pending / settled rows + a returns overview (best-effort).

    Never raises: a missing or unreadable file yields ``{"available": False}``
    so a digest is never blocked by the log. Counts are computed from a tolerant
    line-by-line parse (a corrupt line is skipped, not fatal); the returns block
    reuses the single-point 口径 in :mod:`stock_platform_research.performance`
    (``settled_records`` + ``build_attribution``) so the digest numbers and the
    performance CLI never drift.
    """
    out: dict[str, Any] = {"available": False}
    path = _perf_log_path()
    if not path.is_file():
        return out
    total = pending = settled = asof_pending = 0
    parsed: list[Mapping[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, Mapping):
                    continue
                parsed.append(row)
                total += 1
                if row.get("pending"):
                    pending += 1
                else:
                    settled += 1
                if asof and str(row.get("date") or "")[:10] == asof and row.get("pending"):
                    asof_pending += 1
    except OSError:
        return out
    out = {
        "available": True,
        "path": str(path),
        "total": total,
        "pending": pending,
        "settled": settled,
        "returns": build_attribution(settled_records(parsed)),
    }
    if asof:
        out["asofPending"] = asof_pending
    return out


def _fmt_score(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_price(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


_DASH = "—"
_SESSION_LABEL = {"pre": "盘前", "post": "盘后"}
_BENCHMARK = "000905"
_SECONDARY_DISCLAIMER = (
    "二次精选是呈现口径，不参与评分、不改 picks、不改变仓位建议；入选不是更强的推荐。"
)


def _sym6(symbol: Any) -> str:
    raw = str(symbol or "").split(".")[0]
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits.zfill(6)[-6:] if digits else ""


def _quote_label(quote_date: str | None) -> str:
    if not quote_date or len(str(quote_date)) < 10:
        return _DASH
    parts = str(quote_date)[:10].split("-")
    if len(parts) != 3:
        return str(quote_date)
    return f"{parts[1]}-{parts[2]}"


def _cell(value: Any, *, price: bool = False, pct: bool = False) -> str:
    if value is None:
        return _DASH
    if pct:
        try:
            return f"{float(value) * 100:+.2f}%"
        except (TypeError, ValueError):
            return _DASH
    if price:
        return _fmt_price(value)
    return str(value)


def _quote_triplet(
    symbol: Any,
    *,
    show_quotes: bool,
    quotes: Mapping[str, Mapping[str, Any]] | None,
    prev_close: float | None,
) -> tuple[str, str, str]:
    if not show_quotes:
        return _DASH, _DASH, _DASH
    bar = (quotes or {}).get(_sym6(symbol)) or {}
    opened = bar.get("open")
    closed = bar.get("close")
    pct = None
    if closed is not None and prev_close not in (None, 0):
        try:
            pct = float(closed) / float(prev_close) - 1.0
        except (TypeError, ValueError, ZeroDivisionError):
            pct = None
    return (
        _cell(opened, price=True) if opened is not None else _DASH,
        _cell(closed, price=True) if closed is not None else _DASH,
        _cell(pct, pct=True) if pct is not None else _DASH,
    )


def _prev_for(
    symbol: Any,
    asof_close: Any,
    *,
    asof: str,
    quote_date: str | None,
    prior_closes: Mapping[str, Any] | None,
) -> float | None:
    from .quotes import resolve_prev_close

    key = _sym6(symbol)
    prior = (prior_closes or {}).get(key)
    if prior is None:
        prior = (prior_closes or {}).get(str(symbol or ""))
    try:
        asof_num = float(asof_close) if asof_close is not None else None
    except (TypeError, ValueError):
        asof_num = None
    return resolve_prev_close(
        quote_date=str(quote_date or ""),
        asof=str(asof or "")[:10],
        asof_close=asof_num,
        prior_close=None if prior is None else float(prior),
    )


def _full_reason(row: Mapping[str, Any]) -> str:
    text = str(row.get("reasonSummary") or row.get("reason") or row.get("secondaryReason") or "")
    return text.replace("|", "\\|").replace("\n", " ")


def _quote_table(
    rows: list[Mapping[str, Any]],
    *,
    asof: str,
    quote_date: str | None,
    show_quotes: bool,
    quotes: Mapping[str, Mapping[str, Any]] | None,
    prior_closes: Mapping[str, Any] | None,
    reason_key: str = "reasonSummary",
) -> list[str]:
    label = _quote_label(quote_date)
    lines = [
        "| # | 代码 | 名称 | 综合分 | 收盘(asof) | "
        f"开盘({label}) | 收盘({label}) | 涨跌({label}) | 入选理由 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, row in enumerate(rows, start=1):
        prev = _prev_for(
            row.get("symbol"),
            row.get("close"),
            asof=asof,
            quote_date=quote_date,
            prior_closes=prior_closes,
        )
        opened, closed, pct = _quote_triplet(
            row.get("symbol"),
            show_quotes=show_quotes,
            quotes=quotes,
            prev_close=prev,
        )
        reason = str(row.get(reason_key) or row.get("reasonSummary") or row.get("reason") or "")
        reason = reason.replace("|", "\\|").replace("\n", " ")
        name = str(row.get("name") or "-").replace("|", "\\|")
        lines.append(
            f"| {i} | {row.get('symbol', '-')} | {name} "
            f"| {_fmt_score(row.get('composite_score'))} "
            f"| {_fmt_price(row.get('close'))} | {opened} | {closed} | {pct} | {reason or '-'} |"
        )
    return lines


def _benchmark_warning(name: str | None, symbol: str = _BENCHMARK) -> str | None:
    if not name:
        return None
    return (
        f"平台基准 `{symbol}` 在引擎库中解析为 **{name}**（个股），"
        "并非中证500 指数点位；因此「相对基准」列是相对该**个股**的超额，"
        "**不能读作指数超额**（A4 绩效台账的 avgAlpha 用的是同一口径）。"
    )


def _pct_value(
    symbol: Any,
    asof_close: Any,
    *,
    asof: str,
    quote_date: str | None,
    show_quotes: bool,
    quotes: Mapping[str, Mapping[str, Any]] | None,
    prior_closes: Mapping[str, Any] | None,
) -> float | None:
    if not show_quotes:
        return None
    bar = (quotes or {}).get(_sym6(symbol)) or {}
    closed = bar.get("close")
    prev = _prev_for(
        symbol, asof_close, asof=asof, quote_date=quote_date, prior_closes=prior_closes
    )
    if closed is None or prev in (None, 0):
        return None
    try:
        return float(closed) / float(prev) - 1.0
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _summary_line(
    rows: list[Mapping[str, Any]],
    *,
    asof: str,
    quote_date: str | None,
    show_quotes: bool,
    quotes: Mapping[str, Mapping[str, Any]] | None,
    prior_closes: Mapping[str, Any] | None,
    benchmark_name: str | None,
    benchmark_asof_close: float | None = None,
) -> list[str]:
    if not show_quotes:
        return []
    pcts = [
        p
        for p in (
            _pct_value(
                row.get("symbol"),
                row.get("close"),
                asof=asof,
                quote_date=quote_date,
                show_quotes=True,
                quotes=quotes,
                prior_closes=prior_closes,
            )
            for row in rows
        )
        if p is not None
    ]
    label = quote_date or _DASH
    if not pcts:
        return [
            f"> {label} 行情缺失，无可计算涨跌"
            "（外部日线源不可用且引擎库无该日 K 线；见顶部「数据备注」）",
            "",
        ]
    avg = sum(pcts) / len(pcts)
    bench_prev = _prev_for(
        _BENCHMARK,
        benchmark_asof_close,
        asof=asof,
        quote_date=quote_date,
        prior_closes=prior_closes,
    )
    bench = _pct_value(
        _BENCHMARK,
        bench_prev if quote_date == asof else benchmark_asof_close,
        asof=asof,
        quote_date=quote_date,
        show_quotes=True,
        quotes=quotes,
        prior_closes=prior_closes if quote_date == asof else None,
    )
    # When dates match, _pct_value's asof_close argument is ignored by
    # resolve_prev_close in favour of prior_closes. Pass prior via that map.
    if quote_date == asof:
        bench = None
        bar = (quotes or {}).get(_BENCHMARK) or {}
        closed = bar.get("close")
        if closed is not None and bench_prev not in (None, 0):
            try:
                bench = float(closed) / float(bench_prev) - 1.0
            except (TypeError, ValueError, ZeroDivisionError):
                bench = None
    head = f"> {len(pcts)} 只 {label} 平均涨跌 {avg * 100:+.2f}%"
    if bench is None:
        lines = [head + "。基准不可用", ""]
    else:
        beat = sum(1 for p in pcts if p > bench)
        lines = [head + f"，相对 {_BENCHMARK} 上涨家数 {beat}/{len(pcts)}", ""]
    warning = _benchmark_warning(benchmark_name)
    if warning:
        lines.insert(0, f"> {warning}")
    return lines


def _picks_table(
    picks: list[Mapping[str, Any]],
    *,
    asof: str,
    quote_date: str | None,
    show_quotes: bool,
    quotes: Mapping[str, Mapping[str, Any]] | None,
    prior_closes: Mapping[str, Any] | None,
) -> list[str]:
    return _quote_table(
        picks,
        asof=asof,
        quote_date=quote_date,
        show_quotes=show_quotes,
        quotes=quotes,
        prior_closes=prior_closes,
    )


def _ths_code(symbol: Any) -> str:
    """Bare 6-digit code that 同花顺 expects (drop any ``.SZ`` / ``.SH`` suffix).

    Only a clean 6-digit code is returned; anything else (e.g. dirty upstream
    rows) yields ``""`` so it never pollutes the paste-ready import line.
    """
    if symbol is None:
        return ""
    base = str(symbol).strip().split(".")[0].strip()
    digits = "".join(ch for ch in base if ch.isdigit())
    return digits if len(digits) == 6 else ""


def _ths_codes(picks: list[Mapping[str, Any]]) -> list[str]:
    """Ordered, de-duplicated list of bare 6-digit codes for 同花顺 import.

    Keeps recommendation order (rank ascending); only clean 6-digit codes pass
    (:func:`_ths_code`), so dirty upstream rows never pollute the output.
    """
    codes: list[str] = []
    seen: set[str] = set()
    for p in picks:
        code = _ths_code(p.get("symbol"))
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def _short_term_codes(record: "BriefRecord | None") -> list[str]:
    """Bare 6-digit codes of the ②B 短线榜 board (payload ``rankings``).

    短线与长线各有独立的可复制代码块；这里从 brief payload 的榜单取 ②B 榜，
    再走同一套 :func:`_ths_code` 归一化（单点），保证两条线口径一致。
    """
    if record is None:
        return []
    from .rankings import BOARD_SLUGS, SHORT_TERM_KEY  # local: keep module import-light

    boards = ((record.payload or {}).get("rankings") or {}).get("boards") or {}
    items = (boards.get(BOARD_SLUGS[SHORT_TERM_KEY]) or {}).get("items") or []
    return _ths_codes([dict(it) for it in items if isinstance(it, Mapping)])


def _secondary_codes(record: "BriefRecord | None", profile: str) -> list[str]:
    """Bare 6-digit codes of the 二次精选 selection for ``profile``.

    二次精选在 :func:`build_digest_text` 里是**现场重算**的（不入 brief 存档），
    所以 txt 侧必须用同一个函数、同一份入参再算一次，才能和报告里的代码块逐字一致。
    ②A 取 quality 榜 ``items``；②B 取 short_term 榜 ``pool``（无 pool 即无二次精选）。
    """
    if record is None:
        return []
    from .rankings import BOARD_SLUGS, QUALITY_KEY, SHORT_TERM_KEY
    from .secondary_pick import select_secondary

    boards = ((record.payload or {}).get("rankings") or {}).get("boards") or {}
    if profile == "quality":
        board = boards.get(BOARD_SLUGS[QUALITY_KEY]) or {}
        source = board.get("items") or []
    else:
        board = boards.get(BOARD_SLUGS[SHORT_TERM_KEY]) or {}
        source = board.get("pool")
        if source is None:
            return []
    rows = [dict(it) for it in source if isinstance(it, Mapping)]
    if not rows:
        return []
    picked = select_secondary(rows, profile=profile, top_k=THS_IMPORT_PER_LINE)
    return _ths_codes(list(picked.get("selected") or []))


def _ths_import_section(
    picks: list[Mapping[str, Any]],
    *,
    per_line: int = THS_IMPORT_PER_LINE,
    label: str | None = None,
    source_note: str | None = None,
) -> list[str]:
    """Copy-paste block for 同花顺 (THS) self-select import.

    同花顺手机版**一次最多导入 5 只**，故按 ``per_line`` 分组：每行一组、逐行粘贴。
    代码按推荐序（rank 升序）保留，去重 + 归一化为 6 位。无有效代码则整块省略
    （与全篇 fail-closed 一致，不生成占位行）。``label`` 标注线别（长线 / 短线），
    两条线各出一块，互不混淆。
    """
    codes = _ths_codes(picks)
    if not codes:
        return []
    tag = f" · {label}" if label else ""
    out = [f"**同花顺导入{tag}（每行 {per_line} 只，逐行复制到「自选 → 导入」）：**", ""]
    out.append("```text")
    for i in range(0, len(codes), per_line):
        out.append(" ".join(codes[i : i + per_line]))
    out.append("```")
    out.append("")
    out.append(source_note or "导入码来自生产榜，不是二次精选结果。")
    out.append("")
    return out


def write_ths_import(
    codes: list[str],
    *,
    day: str,
    out_dir: str | Path | None = None,
    kind: str = "",
) -> dict[str, Any] | None:
    """Emit the 同花顺 (THS) watchlist import txt for report ``day``.

    Writes ``{out_dir}/{day}{kind}.txt`` plus a ``latest{kind}.txt`` pointer
    copy -- one bare 6-digit code per line, no header, no names (exactly what
    同花顺's 「导入自选」 dialog wants; the user confirmed this import path works).
    Returns ``{"thsPath", "latestThsPath", "thsCount"}``, or ``None`` when there
    are no codes (fail-closed: no placeholder file). Stale ``*.sel`` files in
    the same directory are removed -- the project standardised on txt only.
    """
    if not codes:
        return None
    root = Path(out_dir) if out_dir is not None else Path(DEFAULT_THS_DIR)
    root.mkdir(parents=True, exist_ok=True)
    for stale in sorted(root.glob("*.sel")):
        try:
            stale.unlink()
        except OSError:  # pragma: no cover - best effort
            pass
    text = "\n".join(codes) + "\n"
    dated = root / f"{day}{kind}.txt"
    latest = root / f"latest{kind}.txt"
    dated.write_text(text, encoding="utf-8")
    shutil.copyfile(dated, latest)
    return {
        "thsPath": str(dated),
        "latestThsPath": str(latest),
        "thsCount": len(codes),
    }


_ACTION_LABELS = {
    "exit": "退出",
    "trim": "减仓",
    "add": "补仓",
    "hold": "继续持有",
    "pending": "待定（缺成本价/现价）",
}


def _profile_compare() -> list[str]:
    from .secondary_pick import PROFILE_TREND, QUALITY_WEIGHTS, SHORT_WEIGHTS

    def _w(weights: Mapping[str, float]) -> str:
        return " · ".join(f"{k} {v * 100:.0f}%" for k, v in weights.items())

    return [
        "**两条榜用不同的取舍口径**（同一截面，取向相反）：",
        "",
        "| 榜 | 维度权重 | 取向 |",
        "|---|---|---|",
        f"| ②A 长线 | {_w(QUALITY_WEIGHTS)} | {PROFILE_TREND['quality']} |",
        f"| ②B 短线 | {_w(SHORT_WEIGHTS)} | {PROFILE_TREND['short']} |",
        "",
        _SECONDARY_DISCLAIMER,
        "",
    ]


def _secondary_lines(
    title: str,
    result: Mapping[str, Any],
    *,
    asof: str,
    quote_date: str | None,
    show_quotes: bool,
    quotes: Mapping[str, Mapping[str, Any]] | None,
    prior_closes: Mapping[str, Any] | None,
    import_label: str | None = None,
    import_note: str | None = None,
) -> list[str]:
    selected = list(result.get("selected") or [])
    rejected = list(result.get("rejected") or [])
    n_in = int((result.get("stats") or {}).get("input") or 0)
    lines = [f"### {title}（{n_in} 进 {len(selected)}）", ""]
    note = (result.get("stats") or {}).get("note")
    if note:
        lines.append(str(note))
        lines.append("")
    if selected:
        lines.extend(
            _quote_table(
                selected,
                asof=asof,
                quote_date=quote_date,
                show_quotes=show_quotes,
                quotes=quotes,
                prior_closes=prior_closes,
                reason_key="secondaryReason",
            )
        )
        lines.append("")
        # 二次精选自己也要「一键导入」：生产榜的代码块与二次精选取舍口径不同
        # （②B 尤其如此），只给生产榜的块会让人手动删改。紧贴入选表出一块。
        if import_label:
            lines.extend(
                _ths_import_section(
                    selected, label=import_label, source_note=import_note
                )
            )
    else:
        lines.append("_无入选_")
        lines.append("")
    lines.append(f"#### {title}未入选")
    lines.append("")
    if not rejected:
        lines.append("_无_")
        lines.append("")
        return lines
    lines.append("| 代码 | 名称 | 落选原因 |")
    lines.append("|---|---|---|")
    for row in rejected:
        reason = str(row.get("rejectReason") or "-").replace("|", "\\|")
        name = str(row.get("name") or "-").replace("|", "\\|")
        lines.append(f"| {row.get('symbol', '-')} | {name} | {reason} |")
    lines.append("")
    return lines


def _action_details(payload: Mapping[str, Any], items: list[Mapping[str, Any]]) -> list[str]:
    from .rankings import code_key

    rankings = payload.get("rankings") or {}
    review = rankings.get("holdingsReview") or {}
    policy = review.get("exitPolicy") or {}
    rows = {
        code_key(r.get("code")): r
        for r in (review.get("rows") or [])
        if isinstance(r, Mapping)
    }
    sizing = rankings.get("positionSizing") or {}
    orders = {
        code_key(o.get("code")): o
        for o in (sizing.get("orders") or [])
        if isinstance(o, Mapping)
    }
    market = str(payload.get("market") or "")
    cap = sizing.get("capWeight")
    lines: list[str] = []
    for it in items:
        key = code_key(it.get("symbol"))
        row = rows.get(key) or {}
        order = orders.get(key) or {}
        name = it.get("name") or row.get("name") or ""
        action = it.get("action") or row.get("action") or "-"
        qty = it.get("suggestQty")
        if qty is None:
            qty = order.get("qty")
        reason = it.get("reason") or row.get("reason") or "-"
        ret = row.get("ret_pct")
        if ret is None:
            ret = it.get("ret_pct")
        entry = row.get("entry_price")
        price = row.get("price")
        if price is None:
            price = it.get("price")
        held = row.get("held_days")
        asset = row.get("asset_class") or order.get("assetClass") or it.get("assetClass")
        available = order.get("available")
        if available is None:
            available = it.get("availableQty")
        unsellable = order.get("unsellable")
        held_qty = order.get("heldQty")
        if held_qty is None:
            held_qty = it.get("heldQty")
        w0 = order.get("weightBefore")
        if w0 is None:
            w0 = it.get("weightPct")
        w1 = order.get("weightAfter")
        if w1 is None:
            w1 = it.get("weightAfterPct")
        lines.append(f"**{it.get('symbol') or '-'} {name} · {action} {qty if qty is not None else '-'} 股**")
        stop = policy.get("stop_loss")
        ret_txt = "-" if ret is None else f"{float(ret):+.2f}%"
        stop_txt = "-" if stop is None else f"−{abs(float(stop)):.0f}%"
        lines.append(f"- 触发规则：{reason}；止损线 {stop_txt}，实际收益 {ret_txt}")
        if policy.get("take_profit") in (0, 0.0):
            lines.append("- 未触发：take_profit 已关闭")
        entry_txt = _fmt_price(entry) if entry is not None else "-"
        price_txt = _fmt_price(price) if price is not None else "-"
        held_txt = "-" if held is None else str(held)
        lines.append(f"- 成本 {entry_txt} → 参考价 {price_txt} · 持有 {held_txt} 个交易日")
        min_hold = policy.get("min_hold")
        reason_s = str(reason or "")
        if (
            held is not None
            and min_hold is not None
            and int(held) < int(min_hold)
            and not reason_s.startswith("stop_loss")
            and not reason_s.startswith("take_profit")
        ):
            lines.append(f"- 未到最短持有 {int(min_hold)} 个交易日，故非到期退出")
        av = "-" if available is None else str(int(available))
        hq = "-" if held_qty is None else str(int(held_qty))
        un = "-" if unsellable is None else str(int(unsellable))
        lines.append(f"- 可卖 {av} / 持仓 {hq}，不可卖 {un}")
        try:
            unsellable_n = float(unsellable) if unsellable is not None else 0
        except (TypeError, ValueError):
            unsellable_n = 0
        if asset == "stock" and market == "CN" and unsellable_n > 0:
            lines.append("- 不可卖数量按 A 股 T+1 理解")
        def _w(value: Any) -> str:
            if value is None:
                return "-"
            try:
                return f"{float(value) * 100:.2f}%"
            except (TypeError, ValueError):
                return str(value)
        cap_txt = "-" if cap is None else f"{float(cap) * 100:.0f}%"
        lines.append(f"- 集中度：{_w(w0)} → {_w(w1)}，单票上限 {cap_txt}")
        lines.append("")
    return lines


def _rankings_section(
    payload: Mapping[str, Any],
    *,
    asof: str = "",
    quote_date: str | None = None,
    show_quotes: bool = False,
    quotes: Mapping[str, Mapping[str, Any]] | None = None,
    prior_closes: Mapping[str, Any] | None = None,
    benchmark_name: str | None = None,
    benchmark_asof_close: float | None = None,
) -> list[str]:
    rankings = payload.get("rankings") or {}
    boards = rankings.get("boards") or {}
    if not boards:
        return []
    lines: list[str] = []
    # ③B 明细行来自 holdingsReview（B5 复核结果），本身不带中文名 —— 用 ③A 补。
    name_by_code = {
        str(it.get("symbol") or "").strip(): it.get("name")
        for it in ((boards.get("holdings") or {}).get("items") or [])
        if it.get("name")
    }
    order = [
        ("quality", "②A 质量榜", "二"),
        ("short_term", "②B 短线榜", "三"),
        ("holdings", "③A 持仓", "四"),
        ("actions", "③B 操作建议", "五"),
        ("watchlist", "③C 观察名单", "六"),
    ]
    for slug, label, num in order:
        board = boards.get(slug) or {}
        items = board.get("items") or []
        review = rankings.get("holdingsReview") or {}
        review_rows = list(review.get("rows") or [])
        rcounts = review.get("counts") or {}

        if slug == "actions" and not items and review_rows:
            # ③B only ever lists exit/trim (REDUCE_ACTIONS). When the whole book
            # is "hold" the board is empty *by design* — but an empty board read
            # like a data failure. Render the real verdict per holding instead.
            pending = int(rcounts.get("pending") or 0)
            held = int(rcounts.get("hold") or 0)
            lines.append(f"## {num}、{label}（0 需操作 · {len(review_rows)} 只已复核）")
            lines.append("")
            if pending == len(review_rows):
                lines.append("_空（fail-closed：持仓缺成本价/现价，不生成占位条目）_")
                lines.append("")
                continue
            if held:
                lines.append(
                    f"**当日无需减仓：{held} 只持仓全部继续持有**"
                    f"（B5 规则未触发 exit/trim）"
                )
                lines.append("")
            lines.append("| # | 代码 | 名称 | 持有天数 | 收益% | 动作 |")
            lines.append("|---|---|---|---|---|---|")
            for i, r in enumerate(review_rows, start=1):
                ret = r.get("ret_pct")
                held_days = r.get("held_days")
                code = str(r.get("code") or "").strip()
                lines.append(
                    f"| {i} | {code or '-'} | {name_by_code.get(code) or '-'} "
                    f"| {'-' if held_days is None else held_days} "
                    f"| {'' if ret is None else f'{ret:+.2f}'} "
                    f"| {_ACTION_LABELS.get(r.get('action'), r.get('action') or '-')} |"
                )
            lines.append("")
            continue

        if slug == "quality" and items:
            from .secondary_pick import select_secondary

            picked = select_secondary(items, profile="quality", top_k=5)
            lines.append(f"## {num}、{label}")
            lines.append("")
            lines.extend(_profile_compare())
            lines.extend(
                _secondary_lines(
                    "②A 二次精选",
                    picked,
                    asof=asof,
                    quote_date=quote_date,
                    show_quotes=show_quotes,
                    quotes=quotes,
                    prior_closes=prior_closes,
                    import_label="二次精选（长线）",
                    import_note=(
                        "导入码 = 上方②A 二次精选入选（已剔除 ST/地量，"
                        "与「一、今日 Top10」的生产榜不同）。"
                    ),
                )
            )
            continue

        if slug == "short_term":
            from .secondary_pick import select_secondary

            lines.append(f"## {num}、{label}")
            lines.append("")
            pool = board.get("pool")
            if pool is None:
                lines.append("无候选池，未做二次精选")
                lines.append("")
            else:
                picked = select_secondary(list(pool), profile="short", top_k=5)
                lines.extend(
                    _secondary_lines(
                        "②B 短线榜 · 二次精选",
                        picked,
                        asof=asof,
                        quote_date=quote_date,
                        show_quotes=show_quotes,
                        quotes=quotes,
                        prior_closes=prior_closes,
                        import_label="二次精选（短线）",
                        import_note=(
                            "导入码 = 上方②B 二次精选入选（与下方生产榜的短线块不同）。"
                        ),
                    )
                )
                lines.extend(
                    _summary_line(
                        list(pool),
                        asof=asof,
                        quote_date=quote_date,
                        show_quotes=show_quotes,
                        quotes=quotes,
                        prior_closes=prior_closes,
                        benchmark_name=benchmark_name,
                        benchmark_asof_close=benchmark_asof_close,
                    )
                )
            # 生产榜的块照 ADR 0083 保留：其内容 = data/ths_import/{reportDay}_short.txt。
            if items:
                lines.extend(_ths_import_section(items, label="短线"))
            elif pool is None:
                lines.append("_空（fail-closed，不生成占位条目）_")
                lines.append("")
            continue

        shown = min(len(items), 10)
        total = len(items)
        suffix = f"{total} 条" if shown == total else f"{total} 条，列前 {shown}"
        lines.append(f"## {num}、{label}（{suffix}）")
        lines.append("")
        if not items:
            lines.append("_空（fail-closed，不生成占位条目）_")
            lines.append("")
            continue
        if slug == "actions" and any(it.get("suggestQty") for it in items):
            # ADR 0081：操作建议必须可执行 —— 给出股数 / 金额，而不只是一句 reason。
            lines.append("| # | 代码 | 名称 | 动作 | 卖出数量 | 参考价 | 金额 | 权重 | 备注 |")
            lines.append("|---|---|---|---|---|---|---|---|---|")
            for i, it in enumerate(items[:10], start=1):
                qty = it.get("suggestQty")
                px = float(it.get("price") or it.get("close") or 0) or None
                amt = it.get("suggestAmount")
                w0, w1 = it.get("weightPct"), it.get("weightAfterPct")
                weight = (
                    f"{w0 * 100:.2f}% → {w1 * 100:.2f}%"
                    if w0 is not None and w1 is not None
                    else "-"
                )
                note = str(it.get("reason") or "").replace("|", "\\|")
                code = str(it.get("symbol") or "-")
                lines.append(
                    f"| {i} | {code} | {it.get('name') or name_by_code.get(code) or '-'} "
                    f"| {_ACTION_LABELS.get(it.get('action'), it.get('action') or '-')} "
                    f"| **{qty} 股** | {'-' if px is None else f'{px:.3f}'} "
                    f"| {'-' if amt is None else f'{amt:,.2f}'} | {weight} | {note or '-'} |"
                )
            lines.append("")
            lines.extend(_action_details(payload, list(items[:10])))
            sizing = rankings.get("positionSizing") or {}
            if sizing:
                lines.append(
                    f"> 单票上限 {float(sizing.get('capWeight') or 0) * 100:.0f}%；"
                    f"整手 {sizing.get('lot') or 100} 股；本表合计卖出 "
                    f"**{float(sizing.get('totalAmount') or 0):,.2f}** 元。不产生加仓建议。"
                )
                lines.append("")
            continue
        if slug == "holdings":
            lines.append("| # | 代码 | 名称 | 综合分 | 截面排名 | 备注 |")
            lines.append("|---|---|---|---|---|---|")
        else:
            lines.append("| # | 代码 | 名称 | 综合分 | 备注 |")
            lines.append("|---|---|---|---|---|")
        for i, it in enumerate(items[:10], start=1):
            # ③A/③C 的 item 只有 reasonSummary（没有 reason）；漏取会让备注列恒为 "-"
            note = str(
                it.get("reason")
                or it.get("reasonSummary")
                or (it.get("belowMedian") and "低于中位（只读提示）")
                or ""
            ).replace("|", "\\|")
            score = _fmt_score(it.get("composite_score"))
            if slug == "holdings":
                rank = it.get("crossSectionRank")
                lines.append(
                    f"| {i} | {it.get('symbol', '-')} | {it.get('name') or '-'} "
                    f"| {score} | {'-' if rank is None else rank} | {note or '-'} |"
                )
            else:
                lines.append(
                    f"| {i} | {it.get('symbol', '-')} | {it.get('name') or '-'} "
                    f"| {score} | {note or '-'} |"
                )
        lines.append("")
    return lines


def _human_ts(iso: Any) -> str:
    """Render an ISO timestamp in the machine's local zone (best-effort).

    ``BriefRecord.generated_at`` is stored as UTC (e.g. ``2026-10-16T00:30:37+00:00``),
    which reads like "00:30" and made the digest look stale/odd to a CST reader.
    Falls back to the raw string when it cannot be parsed.
    """
    if not iso:
        return ""
    raw = str(iso).strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return raw
    if dt.tzinfo is None:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    local = dt.astimezone()
    off = local.strftime("%z")
    if len(off) == 5:  # +0800 -> +08:00
        off = f"{off[:3]}:{off[3:]}"
    return local.strftime("%Y-%m-%d %H:%M:%S") + f" {off}"


def _coerce_session(session: str | None, payload: Mapping[str, Any]) -> str:
    raw = session if session is not None else payload.get("session")
    text = str(raw or "pre").strip().lower()
    return text if text in {"pre", "post"} else "pre"


def _coerce_run_date(run_date: str | None, payload: Mapping[str, Any]) -> str | None:
    raw = run_date if run_date is not None else payload.get("runDate")
    if not raw:
        return None
    return str(raw)[:10]


def build_digest_text(
    record: BriefRecord,
    *,
    hits_repo: Any | None = None,
    session: str | None = None,
    run_date: str | None = None,
    quote_date: str | None = None,
    show_quotes: bool = False,
    quotes: Mapping[str, Mapping[str, Any]] | None = None,
    prior_closes: Mapping[str, Any] | None = None,
    extra_notes: list[str] | None = None,
    benchmark_name: str | None = None,
    benchmark_asof_close: float | None = None,
) -> str:
    """Render one BriefRecord as the human-readable markdown digest."""
    payload = record.payload or {}
    asof = record.asof
    sess = _coerce_session(session, payload)
    label = _SESSION_LABEL[sess]
    rd = _coerce_run_date(run_date, payload)
    qd = str(quote_date)[:10] if quote_date else (str(payload.get("quoteDate"))[:10] if payload.get("quoteDate") else None)
    lines: list[str] = []
    # 标题的日期 = 运行日（这份简报服务的那一天）；asof 只是选股用的截面基准日。
    # 定时任务都带 -PrevSession，asof 恒为 T-1，若标题只写 asof，盘后正文里
    # 「开盘(T)/收盘(T)/涨跌(T)」那几列会和标题日期直接冲突。
    report_day = rd or asof
    basis_note = f"（选股基准 {asof}）" if rd and rd != asof else ""
    lines.append(f"# 每日简报 · {label} · {report_day}{basis_note}")
    lines.append("")
    # 口径自证：定时任务（08:30 盘前 / 15:30 盘后）都带 -PrevSession，asof 恒为
    # 「上一交易日收盘截面」—— 当日 K 线要等 18:30 回补后才进市场库。把「数据基准日」
    # 与「本简报实际生成时刻」并列写出，避免 asof 被误读成「报告过期」。
    generated_local = _human_ts(record.generated_at)
    lines.append(
        f"> **口径**：数据基准日 asof={asof}（T-1 收盘截面）；"
        f"报告类型：{label}；运行日 {rd or '未提供'}；报价日 quoteDate={qd or '未提供'}；"
        f"生成于 {generated_local or '-'}。"
        f"盘前/盘后任务取上一交易日收盘（当日 K 线尚未入库），这是设计约定，不是数据滞后。"
    )
    if sess == "pre":
        lines.append("> 盘前：运行日行情尚未作为本报告的报价使用，开盘/收盘/涨跌留空（—）。盘后报告补齐。")
    lines.append("")
    lines.append(f"- 环境：{record.environment}（{_DISCLAIMER}）")
    provider = record.provider or payload.get("provider") or "未记录"
    lines.append(f"- 数据源：`{provider}`")
    tier = record.universe_tier or payload.get("universeTier") or "-"
    lines.append(
        f"- 宇宙：{payload.get('universeSize', '-')} 只（档位 {tier}），"
        f"截面 {payload.get('panelSize', '-')} 行，TopN {payload.get('topN', '-')}"
    )
    if record.data_note:
        lines.append(f"- 数据备注：{record.data_note}")
    for note in extra_notes or []:
        if note:
            lines.append(f"- 数据备注：{note}")
    if payload.get("softGates"):
        lines.append("- 闸门：softGates 开启" + ("（闸门放宽）" if payload.get("gatesRelaxed") else ""))
    _gen_raw = record.generated_at or ""
    if generated_local and _gen_raw and generated_local != _gen_raw:
        lines.append(f"- 生成时间：{generated_local}（存档值 {_gen_raw}）")
    else:
        lines.append(f"- 生成时间：{generated_local or _gen_raw or '-'}")
    lines.append("")

    picks = record.picks or []
    lines.append(f"## 一、今日 Top10 · 长线（{len(picks)} 条）")
    lines.append("")
    if not picks:
        msg = payload.get("emptyPicksMessage") or "当日无推荐"
        tip = payload.get("emptyPicksTip")
        lines.append(f"**{msg}**")
        if tip:
            lines.append("")
            lines.append(f"> {tip}")
        lines.append("")
    else:
        lines.extend(_ths_import_section(picks, label="长线"))
        lines.extend(
            _picks_table(
                picks,
                asof=asof,
                quote_date=qd,
                show_quotes=show_quotes,
                quotes=quotes,
                prior_closes=prior_closes,
            )
        )
        lines.append("")
        if not show_quotes:
            lines.append(f"盘后报告补齐 {qd or 'quoteDate'} 行情。")
            lines.append("")
        else:
            lines.extend(
                _summary_line(
                    picks,
                    asof=asof,
                    quote_date=qd,
                    show_quotes=True,
                    quotes=quotes,
                    prior_closes=prior_closes,
                    benchmark_name=benchmark_name,
                    benchmark_asof_close=benchmark_asof_close,
                )
            )

    lines.extend(
        _rankings_section(
            payload,
            asof=asof,
            quote_date=qd,
            show_quotes=show_quotes,
            quotes=quotes,
            prior_closes=prior_closes,
            benchmark_name=benchmark_name,
            benchmark_asof_close=benchmark_asof_close,
        )
    )

    # ---- hit tracking (X3 single point rendering) ----
    if hits_repo is not None:
        lines.append("## 七、命中追踪")
        lines.append("")
        try:
            hits_text = format_hit_report(hits_repo, asof=asof).strip()
            hits_lines = hits_text.splitlines()
            # The report renders its own H1/H2; demote so the digest keeps one H1
            # per file and 命中追踪 stays a subsection of 七.
            demoted = []
            for line in hits_lines:
                if line.startswith("## "):
                    demoted.append("#### " + line[3:])
                elif line.startswith("# "):
                    demoted.append("### " + line[2:])
                else:
                    demoted.append(line)
            lines.append("\n".join(demoted))
        except Exception as exc:  # pragma: no cover - defensive, digest never crashes
            lines.append(f"_命中追踪暂不可用：{exc}_")
            lines.append("")

    perf = performance_summary(asof)
    lines.append("## 八、绩效台账")
    lines.append("")
    if not perf.get("available"):
        lines.append("_绩效 JSONL 未配置或不存在（best-effort，不阻断简报）_")
    else:
        lines.append(
            f"- 累计决策 {perf.get('total', 0)} 条：待结算 {perf.get('pending', 0)}，"
            f"已结算 {perf.get('settled', 0)}"
        )
        if asof:
            lines.append(f"- 其中 {asof} 新增待结算 {perf.get('asofPending', 0)} 条")
        ret = perf.get("returns") or {}
        if ret.get("count"):
            win = ret.get("winRate")
            avg = ret.get("avgReturn")
            bench = ret.get("benchmarkSymbol") or "-"
            beat = ret.get("beatBenchmarkRate")
            best, worst = ret.get("best"), ret.get("worst")
            avg_txt = format_pct(float(avg)) if avg is not None else "-"
            win_txt = f"{float(win) * 100:.1f}%" if win is not None else "-"
            beat_txt = f"{float(beat) * 100:.1f}%" if beat is not None else "-"
            best_txt = format_pct(float(best)) if best is not None else "-"
            worst_txt = format_pct(float(worst)) if worst is not None else "-"
            lines.append(
                f"- 收益概览（已结算 {ret['count']} 条 / 基准 {bench}）："
                f"胜率 {win_txt}，平均收益 {avg_txt}，跑赢基准 {beat_txt}，"
                f"最好 {best_txt}、最差 {worst_txt}"
            )
            if ret.get("avgAlpha") is None:
                lines.append("  - 超额（alpha）暂缺：结算时未带基准日线")
        elif perf.get("settled", 0):
            lines.append("- 已结算样本缺可解析收益（raw 全空），暂无收益数字")
        else:
            lines.append("- 暂无已结算样本，暂无收益数字（待持有期到期后结算）")
    lines.append("")

    lines.append("---")
    lines.append("*digest 由 `stock-platform-digest` 渲染；权威数据以 SQLite brief 仓库为准。*")
    lines.append("")
    return "\n".join(lines)


def _stub_text(asof: str) -> str:
    return (
        f"# 每日简报 · {asof}\n\n"
        f"**未找到该日期的 brief 存档**（fail-closed：不生成编造内容）。\n\n"
        f"可先运行 `stock-platform-daily`（或调度包装脚本）生成 brief，再渲染 digest。\n"
    )


def build_digest(
    *,
    asof: str | None = None,
    db_url: str | Path | None = None,
    hit_db_url: str | Path | None = None,
    out_dir: str | Path | None = None,
    emit_html: bool = False,
    emit_ths: bool = False,
    ths_dir: str | Path | None = None,
    session: str | None = None,
    run_date: str | None = None,
    ohlc: bool | None = None,
    cache_dir: str | Path | None = None,
    quotes: Mapping[str, Mapping[str, Any]] | None = None,
    prior_closes: Mapping[str, Any] | None = None,
    benchmark_name: str | None = None,
    benchmark_asof_close: float | None = None,
    fetch_ohlc: Any | None = None,
) -> dict[str, Any]:
    """Render the digest for ``asof`` (or the latest brief) and write files.

    Returns ``{"asof", "found", "digestPath", "latestPath"}`` (plus
    ``htmlPath`` / ``latestHtmlPath`` when ``emit_html``). Writes ``{asof}.md``
    plus a ``latest.md`` pointer copy when a brief was found; a stub
    ``{asof}.md`` (and latest copy) when not. ``emit_html`` additionally renders
    the same text through :mod:`stock_platform_research.report_html` so the
    scheduled runs ship markdown **and** the local report-template HTML.
    ``emit_ths`` additionally emits the 同花顺 import txt for **both** lines
    (``{asof}.txt`` / ``latest.txt`` for 长线, ``{asof}_short.txt`` /
    ``latest_short.txt`` for 短线); its directory defaults to a ``ths_import``
    sibling of the digest dir, or ``DEFAULT_THS_DIR`` when ``out_dir`` is not given.
    """
    repo = open_brief_repository(db_url)
    record = repo.get_by_asof(asof) if asof else None
    if record is None and not asof:
        recent = repo.list_recent(limit=1)
        record = recent[0] if recent else None
    render_kw: dict[str, Any] = {}
    sess = "pre"
    if record is None and asof:
        text = _stub_text(asof)
    elif record is None:
        text = _stub_text(asof or "undated")
    else:
        hits_repo = open_hit_repository(hit_db_url) if hit_db_url is not None else open_hit_repository()
        payload = record.payload or {}
        sess = _coerce_session(session, payload)
        rd = _coerce_run_date(run_date, payload)
        notes: list[str] = []
        qd = None
        show = False
        loaded = quotes
        prior = dict(prior_closes or {})
        if not rd:
            notes.append("未提供运行日，未取行情")
        else:
            from .quotes import resolve_quote_date

            qd = resolve_quote_date(date.fromisoformat(rd)).isoformat()
        want_ohlc = ohlc if ohlc is not None else (sess == "post")
        show = bool(want_ohlc and sess == "post" and rd and qd)
        if show and loaded is None:
            symbols = [_sym6(p.get("symbol")) for p in (record.picks or [])]
            pool = (
                ((payload.get("rankings") or {}).get("boards") or {})
                .get("short_term", {})
                .get("pool")
                or []
            )
            symbols.extend(_sym6(it.get("symbol")) for it in pool if isinstance(it, Mapping))
            symbols.append(_BENCHMARK)
            from .quotes import load_ohlc

            cache = Path(cache_dir) if cache_dir is not None else Path("./data/quotes")
            loaded, err = load_ohlc(
                [s for s in symbols if s],
                qd or rd,
                cache_dir=cache,
                allow_network=True,
                fetch=fetch_ohlc,
                selection_asof=record.asof,
            )
            if err:
                notes.append(err)
            if qd == record.asof and not prior:
                from .quotes import load_prior_closes

                prior = load_prior_closes(symbols, record.asof)
        if sess == "pre":
            show = False
        render_kw = {
            "session": sess,
            "run_date": rd,
            "quote_date": qd,
            "show_quotes": show,
            "quotes": loaded,
            "prior_closes": prior,
            "extra_notes": notes,
            "benchmark_name": benchmark_name,
            "benchmark_asof_close": benchmark_asof_close,
        }
        text = build_digest_text(record, hits_repo=hits_repo, **render_kw)

    root = Path(out_dir) if out_dir is not None else Path(DEFAULT_OUT_DIR)
    root.mkdir(parents=True, exist_ok=True)
    target_asof = record.asof if record is not None else (asof or "undated")
    if record is None:
        sess = _coerce_session(session, {})
    # 文件名与标题同一天（报告日期）；asof 只留在正文口径行与 brief 库主键里。
    target_run = _coerce_run_date(
        run_date, (record.payload if record is not None else {}) or {}
    )
    report_day = target_run or target_asof
    session_path = root / f"{report_day}-{sess}.md"
    alias_path = root / f"{report_day}.md"
    latest_path = root / "latest.md"
    latest_session_path = root / f"latest-{sess}.md"
    session_path.write_text(text, encoding="utf-8")
    shutil.copyfile(session_path, alias_path)
    shutil.copyfile(session_path, latest_path)
    shutil.copyfile(session_path, latest_session_path)
    digest_path = session_path

    result: dict[str, Any] = {
        "asof": target_asof,
        "reportDate": report_day,
        "found": record is not None,
        "digestPath": str(digest_path),
        "aliasPath": str(alias_path),
        "latestPath": str(latest_path),
        "session": sess,
    }
    if emit_html:
        env_note = f"环境 {record.environment}" if record is not None else "无该日 brief 存档（stub）"
        gen_note = ""
        if record is not None:
            _g = _human_ts(record.generated_at)
            if _g:
                gen_note = f" · 生成 {_g}"
        _basis = f"（选股基准 {target_asof}）" if report_day != target_asof else ""
        html_title = (
            f"每日简报 · {_SESSION_LABEL.get(sess, sess)} · {report_day}{_basis}"
            if record is not None
            else f"每日简报 · {target_asof}"
        )
        doc = render_report_html(
            text,
            title=html_title,
            subtitle=f"报告日 {report_day} · 选股基准 asof {target_asof} · {env_note}{gen_note}",
            source="数据来源：SQLite brief 仓库（只读）+ 命中追踪 + 绩效 JSONL",
            badge="DAILY DIGEST",
            strip_leading_h1=True,
        )
        html_path = root / f"{report_day}-{sess}.html"
        alias_html = root / f"{report_day}.html"
        latest_html_path = root / "latest.html"
        latest_session_html = root / f"latest-{sess}.html"
        html_path.write_text(doc, encoding="utf-8")
        shutil.copyfile(html_path, alias_html)
        shutil.copyfile(html_path, latest_html_path)
        shutil.copyfile(html_path, latest_session_html)
        result["htmlPath"] = str(html_path)
        result["latestHtmlPath"] = str(latest_html_path)
    if emit_ths:
        codes = _ths_codes(record.picks or []) if record is not None else []
        short_codes = _short_term_codes(record)
        if ths_dir is not None:
            ths_root = Path(ths_dir)
        elif out_dir is not None:
            ths_root = root.parent / "ths_import"
        else:
            ths_root = Path(DEFAULT_THS_DIR)
        ths = write_ths_import(codes, day=report_day, out_dir=ths_root)
        if ths:
            result.update(ths)
        # 短线同样「可直接复制」：另存一份 *_short.txt，与长线池互不混淆。
        short_ths = write_ths_import(
            short_codes, day=report_day, out_dir=ths_root, kind="_short"
        )
        if short_ths:
            result["thsShortPath"] = short_ths["thsPath"]
            result["latestThsShortPath"] = short_ths["latestThsPath"]
            result["thsShortCount"] = short_ths["thsCount"]
        # 二次精选同样落盘：生产榜与二次精选是两套取舍口径，各存一份才不互相覆盖。
        for kind, profile, key in (
            ("_quality_sec", "quality", "QualitySec"),
            ("_short_sec", "short", "ShortSec"),
        ):
            sec = write_ths_import(
                _secondary_codes(record, profile),
                day=report_day,
                out_dir=ths_root,
                kind=kind,
            )
            if sec:
                result[f"ths{key}Path"] = sec["thsPath"]
                result[f"latestThs{key}Path"] = sec["latestThsPath"]
                result[f"ths{key}Count"] = sec["thsCount"]
    return result


__all__ = [
    "DEFAULT_OUT_DIR",
    "DEFAULT_PERF_LOG",
    "DEFAULT_THS_DIR",
    "ENV_PERF_LOG",
    "THS_IMPORT_PER_LINE",
    "build_digest",
    "build_digest_text",
    "performance_summary",
    "write_ths_import",
]
