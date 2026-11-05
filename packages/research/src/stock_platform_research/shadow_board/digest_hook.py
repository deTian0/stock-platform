"""Read-only digest appendix for shadow Final Board (omit when file missing)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ledger import default_shadow_dir


def shadow_board_json_path(
    asof: str,
    *,
    shadow_dir: Path | str | None = None,
) -> Path:
    root = Path(shadow_dir) if shadow_dir is not None else default_shadow_dir()
    day = str(asof or "").strip()[:10]
    return root / f"final_board_{day}.json"


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
    if not board:
        lines.append("_合法空板：硬闸后无入选（不是缺陷）。_")
        lines.append("")
        return lines

    lines.append("| 代码 | 名称 | 学校 | 得分 | 持有期 |")
    lines.append("|------|------|------|------|--------|")
    for row in board:
        if not isinstance(row, dict):
            continue
        score = row.get("score")
        try:
            score_txt = f"{float(score):.3f}"
        except (TypeError, ValueError):
            score_txt = "-"
        lines.append(
            f"| {row.get('code') or '-'} | {row.get('name') or '-'} | "
            f"{row.get('school') or '-'} | {score_txt} | "
            f"{row.get('holdingPeriod') or '-'} |"
        )
    lines.append("")
    lines.append("_本附录不改出厂 picks / 同花顺导入；升级仍须 Y1→Y2。_")
    lines.append("")
    return lines


__all__ = ["render_shadow_board_appendix", "shadow_board_json_path"]
