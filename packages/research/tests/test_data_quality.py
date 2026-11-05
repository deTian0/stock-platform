"""T3 — data_quality checks against a fixture SQLite (never production market.db)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from stock_platform_research.data_quality import (
    SECTION_DEGRADED,
    SECTION_OK,
    SECTION_WARN,
    collect_data_quality,
    data_quality_section,
    render_data_quality_markdown,
)
from stock_platform_research.loop_health import roll_up_verdict


def _make_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE daily_price ("
        "code TEXT, date TEXT, open REAL, high REAL, low REAL, "
        "close REAL, vol REAL, pct_chg REAL)"
    )
    # Stock: fraction-scale pct_chg; closes move ~1%.
    rows = []
    close = 10.0
    for i, day in enumerate(
        ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-06", "2026-10-07"]
    ):
        prev = close
        close = prev * 1.01
        rows.append(("600000.SH", day, prev, close, prev, close, 1000.0, 0.01))
    # Benchmark present every day.
    bclose = 100.0
    for day in ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-06", "2026-10-07"]:
        prev = bclose
        bclose = prev * 1.005
        rows.append(("000905.SZ", day, prev, bclose, prev, bclose, 5000.0, 0.5))
    # Dirty SH fund stored as .SZ
    rows.append(("588080.SZ", "2026-10-07", 1.0, 1.0, 1.0, 1.0, 100.0, 0.1))
    # Halt streak
    for day in ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-06", "2026-10-07"]:
        rows.append(("000001.SZ", day, 10.0, 10.0, 10.0, 10.0, 0.0, 0.0))
    # Close jump without adj factor
    rows.append(("600519.SH", "2026-10-06", 100.0, 100.0, 100.0, 100.0, 800.0, 0.0))
    rows.append(("600519.SH", "2026-10-07", 100.0, 140.0, 100.0, 140.0, 800.0, 0.4))
    con.executemany(
        "INSERT INTO daily_price VALUES (?,?,?,?,?,?,?,?)",
        rows,
    )
    con.commit()
    con.close()


def test_collect_five_checks(tmp_path: Path) -> None:
    db = tmp_path / "market.db"
    _make_db(db)
    payload = collect_data_quality(
        market_db=db,
        asof="2026-10-07",
        lookback_days=30,
        sample_codes=50,
        benchmark="000905",
        watch_etfs=("510300", "588080"),
    )
    ids = {c["id"] for c in payload["checks"]}
    assert ids == {"pctScale", "halts", "closeJumps", "dirtyCodes", "coverageGaps"}
    by_id = {c["id"]: c for c in payload["checks"]}
    assert by_id["dirtyCodes"]["status"] == SECTION_WARN
    assert by_id["dirtyCodes"]["dirtyCount"] >= 1
    assert by_id["halts"]["status"] in {SECTION_WARN, SECTION_OK}
    assert by_id["closeJumps"]["suspectCount"] >= 1
    assert by_id["coverageGaps"]["status"] in {SECTION_DEGRADED, SECTION_WARN, SECTION_OK}
    md = render_data_quality_markdown(payload)
    assert "数据质量体检" in md


def test_missing_db_unavailable(tmp_path: Path) -> None:
    payload = collect_data_quality(market_db=tmp_path / "nope.db", asof="2026-10-07")
    assert payload["status"] == "unavailable"
    assert payload["checks"] == []


def test_loop_health_section_never_blocks() -> None:
    section = data_quality_section(
        {
            "status": "degraded",
            "asof": "2026-10-07",
            "checks": [
                {"id": "coverageGaps", "status": "degraded", "detail": "缺基准"},
            ],
        }
    )
    verdict = roll_up_verdict(
        {
            "coverage": {"status": "ok", "latestTradeDate": "2026-10-07"},
            "latestBrief": {"status": "ok", "asof": "2026-10-07"},
            "briefDue": {"asof": "2026-10-07"},
            "briefContinuity": {"status": "ok", "windowDays": 5, "missingDays": []},
            "hits": {"status": "ok", "totalCodeCount": 1, "totalCumulativeHits": 1},
            "performance": {
                "status": "ok",
                "settledCount": 50,
                "sampleSufficient": True,
                "minMeaningfulSample": 20,
            },
            "symbolMaster": {"status": "ok", "total": 10},
            "opsLedger": {"status": "ok", "taskCount": 1, "totalRuns": 1, "failingTasks": []},
            "dataQuality": section,
        }
    )
    assert "dataQuality" in verdict["warned"]
    assert verdict["status"] == "degraded"
    assert "dataQuality" not in verdict["failed"]
