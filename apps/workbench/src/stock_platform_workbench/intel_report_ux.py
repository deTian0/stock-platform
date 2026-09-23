"""Intel-report template crosswalk + partial prefill from platform data (MR-3/MR-5).

Never writes to brief SQLite. Never invents market levels / news / US futures.
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_PKG_DIR = Path(__file__).resolve().parent
_TEMPLATE_DIR = _PKG_DIR / "static" / "report-templates"

_WEEKDAY_ZH = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")

KIND_FILES: dict[str, str] = {
    "a-share-preopen": "a-share-preopen.html",
    "a-share-intraday": "a-share-intraday.html",
    "us-preopen": "us-preopen.html",
}

KIND_LABELS: dict[str, str] = {
    "a-share-preopen": "A股盘前",
    "a-share-intraday": "A股盘中",
    "us-preopen": "美股盘前",
}

# Capability gaps that templates expect but product matrix does not fully cover
# as a "market intel board" (honest missing list; do not silent-fill).
_BASE_MISSING: list[dict[str, str]] = [
    {
        "field": "指数点位/涨跌幅/成交额",
        "reason": "矩阵无专用「核心指数看板」产品契约；日K可查个股但禁止用假指数填模板",
    },
    {
        "field": "涨停/跌停/连板/炸板率",
        "reason": "全市场情绪统计未进能力矩阵（延期能力）；不得虚构家数",
    },
    {
        "field": "隔夜美股 / 中概 / 经济日历",
        "reason": "美股盘前叙事依赖 Skill 侧情报；global_* 仅个股日K/实时，非期货日历主链",
    },
    {
        "field": "政策/新闻全文定性",
        "reason": "news 能力为轻量特征，非 LLM 摘要；禁止用 WebSearch 写入 brief SQLite",
    },
]


def list_kinds() -> list[dict[str, str]]:
    return [
        {"kind": k, "label": KIND_LABELS[k], "template": KIND_FILES[k]}
        for k in KIND_FILES
    ]


def template_path(kind: str) -> Path:
    name = KIND_FILES.get(kind)
    if name is None:
        raise ValueError(f"未知情报模板 kind={kind!r}；可选：{', '.join(KIND_FILES)}")
    path = _TEMPLATE_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"模板文件缺失：{path}")
    return path


def _asof_date(asof: date | str | None) -> date | None:
    if asof is None:
        return None
    if isinstance(asof, date):
        return asof
    return date.fromisoformat(str(asof)[:10])


def _fmt_calendar(asof_d: date, *, now: datetime | None = None) -> dict[str, str]:
    tz = ZoneInfo("Asia/Shanghai")
    now = now or datetime.now(tz)
    mmdd = f"{asof_d.month:02d}{asof_d.day:02d}"
    ymd_zh = f"{asof_d.year}年{asof_d.month}月{asof_d.day}日"
    weekday = _WEEKDAY_ZH[asof_d.weekday()]
    hhmm = now.strftime("%H:%M")
    stamp = now.strftime("%Y-%m-%d %H:%M")
    return {
        "MMDD": mmdd,
        "YYYY年M月D日": ymd_zh,
        "星期X": weekday,
        "HH:MM": hhmm,
        "YYYY-MM-DD HH:MM": stamp,
        "昨日日期": asof_d.isoformat(),
    }


def _replace_exact(html_text: str, placeholder_inner: str, value: str) -> tuple[str, bool]:
    token = "{{" + placeholder_inner + "}}"
    if token not in html_text:
        return html_text, False
    return html_text.replace(token, value), True


def _inject_platform_panel(html_text: str, panel_html: str) -> str:
    """Insert platform crosswalk panel after opening wrap when possible."""
    marker = '<div class="wrap">'
    if marker in html_text:
        return html_text.replace(marker, marker + "\n" + panel_html + "\n", 1)
    return panel_html + "\n" + html_text


def _build_panel(
    *,
    kind: str,
    asof_s: str | None,
    brief: dict[str, Any] | None,
    ops: dict[str, Any] | None,
    concept_note: str | None,
) -> str:
    picks = (brief or {}).get("picks") or []
    tier = (brief or {}).get("universeTier") or "—"
    univ = (brief or {}).get("universeSize")
    pick_rows = ""
    for p in picks[:8]:
        sym = html.escape(str(p.get("symbol") or ""))
        score = p.get("composite_score")
        score_s = f"{score:.4f}" if isinstance(score, (int, float)) else "—"
        reason = html.escape(str(p.get("reasonSummary") or p.get("reason") or "")[:120])
        pick_rows += (
            f"<tr><td>{html.escape(str(p.get('rank') or ''))}</td>"
            f"<td>{sym}</td><td>{score_s}</td><td>{reason}</td></tr>"
        )
    if not pick_rows:
        pick_rows = (
            "<tr><td colspan='4'>同日无已存 brief picks（fail-closed；"
            "请先在「今日推荐/向导」生成，或预填时不造假数据）</td></tr>"
        )

    ops_bits = []
    if ops:
        ops_bits.append(f"status={ops.get('status')}")
        ops_bits.append(f"preset={ops.get('providerPreset')}")
        ops_bits.append(f"version={ops.get('version')}")
    ops_line = " · ".join(ops_bits) if ops_bits else "ops health 未注入"

    concept_line = concept_note or "concept_blocks 未拉取或不可用"

    return f"""
<section class="block" id="platform-crosswalk" style="border-color:#4d8dff">
  <h2 class="block-title"><span class="bar"></span>平台数据对照（非 Skill 运行时）</h2>
  <p style="font-size:13px;color:#8b96ab;margin-bottom:10px">
    类型：{html.escape(KIND_LABELS.get(kind, kind))} · asof={html.escape(asof_s or "—")} ·
    宇宙 tier={html.escape(str(tier))} · universeSize={html.escape(str(univ if univ is not None else "—"))} ·
    <strong>不得</strong>将本预填或 WebSearch 写入 brief SQLite。
    跳转：Workbench <a href="#recommend" style="color:#4d8dff">今日推荐</a> /
    <a href="#wizard" style="color:#4d8dff">向导</a> /
    <a href="#intel-report" style="color:#4d8dff">情报报告</a>
  </p>
  <p style="font-size:12px;color:#8b96ab;margin-bottom:8px">ops：{html.escape(ops_line)}</p>
  <p style="font-size:12px;color:#8b96ab;margin-bottom:8px">概念板块：{html.escape(concept_line)}</p>
  <div class="tbl-wrap"><table class="tbl">
    <thead><tr><th>排名</th><th>代码</th><th>综合分</th><th>理由摘要</th></tr></thead>
    <tbody>{pick_rows}</tbody>
  </table></div>
</section>
"""


def _fill_opportunity_from_picks(
    html_text: str, picks: list[dict[str, Any]]
) -> tuple[str, list[str]]:
    """Fill first opportunity-card fields from brief picks when markers exist."""
    filled: list[str] = []
    if not picks:
        return html_text, filled

    first = picks[0]
    sym = str(first.get("symbol") or "")
    summary = str(first.get("reasonSummary") or first.get("reason") or "见平台 brief")
    title = f"平台推荐对照 · {sym}"
    conclusion = f"截面 Top1 {sym}（lvrev brief，非盘面情报定性）：{summary}"

    candidates = [
        ("板块 / 主题方向", title),
        ("结论：明确的方向性判断", conclusion),
        (
            "政策催化 / 隔夜美股映射 / 资金动向 / 消息驱动 —— 写清因果链",
            "数据来源：build_premarket_brief picks（禁止 WebSearch 落库）",
        ),
        (
            "出现什么情况说明该判断不成立",
            "若 brief 同日记录被覆盖或能力不可用，本对照失效；以 Workbench 今日推荐为准",
        ),
    ]
    for inner, value in candidates:
        token = "{{" + inner + "}}"
        if token in html_text:
            html_text = html_text.replace(token, html.escape(value), 1)
            filled.append(inner)
    return html_text, filled


def build_crosswalk(
    *,
    asof: date | str | None,
    brief: dict[str, Any] | None,
) -> dict[str, Any]:
    asof_d = _asof_date(asof)
    asof_s = asof_d.isoformat() if asof_d else (brief or {}).get("asof")
    picks = (brief or {}).get("picks") or []
    return {
        "asof": asof_s,
        "briefPresent": brief is not None,
        "universeTier": (brief or {}).get("universeTier"),
        "universeSize": (brief or {}).get("universeSize"),
        "pickCount": len(picks) if isinstance(picks, list) else 0,
        "provider": (brief or {}).get("provider"),
        "note": (
            "情报报告（HTML 配方/Skill）与 build_premarket_brief（lvrev TopN）并列对照，"
            "非替换；禁止 WebSearch / 预填结果写入 brief SQLite。"
        ),
        "links": {
            "recommend": "#recommend",
            "wizard": "#wizard",
            "intelReport": "#intel-report",
        },
    }


def prefill_intel_report(
    *,
    kind: str,
    asof: date | str | None,
    brief: dict[str, Any] | None = None,
    ops_health: dict[str, Any] | None = None,
    concept_items: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Partial-fill HTML from platform data; leave remaining placeholders intact."""
    if kind not in KIND_FILES:
        raise ValueError(f"未知情报模板 kind={kind!r}；可选：{', '.join(KIND_FILES)}")

    asof_d = _asof_date(asof) or _asof_date((brief or {}).get("asof"))
    asof_s = asof_d.isoformat() if asof_d else None
    raw = template_path(kind).read_text(encoding="utf-8")
    filled: list[dict[str, str]] = []
    missing = [dict(m) for m in _BASE_MISSING]

    if kind == "a-share-intraday":
        missing.append(
            {
                "field": "盘中量能/分时特征/情绪阶段",
                "reason": "缺全市场盘中情绪产品能力；minute/realtime 不可冒充情绪看板",
            }
        )
    if kind == "us-preopen":
        missing.append(
            {
                "field": "美股期货/财报日历/官员表态",
                "reason": "平台无美股情报日历主链；仅保留模板占位，助手 Skill 可另填",
            }
        )

    concept_note = None
    if concept_items:
        tags: list[str] = []
        for item in concept_items[:6]:
            sym = item.get("symbol") or ""
            names = []
            for b in (item.get("boards") or [])[:3]:
                if isinstance(b, dict) and b.get("name"):
                    names.append(str(b["name"]))
            for t in (item.get("concept_tags") or [])[:3]:
                names.append(str(t))
            if names:
                tags.append(f"{sym}:{'/'.join(names[:3])}")
        concept_note = "；".join(tags) if tags else "已请求 concept_blocks，但无可用板块名"
        filled.append(
            {"field": "concept_blocks", "source": "concept_blocks", "value": concept_note[:200]}
        )
    else:
        missing.append(
            {
                "field": "个股概念板块标签",
                "reason": "未注入 concept_blocks（能力不可用、无 picks、或调用失败）",
            }
        )

    panel = _build_panel(
        kind=kind,
        asof_s=asof_s,
        brief=brief,
        ops=ops_health,
        concept_note=concept_note,
    )
    out = _inject_platform_panel(raw, panel)
    filled.append({"field": "platform-crosswalk-panel", "source": "brief+ops", "value": "injected"})

    if asof_d is not None:
        cal = _fmt_calendar(asof_d, now=now)
        for key, val in cal.items():
            out, ok = _replace_exact(out, key, val)
            if ok:
                filled.append({"field": key, "source": "calendar", "value": val})
    else:
        missing.append(
            {
                "field": "报告日期日历字段",
                "reason": "未提供 asof 且无 brief.asof，日期占位符保留",
            }
        )

    if brief and (brief.get("picks") or []):
        n = len(brief["picks"])
        tier = brief.get("universeTier") or "—"
        verdict = (
            f"平台对照：截面日 {asof_s} · 宇宙 {tier} · TopN={n} "
            f"（lvrev brief；非盘面情报定性，详见上方对照表）"
        )
        verdict_patterns = [
            r"\{\{一句话定性今日盘面基调[^}]*\}\}",
            r"\{\{一句话定性今日基调[^}]*\}\}",
            r"\{\{一句话描述当前状态[^}]*\}\}",
        ]
        for pat in verdict_patterns:
            new_out, nsub = re.subn(pat, html.escape(verdict), out, count=1)
            if nsub:
                out = new_out
                filled.append({"field": "verdict", "source": "brief", "value": verdict[:120]})
                break
        out, opp_fields = _fill_opportunity_from_picks(out, list(brief.get("picks") or []))
        for f in opp_fields:
            filled.append({"field": f, "source": "brief.picks", "value": "partial"})
    else:
        missing.append(
            {
                "field": "机会卡 / 核心观点（brief 对照）",
                "reason": "同日无 brief picks；不静默编造机会叙事",
            }
        )

    if ops_health:
        src = (
            f"stock-platform providers · preset={ops_health.get('providerPreset')} · "
            f"status={ops_health.get('status')}"
        )
        out, ok = _replace_exact(out, "东方财富 / 财联社 / 新浪财经 等", src)
        if not ok:
            out, ok = _replace_exact(out, "东方财富 / 财联社 / 同花顺 等", src)
        if not ok:
            out, ok = _replace_exact(out, "金十数据 / 新浪美股 / 富途 等", src)
        if ok:
            filled.append({"field": "数据来源", "source": "ops.health", "value": src})

    remaining = sorted(set(re.findall(r"\{\{[^}]+\}\}", out)))
    crosswalk = build_crosswalk(asof=asof_s, brief=brief)

    return {
        "kind": kind,
        "label": KIND_LABELS[kind],
        "template": KIND_FILES[kind],
        "asof": asof_s,
        "html": out,
        "filled": filled,
        "missing": missing,
        "remainingPlaceholders": remaining,
        "remainingCount": len(remaining),
        "crossWalk": crosswalk,
        "writesBriefSqlite": False,
        "liveTradingEnabled": False,
        "environment": "SIMULATE",
        "disclaimer": (
            "部分预填预览：仅平台已有数据；其余占位保留。"
            "非投资建议；非 Skill 运行时；禁止 WebSearch 写入 brief SQLite。"
        ),
    }
