"""loop_health.shadowBoard.s2（S2-P1 前向观测）：只读、最多 warn、永不 fail。"""

from __future__ import annotations

import json
from pathlib import Path

from stock_platform_research.loop_health import (
    _collect_shadow_board,
    render_loop_health_markdown,
    roll_up_verdict,
)


def _seed(root: Path, days: dict[str, tuple[str | None, int]]) -> None:
    """days: asof → (snapshot status or None, S2 candidate count)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "s2_snapshots").mkdir(exist_ok=True)
    lines = []
    for day, (snap, n) in days.items():
        lines.append(json.dumps({"asof": day, "status": "ok", "finalCount": 1}))
        if snap is not None:
            (root / "s2_snapshots" / f"s2_snapshot_{day}.json").write_text(
                json.dumps({"asof": day, "status": snap}), encoding="utf-8"
            )
        pool = {"status": "ok" if n else "empty", "candidates": [{"code": "600519"}] * n}
        (root / f"final_board_{day}.json").write_text(
            json.dumps({"asof": day, "schools": {"S2": pool}}), encoding="utf-8"
        )
    (root / "final_board.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_s2_forward_counts_snapshot_and_non_empty_days(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        {
            "2026-11-04": (None, 0),  # 起算前无快照
            "2026-11-05": ("ok", 3),
            "2026-11-06": ("partial", 0),
        },
    )
    s2 = _collect_shadow_board(tmp_path)["s2"]
    assert s2["status"] == "ok"
    assert s2["windowDays"] == 3
    assert s2["snapshotDays"] == 2
    assert s2["nonEmptyPoolDays"] == 1
    assert s2["nonEmptyPoolRatio"] == round(1 / 3, 4)
    assert s2["latestAsof"] == "2026-11-06"
    assert s2["latestSnapshotStatus"] == "partial"


def test_s2_failed_snapshot_is_warn_not_fail(tmp_path: Path) -> None:
    _seed(tmp_path, {"2026-11-05": ("failed", 0)})
    sb = _collect_shadow_board(tmp_path)
    verdict = roll_up_verdict({"shadowBoard": sb})
    checks = {c["id"]: c for c in verdict["checks"]}
    assert checks["shadowS2Snapshot"]["level"] == "warn"
    # Other sections are absent here (their own fails); shadow ids must never fail.
    assert "shadowS2Snapshot" not in verdict["failed"]
    assert "shadowBoard" not in verdict["failed"]


def test_s2_partial_or_missing_snapshot_adds_no_check(tmp_path: Path) -> None:
    _seed(tmp_path, {"2026-11-05": (None, 0)})
    verdict = roll_up_verdict({"shadowBoard": _collect_shadow_board(tmp_path)})
    assert "shadowS2Snapshot" not in {c["id"] for c in verdict["checks"]}


def test_s2_row_rendered_in_markdown(tmp_path: Path) -> None:
    _seed(tmp_path, {"2026-11-05": ("ok", 2)})
    md = render_loop_health_markdown({"shadowBoard": _collect_shadow_board(tmp_path)})
    assert "影子 S2 快照" in md
