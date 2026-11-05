"""loop_health 的 shadowBoard 段（ADR 0093 增补）：opt-in、永不 fail、只读。"""

from __future__ import annotations

import json
from pathlib import Path

from stock_platform_research.loop_health import (
    SECTION_DISABLED,
    VERDICT_BLOCKED,
    _collect_shadow_board,
    collect_loop_health,
    render_loop_health_markdown,
    roll_up_verdict,
)


def _write_jsonl(root: Path, rows: list[dict]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "final_board.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def test_shadow_disabled_when_no_ledger(tmp_path: Path) -> None:
    sec = _collect_shadow_board(tmp_path / "nope")
    assert sec["status"] == SECTION_DISABLED
    assert sec["excludedFromPerformance"] is True


def test_shadow_ok_counts_empty_board_ratio(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path,
        [
            {"asof": "2026-11-02", "status": "ok", "finalCount": 0},
            {"asof": "2026-11-03", "status": "ok", "finalCount": 3},
            {"asof": "2026-11-04", "status": "degraded", "finalCount": 0},
        ],
    )
    sec = _collect_shadow_board(tmp_path)
    assert sec["status"] == "ok"
    assert sec["latestAsof"] == "2026-11-04"
    assert sec["daysRecorded"] == 3
    assert sec["emptyBoardDays"] == 2
    assert sec["emptyBoardRatio"] == round(2 / 3, 4)
    assert sec["failedDays"] == []


def test_shadow_same_day_rerun_last_wins_and_bad_lines_skipped(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "final_board.jsonl").write_text(
        "not-json\n"
        + json.dumps({"asof": "2026-11-04", "status": "ok", "finalCount": 0})
        + "\n"
        + json.dumps({"asof": "2026-11-04", "status": "ok", "finalCount": 2})
        + "\n",
        encoding="utf-8",
    )
    sec = _collect_shadow_board(tmp_path)
    assert sec["daysRecorded"] == 1
    assert sec["latestFinalCount"] == 2


def test_shadow_failed_latest_is_warn_not_blocked() -> None:
    sections = {
        "shadowBoard": {
            "status": "warn",
            "latestAsof": "2026-11-04",
            "reason": "最近一次影子终榜失败（status=error）",
        }
    }
    verdict = roll_up_verdict(sections)
    checks = {c["id"]: c for c in verdict["checks"]}
    assert checks["shadowBoard"]["level"] == "warn"
    assert "shadowBoard" in verdict["warned"]
    assert "shadowBoard" not in verdict["failed"]


def test_shadow_disabled_adds_no_check() -> None:
    verdict = roll_up_verdict({"shadowBoard": {"status": SECTION_DISABLED}})
    assert "shadowBoard" not in {c["id"] for c in verdict["checks"]}


def test_collect_loop_health_includes_shadow_section_and_never_blocks(
    tmp_path: Path,
) -> None:
    shadow = tmp_path / "shadow"
    _write_jsonl(shadow, [{"asof": "2026-11-04", "status": "error", "finalCount": 0}])
    payload = collect_loop_health(
        db_url=tmp_path / "platform.db",
        market_db=tmp_path / "nope.db",
        perf_log=tmp_path / "missing.jsonl",
        asof="2026-11-04",
        shadow_dir=shadow,
    )
    assert payload["shadowBoard"]["status"] == "warn"
    assert "shadowBoard" not in payload["verdict"]["failed"]
    assert payload["verdict"]["status"] == VERDICT_BLOCKED  # 其它段缺件所致，非影子链
    assert "影子终榜" in render_loop_health_markdown(payload)


def test_collect_loop_health_shadow_default_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STOCK_PLATFORM_SHADOW_DIR", str(tmp_path / "empty_shadow"))
    payload = collect_loop_health(
        db_url=tmp_path / "platform.db",
        market_db=tmp_path / "nope.db",
        perf_log=tmp_path / "missing.jsonl",
        asof="2026-11-04",
    )
    assert payload["shadowBoard"]["status"] == SECTION_DISABLED
    assert "shadowBoard" not in {c["id"] for c in payload["verdict"]["checks"]}
