"""Shadow Final Board forward performance ledger — isolation + A/B metrics (ADR 0093)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_platform_research.shadow_board.performance import (
    SHADOW_PERF_FILENAME,
    board_to_pending,
    default_shadow_perf_path,
    log_shadow_board,
    settle_shadow_ledger,
    shadow_performance_summary,
)


def _board_payload(asof: str = "2026-09-01") -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "asof": asof,
        "status": "ok",
        "finalBoard": [
            {
                "code": "600519",
                "name": "贵州茅台",
                "school": "S3",
                "score": 0.81,
                "holdingPeriod": "10–20 交易日",
            },
            {
                "code": "300750",
                "name": "宁德时代",
                "school": "S4",
                "score": 0.64,
                "holdingPeriod": "2–5 交易日",
            },
        ],
        "advisoryB": {
            "status": "experimental",
            "rankedCodes": ["300750", "600519"],
            "rankHints": [
                {"code": "300750", "advisoryScore": 0.70, "note": "x"},
                {"code": "600519", "advisoryScore": 0.55, "note": "x"},
            ],
        },
        "excludedFromPerformance": True,
        "shadowOnly": True,
    }


def test_board_to_pending_carries_set_a_and_set_b() -> None:
    rows = board_to_pending(_board_payload())
    assert len(rows) == 2
    by_code = {r["symbol"]: r for r in rows}
    row = by_code["600519"]
    assert row["pending"] is True
    assert row["rating"] == "Buy"
    assert row["setA"] == {"arbiter": "set_a", "passed": True}
    assert row["setB"]["advisoryRank"] == 2  # second in rankedCodes
    assert row["setB"]["advisoryScore"] == 0.55
    assert row["excludedFromPerformance"] is True
    assert row["shadowOnly"] is True

    row2 = by_code["300750"]
    assert row2["setB"]["advisoryRank"] == 1
    assert row2["setB"]["advisoryScore"] == 0.70


def test_board_to_pending_empty_board_yields_nothing() -> None:
    payload = {"asof": "2026-09-01", "finalBoard": []}
    assert board_to_pending(payload) == []


def test_log_shadow_board_writes_only_under_shadow_dir_and_is_idempotent(
    tmp_path: Path,
) -> None:
    prod_marker = tmp_path / "recommend_decisions.jsonl"
    prod_marker.write_text("DO_NOT_TOUCH\n", encoding="utf-8")
    shadow_dir = tmp_path / "shadow"

    appended = log_shadow_board(_board_payload(), shadow_dir=shadow_dir)
    assert len(appended) == 2
    perf_path = default_shadow_perf_path(shadow_dir)
    assert perf_path == shadow_dir / SHADOW_PERF_FILENAME
    assert perf_path.is_file()
    assert prod_marker.read_text(encoding="utf-8") == "DO_NOT_TOUCH\n"

    # Re-logging the same asof appends nothing (dedup on date+symbol).
    again = log_shadow_board(_board_payload(), shadow_dir=shadow_dir)
    assert again == []
    lines = perf_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_settle_shadow_ledger_uses_shared_window_and_isolated_metrics(
    tmp_path: Path,
) -> None:
    shadow_dir = tmp_path / "shadow"
    log_shadow_board(_board_payload(asof="2026-09-01"), shadow_dir=shadow_dir)

    bars_by_symbol = {
        "600519": [
            {"date": "2026-09-01", "close": 100.0},
            {"date": "2026-09-02", "close": 101.0},
            {"date": "2026-09-03", "close": 102.0},
            {"date": "2026-09-04", "close": 103.0},
            {"date": "2026-09-05", "close": 104.0},
            {"date": "2026-09-08", "close": 110.0},  # +10% after 5 sessions
        ],
        "300750": [
            {"date": "2026-09-01", "close": 50.0},
            {"date": "2026-09-02", "close": 49.0},
            {"date": "2026-09-03", "close": 48.0},
            {"date": "2026-09-04", "close": 47.0},
            {"date": "2026-09-05", "close": 46.0},
            {"date": "2026-09-08", "close": 45.0},  # -10% after 5 sessions
        ],
    }

    def get_daily(symbols, *, start, end):
        out = []
        for sym in symbols:
            out.extend(bars_by_symbol.get(sym, []))
        return out

    summary = settle_shadow_ledger(
        shadow_dir=shadow_dir, get_daily=get_daily, alpha_available=False
    )
    assert summary["settledNewly"] == 2
    assert summary["settledCount"] == 2
    assert summary["shadowOnly"] is True
    assert summary["excludedFromPerformance"] is True
    assert summary["notMixedWithMain"] is True
    assert summary["setA"]["metrics"]["count"] == 2
    assert "S3" in summary["setA"]["bySchool"]
    assert "S4" in summary["setA"]["bySchool"]
    # Set B: 600519 ranked 2nd/worse advisory score but +10%; 300750 ranked 1st but -10%.
    set_b = summary["setB"]
    assert set_b["available"] is True
    assert set_b["topHalfCount"] >= 1


def test_shadow_performance_summary_empty_log_is_fail_closed(tmp_path: Path) -> None:
    summary = shadow_performance_summary(shadow_dir=tmp_path / "shadow")
    assert summary["totalEntries"] == 0
    assert summary["settledCount"] == 0
    assert summary["sampleSufficient"] is False
    assert summary["setB"]["available"] is False


def test_log_shadow_board_refuses_forbidden_path(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError, match="禁止写入生产账本"):
        log_shadow_board(
            _board_payload(), path=tmp_path / "recommend_decisions.jsonl"
        )


def test_daily_hook_appends_shadow_ledger_isolated(tmp_path: Path) -> None:
    from stock_platform_research.shadow_board.daily_hook import run_shadow_board_daily

    panel = [
        {"symbol": "600519", "close": 100.0, "amount": 5e8, "rev_chg": -0.10, "rs20": 1.0, "vol20": 0.02, "pct_chg": 1.0},
        {"symbol": "000858", "close": 50.0, "amount": 4e8, "rev_chg": -0.09, "rs20": 0.8, "vol20": 0.02, "pct_chg": 1.0},
        {"symbol": "600036", "close": 30.0, "amount": 3e8, "rev_chg": -0.05, "rs20": 0.5, "vol20": 0.015, "pct_chg": 0.5},
    ]
    names = {"600519": "贵州茅台", "000858": "五粮液", "600036": "招商银行"}
    shadow = tmp_path / "shadow"
    out = run_shadow_board_daily(asof="2026-09-01", panel=panel, name_map=names, shadow_dir=shadow)
    assert out["ok"] is True
    assert out["performanceLedger"]["ok"] is True
    perf = shadow / SHADOW_PERF_FILENAME
    if out["finalCount"]:
        assert perf.is_file()
        assert out["performanceLedger"]["logged"] == out["finalCount"]
    # Production ledger never created.
    assert not (shadow / "recommend_decisions.jsonl").exists()
    again = run_shadow_board_daily(asof="2026-09-01", panel=panel, name_map=names, shadow_dir=shadow)
    assert again["performanceLedger"]["logged"] == 0  # idempotent on (date, symbol)


def test_cli_perf_summary_read_only(tmp_path: Path, capsys) -> None:
    from stock_platform_research.shadow_board.cli import main

    shadow = tmp_path / "shadow"
    log_shadow_board(_board_payload(), shadow_dir=shadow)
    assert main(["--perf-summary", "--shadow-dir", str(shadow)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["totalEntries"] == 2
    assert data["pendingCount"] == 2
    assert data["notMixedWithMain"] is True
    assert not (shadow / "final_board.jsonl").exists()  # summary does not run the board
