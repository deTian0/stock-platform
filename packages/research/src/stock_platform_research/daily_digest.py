"""User-readable daily digest (markdown) rendered from the brief archive.

The pipeline's outputs (brief.json / SQLite / JSONL) are machine-first. This
module answers the "人能一眼看懂" gap: one markdown file per asof, rendered
from the **authoritative SQLite brief repository** (ADR 0049) — never from a
parallel parse of JSON exports.

Data sources, all read-only:
  - brief:      ``SqliteBriefRepository`` (latest or by asof)
  - hit tracking: ``format_hit_report`` (X3 single point)
  - performance: pending/settled counts from the recommendations JSONL

Outputs ``{out_dir}/{asof}.md`` plus a ``latest.md`` pointer copy. Fail-closed:
no brief found → a stub digest that says so (never fabricated numbers).
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


def _picks_table(picks: list[Mapping[str, Any]]) -> list[str]:
    lines = [
        "| # | 代码 | 名称 | 综合分 | 收盘 | 理由 |",
        "|---|---|---|---|---|---|",
    ]
    for p in picks:
        reason = str(p.get("reasonSummary") or p.get("reason") or "").replace("|", "\\|")
        if len(reason) > 80:
            reason = reason[:77] + "..."
        name = str(p.get("name") or "-").replace("|", "\\|")
        lines.append(
            f"| {p.get('rank', '-')} | {p.get('symbol', '-')} | {name} "
            f"| {_fmt_score(p.get('composite_score'))} "
            f"| {_fmt_price(p.get('close'))} | {reason or '-'} |"
        )
    return lines


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


def _ths_import_section(
    picks: list[Mapping[str, Any]],
    *,
    per_line: int = THS_IMPORT_PER_LINE,
    label: str | None = None,
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
    return out


def write_ths_import(
    codes: list[str],
    *,
    asof: str,
    out_dir: str | Path | None = None,
    kind: str = "",
) -> dict[str, Any] | None:
    """Emit the 同花顺 (THS) watchlist import txt for ``asof``.

    Writes ``{out_dir}/{asof}{kind}.txt`` plus a ``latest{kind}.txt`` pointer
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
    dated = root / f"{asof}{kind}.txt"
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


def _rankings_section(payload: Mapping[str, Any]) -> list[str]:
    rankings = payload.get("rankings") or {}
    boards = rankings.get("boards") or {}
    if not boards:
        return []
    lines = ["## 五榜概览", ""]
    # ③B 明细行来自 holdingsReview（B5 复核结果），本身不带中文名 —— 用 ③A 补。
    name_by_code = {
        str(it.get("symbol") or "").strip(): it.get("name")
        for it in ((boards.get("holdings") or {}).get("items") or [])
        if it.get("name")
    }
    order = [
        ("quality", "②A 质量榜"),
        ("short_term", "②B 短线榜"),
        ("holdings", "③A 持仓"),
        ("actions", "③B 操作建议"),
        ("watchlist", "③C 观察名单"),
    ]
    for slug, label in order:
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
            lines.append(f"### {label}（0 需操作 · {len(review_rows)} 只已复核）")
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

        lines.append(f"### {label}（{len(items)} 条）")
        lines.append("")
        if not items:
            lines.append("_空（fail-closed，不生成占位条目）_")
            lines.append("")
            continue
        if slug == "short_term":
            # 短线与长线一样给出可直接复制的 6 位码块（同花顺导入），不再只有表格。
            lines.extend(_ths_import_section(items, label="短线"))
        lines.append("| # | 代码 | 名称 | 备注 |")
        lines.append("|---|---|---|---|")
        for i, it in enumerate(items[:10], start=1):
            note = str(
                it.get("reason") or it.get("belowMedian") and "低于中位（只读提示）" or ""
            ).replace("|", "\\|")
            lines.append(
                f"| {i} | {it.get('symbol', '-')} | {it.get('name') or '-'} "
                f"| {note[:60] or '-'} |"
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


def build_digest_text(record: BriefRecord, *, hits_repo: Any | None = None) -> str:
    """Render one BriefRecord as the human-readable markdown digest."""
    payload = record.payload or {}
    asof = record.asof
    lines: list[str] = []
    lines.append(f"# 每日简报 · {asof}")
    lines.append("")
    # 口径自证：定时任务（08:30 盘前 / 15:30 盘后）都带 -PrevSession，asof 恒为
    # 「上一交易日收盘截面」—— 当日 K 线要等 18:30 回补后才进市场库。把「数据基准日」
    # 与「本简报实际生成时刻」并列写出，避免 asof 被误读成「报告过期」。
    generated_local = _human_ts(record.generated_at)
    if generated_local:
        lines.append(
            f"> **口径**：数据基准日（asof）**{asof}** —— 取该交易日**收盘截面**；"
            f"本简报生成于 **{generated_local}**。"
            f"盘前/盘后任务取上一交易日收盘（当日 K 线尚未入库），这是设计约定，"
            f"不是数据滞后。"
        )
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
    if payload.get("softGates"):
        lines.append("- 闸门：softGates 开启" + ("（闸门放宽）" if payload.get("gatesRelaxed") else ""))
    _gen_raw = record.generated_at or ""
    if generated_local and _gen_raw and generated_local != _gen_raw:
        lines.append(f"- 生成时间：{generated_local}（存档值 {_gen_raw}）")
    else:
        lines.append(f"- 生成时间：{generated_local or _gen_raw or '-'}")
    lines.append("")

    picks = record.picks or []
    lines.append(f"## 当日推荐 · 长线（{len(picks)} 条）")
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
        lines.extend(_picks_table(picks))
        lines.append("")

    lines.extend(_rankings_section(payload))

    # ---- hit tracking (X3 single point rendering) ----
    if hits_repo is not None:
        lines.append("## 命中追踪")
        lines.append("")
        try:
            lines.append(format_hit_report(hits_repo, asof=asof))
        except Exception as exc:  # pragma: no cover - defensive, digest never crashes
            lines.append(f"_命中追踪暂不可用：{exc}_")
            lines.append("")

    perf = performance_summary(asof)
    lines.append("## 绩效台账")
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
    lines.append(f"*digest 由 `stock-platform-digest` 于 {date.today().isoformat()} 渲染；"
                 "权威数据以 SQLite brief 仓库为准。*")
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
    if record is None and asof:
        text = _stub_text(asof)
    elif record is None:
        text = _stub_text(date.today().isoformat())
    else:
        hits_repo = open_hit_repository(hit_db_url) if hit_db_url is not None else open_hit_repository()
        text = build_digest_text(record, hits_repo=hits_repo)

    root = Path(out_dir) if out_dir is not None else Path(DEFAULT_OUT_DIR)
    root.mkdir(parents=True, exist_ok=True)
    target_asof = (record.asof if record is not None else (asof or date.today().isoformat()))
    digest_path = root / f"{target_asof}.md"
    latest_path = root / "latest.md"
    digest_path.write_text(text, encoding="utf-8")
    shutil.copyfile(digest_path, latest_path)

    result: dict[str, Any] = {
        "asof": target_asof,
        "found": record is not None,
        "digestPath": str(digest_path),
        "latestPath": str(latest_path),
    }
    if emit_html:
        env_note = f"环境 {record.environment}" if record is not None else "无该日 brief 存档（stub）"
        gen_note = ""
        if record is not None:
            _g = _human_ts(record.generated_at)
            if _g:
                gen_note = f" · 生成 {_g}"
        doc = render_report_html(
            text,
            title=f"每日简报 · {target_asof}",
            subtitle=f"数据基准日（asof）{target_asof} · {env_note}{gen_note}",
            source="数据来源：SQLite brief 仓库（只读）+ 命中追踪 + 绩效 JSONL",
            badge="DAILY DIGEST",
        )
        html_path = root / f"{target_asof}.html"
        latest_html_path = root / "latest.html"
        html_path.write_text(doc, encoding="utf-8")
        shutil.copyfile(html_path, latest_html_path)
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
        ths = write_ths_import(codes, asof=target_asof, out_dir=ths_root)
        if ths:
            result.update(ths)
        # 短线同样「可直接复制」：另存一份 *_short.txt，与长线池互不混淆。
        short_ths = write_ths_import(
            short_codes, asof=target_asof, out_dir=ths_root, kind="_short"
        )
        if short_ths:
            result["thsShortPath"] = short_ths["thsPath"]
            result["latestThsShortPath"] = short_ths["latestThsPath"]
            result["thsShortCount"] = short_ths["thsCount"]
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
