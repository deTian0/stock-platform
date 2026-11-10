"""Read-only digest appendix for shadow Final Board (omit when file missing).

The appendix answers three questions a reader actually has, and one the old
five-column table never answered at all:

1. **Who got picked** — the Final Board seats.
2. **Why each seat was picked** — ``trigger`` / ``expectation`` /
   ``invalidation`` / ``reasonSource`` per seat.
3. **How the field was narrowed** — Round1 per-school pool sizes (with the
   reason a school returned an empty pool) and the Round2 hard-gate rejections.

Everything here is display-only: it never touches production picks, the
同花顺 import block, or the performance ledger (ADR 0093).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ledger import default_shadow_dir

_FOOTER = "_本附录不改出厂 picks / 同花顺导入；升级仍须 Y1→Y2。_"


def shadow_board_json_path(
    asof: str,
    *,
    shadow_dir: Path | str | None = None,
) -> Path:
    root = Path(shadow_dir) if shadow_dir is not None else default_shadow_dir()
    day = str(asof or "").strip()[:10]
    return root / f"final_board_{day}.json"


def _cell(value: Any, default: str = "-") -> str:
    """One-line, pipe-escaped cell text — tables must never break on newlines."""
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    return text.replace("\n", " ").replace("|", "\\|")


def _score(value: Any) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "-"


def _school_note(payload: dict[str, Any]) -> str:
    """Why a school returned the pool it did — reason first, then profile."""
    reason = payload.get("reason")
    if reason:
        note = _cell(reason)
    else:
        profile = payload.get("profile")
        note = _cell(profile.get("trend")) if isinstance(profile, dict) else "-"
    if payload.get("retired"):
        note = f"{note}（已下线）" if note != "-" else "已下线"
    elif payload.get("advisoryOnly") and "advisory" not in note.lower():
        note = f"{note}（advisory only）" if note != "-" else "advisory only"
    return note


def _school_rows(schools: Any) -> list[str]:
    if not isinstance(schools, dict) or not schools:
        return []
    rows: list[str] = []
    for key in sorted(schools.keys()):
        payload = schools.get(key)
        if not isinstance(payload, dict):
            continue
        candidates = payload.get("candidates")
        count = len(candidates) if isinstance(candidates, list) else 0
        rows.append(
            f"| {payload.get('school') or key} "
            f"| {_cell(payload.get('schoolName'))} "
            f"| {_cell(payload.get('status'))} "
            f"| {count} "
            f"| {_school_note(payload)} |"
        )
    return rows


def _rejected_rows(rejected: Any) -> list[str]:
    if not isinstance(rejected, list):
        return []
    rows: list[str] = []
    for row in rejected:
        if not isinstance(row, dict):
            continue
        rows.append(
            f"| {_cell(row.get('code'))} | {_cell(row.get('name'))} "
            f"| {_cell(row.get('school'))} | {_cell(row.get('reason'))} |"
        )
    return rows


def render_shadow_board_appendix(
    asof: str,
    *,
    shadow_dir: Path | str | None = None,
) -> list[str]:
    """Return markdown lines for a digest appendix, or ``[]`` if snapshot absent.

    Fail-closed: never pads or fabricates a board. Does not touch production
    picks / 同花顺 import semantics.
    """
    path = shadow_board_json_path(asof, shadow_dir=shadow_dir)
    if not path.is_file():
        return []
    try:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []

    board = payload.get("finalBoard") or []
    if not isinstance(board, list):
        board = []
    status = payload.get("status") or "unknown"

    lines = [
        "## 附录 · 影子 Final Board（只读）",
        "",
        f"- 状态：`{status}`；席位 {len(board)}（空板合法）",
        f"- 绩效：excludedFromPerformance="
        f"{payload.get('excludedFromPerformance', True)}；shadowOnly="
        f"{payload.get('shadowOnly', True)}",
        f"- 快照：`{path.as_posix()}`",
        "",
    ]

    school_rows = _school_rows(payload.get("schools"))
    if school_rows:
        lines.append("### Round1 · 各校入池")
        lines.append("")
        lines.append("| 学校 | 名称 | 状态 | 入池 | 说明（为何空池 / 为何参与） |")
        lines.append("|------|------|------|------|------------------------------|")
        lines.extend(school_rows)
        lines.append("")

    round2 = payload.get("round2")
    rejected = round2.get("rejected") if isinstance(round2, dict) else None
    rejected_rows = _rejected_rows(rejected)
    if rejected_rows:
        stats = round2.get("stats") if isinstance(round2, dict) else None
        head = f"### Round2 · 硬闸淘汰（{len(rejected_rows)} 只）"
        if isinstance(stats, dict) and stats.get("input") is not None:
            head += (
                f" — 入闸 {_cell(stats.get('input'))} / 过闸 "
                f"{_cell(stats.get('passed'))}"
            )
        lines.append(head)
        lines.append("")
        lines.append("| 代码 | 名称 | 学校 | 淘汰原因 |")
        lines.append("|------|------|------|----------|")
        lines.extend(rejected_rows)
        lines.append("")

    if not board:
        lines.append("_合法空板：硬闸后无入选（不是缺陷）。_")
        lines.append("")
        lines.append(_FOOTER)
        lines.append("")
        return lines

    lines.append("### 入选席位")
    lines.append("")
    for idx, row in enumerate(board, start=1):
        if not isinstance(row, dict):
            continue
        school = _cell(row.get("school"))
        school_name = row.get("schoolName")
        head = f"**{idx}. {_cell(row.get('code'))} {_cell(row.get('name'))}** · {school}"
        if school_name:
            head += f"（{_cell(school_name)}）"
        head += f" · 得分 {_score(row.get('score'))}"
        lines.append(head)
        lines.append("")
        lines.append(f"- 持有期：{_cell(row.get('holdingPeriod'))}")
        if row.get("industry"):
            lines.append(f"- 行业：{_cell(row.get('industry'))}")
        lines.append(f"- 触发（为什么选）：{_cell(row.get('trigger'))}")
        lines.append(f"- 预期：{_cell(row.get('expectation'))}")
        lines.append(f"- 失效（何时承认选错）：{_cell(row.get('invalidation'))}")
        if row.get("reasonSource"):
            lines.append(f"- 理由来源：`{_cell(row.get('reasonSource'))}`")
        lines.append("")

    lines.append(_FOOTER)
    lines.append("")
    return lines


__all__ = ["render_shadow_board_appendix", "shadow_board_json_path"]
