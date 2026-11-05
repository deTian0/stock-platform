"""Shadow ledger I/O — writes only under the shadow directory."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

ENV_SHADOW_DIR = "STOCK_PLATFORM_SHADOW_DIR"
DEFAULT_SHADOW_DIR = "./local/shadow"

# Production paths that must never be written by this module (test-locked).
FORBIDDEN_BASENAMES = frozenset(
    {
        "recommend_decisions.jsonl",
        "performance_proxy.jsonl",
        "holdings.json",
    }
)


def default_shadow_dir() -> Path:
    raw = (os.environ.get(ENV_SHADOW_DIR) or "").strip()
    if raw:
        return Path(raw)
    return Path.cwd() / "local" / "shadow"


def _assert_shadow_path(path: Path, *, shadow_root: Path) -> None:
    """Refuse writes that escape the shadow root or hit production basenames."""
    name = path.name.lower()
    if name in FORBIDDEN_BASENAMES:
        raise ValueError(f"禁止写入生产账本文件名: {path.name}")
    try:
        path.resolve().relative_to(shadow_root.resolve())
    except ValueError as exc:
        raise ValueError(
            f"影子账本路径必须位于 {shadow_root} 下，拒绝: {path}"
        ) from exc


def write_shadow_ledger(
    payload: Mapping[str, Any],
    *,
    shadow_dir: Path | str | None = None,
    asof: str | None = None,
) -> dict[str, str]:
    """Write ``final_board_{asof}.json`` + append ``final_board.jsonl``.

    Returns absolute path strings for the JSON snapshot and JSONL append file.
    """
    root = Path(shadow_dir) if shadow_dir is not None else default_shadow_dir()
    root.mkdir(parents=True, exist_ok=True)
    day = asof or str(payload.get("asof") or "unknown")
    json_path = root / f"final_board_{day}.json"
    jsonl_path = root / "final_board.jsonl"
    _assert_shadow_path(json_path, shadow_root=root)
    _assert_shadow_path(jsonl_path, shadow_root=root)

    text = json.dumps(dict(payload), ensure_ascii=False, indent=2)
    json_path.write_text(text + "\n", encoding="utf-8")

    board = payload.get("finalBoard") or []
    summary = {
        "schemaVersion": payload.get("schemaVersion", 1),
        "asof": day,
        "status": payload.get("status"),
        "finalCount": len(board) if isinstance(board, list) else 0,
        "excludedFromPerformance": True,
        "shadowOnly": True,
        "snapshot": str(json_path),
    }
    with jsonl_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary, ensure_ascii=False) + "\n")

    return {"json": str(json_path), "jsonl": str(jsonl_path)}


__all__ = [
    "DEFAULT_SHADOW_DIR",
    "ENV_SHADOW_DIR",
    "FORBIDDEN_BASENAMES",
    "default_shadow_dir",
    "write_shadow_ledger",
]
