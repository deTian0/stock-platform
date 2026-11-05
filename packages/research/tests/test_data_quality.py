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


def test_watch_etf_mostly_missing_degrades(tmp_path: Path) -> None:
    """R5-P: ≥半数观察 ETF 整码缺失 → coverageGaps degraded + 中文原因."""
    db = tmp_path / "market.db"
    _make_db(db)
    payload = collect_data_quality(
        market_db=db,
        asof="2026-10-07",
        lookback_days=30,
        benchmark="000905",
        watch_etfs=("510300", "510500", "159915", "159919"),
    )
    gap = next(c for c in payload["checks"] if c["id"] == "coverageGaps")
    assert gap["etfMissingAllCount"] >= 2
    assert gap["status"] == SECTION_DEGRADED
    assert "未回补 ETF" in (gap.get("detail") or "")


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


# --- schema compatibility (real a-stock-engine daily_price has no open/high/low) ---

_DAYS = ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-06", "2026-10-07"]


def _make_engine_schema_db(path: Path, ddl: str, rows: list[tuple]) -> None:
    con = sqlite3.connect(path)
    con.execute(ddl)
    ph = ",".join("?" for _ in rows[0])
    con.executemany(f"INSERT INTO daily_price VALUES ({ph})", rows)
    con.commit()
    con.close()


def _engine_rows() -> list[tuple]:
    rows: list[tuple] = []
    close = 10.0
    for day in _DAYS:
        prev = close
        close = prev * 1.01
        rows.append(("600000.SH", day, close, 0.01, 1000.0, 1e7))
    bclose = 100.0
    for day in _DAYS:
        bclose *= 1.005
        rows.append(("000905.SZ", day, bclose, 0.005, 5000.0, 1e8))
    return rows


_ENGINE_DDL = (
    "CREATE TABLE daily_price (code TEXT, date TEXT, close REAL, "
    "pct_chg REAL, vol REAL, amount REAL)"
)


def test_missing_ohlc_columns_scan_completes(tmp_path: Path) -> None:
    db = tmp_path / "market.db"
    _make_engine_schema_db(db, _ENGINE_DDL, _engine_rows())
    payload = collect_data_quality(
        market_db=db,
        asof="2026-10-07",
        lookback_days=30,
        benchmark="000905",
        watch_etfs=("510300",),
    )
    assert payload["status"] != "unavailable"
    ids = {c["id"] for c in payload["checks"]}
    assert ids == {"pctScale", "halts", "closeJumps", "dirtyCodes", "coverageGaps"}
    # no check may have crashed on the missing columns
    assert all(c["status"] != "unavailable" for c in payload["checks"])
    assert set(payload["missingOptionalColumns"]) == {"open", "high", "low"}
    assert any("open" in n for n in payload["notes"])
    assert payload["sampledRows"] > 0


def test_loop_health_data_quality_not_unavailable_without_open(tmp_path: Path) -> None:
    from stock_platform_research.loop_health import collect_loop_health

    db = tmp_path / "market.db"
    _make_engine_schema_db(db, _ENGINE_DDL, _engine_rows())
    payload = collect_loop_health(
        db_url=tmp_path / "platform.db",
        market_db=db,
        perf_log=tmp_path / "missing.jsonl",
        asof="2026-10-07",
    )
    dq = payload["dataQuality"]
    assert dq["status"] != "unavailable"
    assert dq["checkCount"] == 5
    assert any("open" in n for n in dq["notes"])


def test_volume_alias_and_missing_vol_skips_halts(tmp_path: Path) -> None:
    # 'volume' alias is accepted
    db1 = tmp_path / "alias.db"
    _make_engine_schema_db(
        db1,
        "CREATE TABLE daily_price (code TEXT, date TEXT, close REAL, "
        "pct_chg REAL, volume REAL)",
        [(c, d, cl, p, v) for (c, d, cl, p, v, _a) in _engine_rows()],
    )
    p1 = collect_data_quality(
        market_db=db1, asof="2026-10-07", lookback_days=30, benchmark="000905",
        watch_etfs=("510300",),
    )
    halts = next(c for c in p1["checks"] if c["id"] == "halts")
    assert not halts.get("skipped")
    assert halts["totalRows"] > 0

    # no volume column at all -> halts skipped, not an error
    db2 = tmp_path / "novol.db"
    _make_engine_schema_db(
        db2,
        "CREATE TABLE daily_price (code TEXT, date TEXT, close REAL, pct_chg REAL)",
        [(c, d, cl, p) for (c, d, cl, p, _v, _a) in _engine_rows()],
    )
    p2 = collect_data_quality(
        market_db=db2, asof="2026-10-07", lookback_days=30, benchmark="000905",
        watch_etfs=("510300",),
    )
    halts2 = next(c for c in p2["checks"] if c["id"] == "halts")
    assert halts2["skipped"] is True
    assert "halts" in p2["skippedChecks"]
    assert p2["status"] != "unavailable"


def test_zero_close_does_not_crash_close_jumps(tmp_path: Path) -> None:
    db = tmp_path / "market.db"
    rows = _engine_rows()
    rows.append(("600001.SH", "2026-10-06", 0.0, 0.0, 0.0, 0.0))
    rows.append(("600001.SH", "2026-10-07", 5.0, 0.0, 100.0, 1e5))
    _make_engine_schema_db(db, _ENGINE_DDL, rows)
    payload = collect_data_quality(
        market_db=db, asof="2026-10-07", lookback_days=30, benchmark="000905",
        watch_etfs=("510300",),
    )
    jumps = next(c for c in payload["checks"] if c["id"] == "closeJumps")
    assert jumps["status"] != "unavailable"


def test_missing_required_columns_unavailable_with_reason(tmp_path: Path) -> None:
    db = tmp_path / "market.db"
    _make_engine_schema_db(
        db,
        "CREATE TABLE daily_price (symbol TEXT, trade_date TEXT, close REAL)",
        [("600000.SH", "2026-10-07", 1.0)],
    )
    payload = collect_data_quality(market_db=db, asof="2026-10-07")
    assert payload["status"] == "unavailable"
    assert "missing_columns" in payload["reason"]
    assert "code" in payload["reason"]
    assert payload["checks"] == []
