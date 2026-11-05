"""CLI ``stock-platform-shadow-board`` — multi-strategy shadow Final Board (ADR 0093)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..dotenv import load_dotenv
from .ledger import default_shadow_dir
from .pipeline import run_shadow_board


def _load_universe(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [dict(r) for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict):
        for key in ("universe", "items", "rows", "candidates"):
            block = raw.get(key)
            if isinstance(block, list):
                return [dict(r) for r in block if isinstance(r, dict)]
    raise SystemExit(f"无法解析宇宙 JSON（需 list 或含 universe/items）: {path}")


def _render_summary(payload: dict[str, Any]) -> str:
    board = payload.get("finalBoard") or []
    lines = [
        f"# 影子 Final Board（{payload.get('asof')}）",
        "",
        f"- 状态：`{payload.get('status')}`",
        f"- 席位：{len(board)}（空板合法）",
        f"- 绩效：excludedFromPerformance={payload.get('excludedFromPerformance')}",
        f"- 落盘：{payload.get('ledgerPath') or '（未写）'}",
        "",
    ]
    if not board:
        lines.append("（空板 — 硬闸后无入选，不是缺陷）")
        return "\n".join(lines)
    lines.append("| 代码 | 名称 | 学校 | 得分 | 持有期 |")
    lines.append("|------|------|------|------|--------|")
    for row in board:
        lines.append(
            f"| {row.get('code')} | {row.get('name')} | {row.get('school')} | "
            f"{float(row.get('score') or 0):.3f} | {row.get('holdingPeriod')} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(
        prog="stock-platform-shadow-board",
        description=(
            "多策略影子 Final Board（五校 → 硬 Round2 → 仅写 local/shadow/）。"
            "不改出厂 picks / 主绩效；SIMULATE only。"
        ),
    )
    p.add_argument("--asof", default=None, help="锚定日 YYYY-MM-DD（默认今天）")
    p.add_argument(
        "--universe",
        type=Path,
        default=None,
        help="截面宇宙 JSON（list 或 {universe:[]}）；缺省=空宇宙→合法空板",
    )
    p.add_argument("--top-k", type=int, default=8, help="每校 Round1 上限（默认 8）")
    p.add_argument(
        "--shadow-dir",
        type=Path,
        default=None,
        help="影子目录（默认 STOCK_PLATFORM_SHADOW_DIR 或 ./local/shadow）",
    )
    p.add_argument("--no-write", action="store_true", help="只打印，不落盘")
    p.add_argument(
        "--enable-advisory-b",
        action="store_true",
        help="启用集 B 顾问占位（仍不可覆盖硬闸）",
    )
    p.add_argument("--json-out", type=Path, default=None, help="额外写一份 payload JSON")
    p.add_argument("--quiet", action="store_true", help="少打 Markdown 摘要")
    args = p.parse_args(argv)

    universe = _load_universe(args.universe)
    payload = run_shadow_board(
        universe,
        asof=args.asof,
        top_k=args.top_k,
        shadow_dir=args.shadow_dir or default_shadow_dir(),
        write=not args.no_write,
        enable_advisory_b=args.enable_advisory_b,
        llm_path=False,
    )

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if not args.quiet:
        print(_render_summary(payload))
    print(
        f"shadow-board status={payload.get('status')} "
        f"final={len(payload.get('finalBoard') or [])} "
        f"ledger={payload.get('ledgerPath')}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
