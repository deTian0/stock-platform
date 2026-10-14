"""loop_health：日用循环健康度单点（R3 / v4.7.0）。

锁定四件事：
1. **fail-closed** —— 缺件标 ``unavailable`` / ``empty``，绝不用默认值冒充正常；
2. **永不抛** —— 任意一段炸掉，其余段照常产出，整体仍是 total function；
3. **providers 懒导入** —— 模块顶层零 ``stock_platform_providers`` 依赖；
4. **裁决规则** —— ``roll_up_verdict`` 的 ok/degraded/blocked 词表逐条锁定。

零网络、零真实库：所有 fixture 都建在 ``tmp_path``。
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from stock_platform_research import loop_health as lh
from stock_platform_research.loop_health import (
    VERDICT_BLOCKED,
    VERDICT_DEGRADED,
    VERDICT_OK,
    collect_loop_health,
    render_loop_health_markdown,
    roll_up_verdict,
)
from stock_platform_research.persistence import SqliteBriefRepository
from stock_platform_research.symbol_master import SymbolMasterRepository

# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


def _engine_db_with_coverage(
    path: Path, asof: str, *, min_rows: int = 1, span_days: int = 30
) -> Path:
    """最小引擎库：``daily_price`` 每个窗口内交易日各 ``min_rows`` 行 → coverage=ok。"""
    from stock_platform_providers import get_trading_calendar

    cal = get_trading_calendar("CN")
    expected = cal.last_trading_day(date.fromisoformat(asof))
    start = expected - timedelta(days=span_days)
    rows: list[tuple[str, str, float]] = []
    cursor = start
    while cursor <= expected:
        if cal.is_trading_day(cursor):
            for i in range(min_rows):
                rows.append((f"{i:06d}", cursor.isoformat(), 1.0))
        cursor += timedelta(days=1)

    con = sqlite3.connect(path)
    con.execute("CREATE TABLE daily_price (code TEXT, date TEXT, close REAL)")
    con.executemany("INSERT INTO daily_price VALUES (?,?,?)", rows)
    con.commit()
    con.close()
    return path


def _empty_engine_db(path: Path) -> Path:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE fundamentals (code TEXT, name TEXT)")
    con.commit()
    con.close()
    return path


# ---------------------------------------------------------------------------
# 1. fail-closed：什么都缺
# ---------------------------------------------------------------------------


def test_all_missing_is_blocked_and_never_raises(tmp_path: Path) -> None:
    payload = collect_loop_health(
        db_url=tmp_path / "platform.db",
        market_db=tmp_path / "nope.db",
        perf_log=tmp_path / "missing.jsonl",
        asof="2026-10-14",
    )
    assert payload["environment"] == "SIMULATE"
    assert payload["liveTradingEnabled"] is False
    assert payload["coverage"]["status"] == "unavailable"
    assert payload["latestBrief"]["status"] == "empty"
    assert payload["hits"]["status"] == "empty"
    assert payload["performance"]["status"] == "empty"
    assert payload["symbolMaster"]["status"] == "empty"
    assert payload["verdict"]["status"] == VERDICT_BLOCKED
    assert "coverage" in payload["verdict"]["failed"]


def test_missing_table_reports_missing_table(tmp_path: Path) -> None:
    engine = _empty_engine_db(tmp_path / "market.db")  # 无 daily_price 表
    payload = collect_loop_health(
        db_url=tmp_path / "platform.db",
        market_db=engine,
        perf_log=tmp_path / "missing.jsonl",
        asof="2026-10-14",
    )
    assert payload["coverage"]["status"] == "missing_table"
    assert payload["coverage"]["source"] == "engine_sqlite"
    cov_check = next(c for c in payload["verdict"]["checks"] if c["id"] == "coverage")
    assert cov_check["level"] == "fail"


# ---------------------------------------------------------------------------
# 2. coverage 复用 C2 单点：窗口齐全 → ok
# ---------------------------------------------------------------------------


def test_coverage_ok_when_window_complete(tmp_path: Path) -> None:
    asof = "2026-10-14"
    engine = _engine_db_with_coverage(tmp_path / "market.db", asof, min_rows=1)
    payload = collect_loop_health(
        db_url=tmp_path / "platform.db",
        market_db=engine,
        perf_log=tmp_path / "missing.jsonl",
        asof=asof,
        coverage_min_rows=1,
    )
    cov = payload["coverage"]
    assert cov["status"] == "ok"
    assert cov["latestTradeDate"] == asof
    assert cov["lagTradingDays"] == 0
    cov_check = next(c for c in payload["verdict"]["checks"] if c["id"] == "coverage")
    assert cov_check["level"] == "ok"


# ---------------------------------------------------------------------------
# 3. 有数据时的 happy path
# ---------------------------------------------------------------------------


def test_brief_and_symbol_master_populate(tmp_path: Path) -> None:
    db = tmp_path / "platform.db"
    repo = SqliteBriefRepository(db)
    repo.save(
        {
            "asof": "2026-10-12",
            "provider": "replay",
            "picks": [{"symbol": "600519"}, {"symbol": "000001"}],
            "environment": "SIMULATE",
        }
    )
    SymbolMasterRepository(db).upsert_many(
        [{"code": "600519", "name": "贵州茅台"}, {"code": "000001", "name": "平安银行"}]
    )

    payload = collect_loop_health(
        db_url=db,
        market_db=tmp_path / "nope.db",
        perf_log=tmp_path / "missing.jsonl",
        asof="2026-10-14",
    )
    assert payload["latestBrief"]["status"] == "ok"
    assert payload["latestBrief"]["asof"] == "2026-10-12"
    assert payload["latestBrief"]["pickCount"] == 2
    assert payload["symbolMaster"]["status"] == "ok"
    assert payload["symbolMaster"]["total"] == 2


# ---------------------------------------------------------------------------
# 4. 段隔离：一段炸掉不拖垮整表
# ---------------------------------------------------------------------------


def test_section_failure_is_isolated(monkeypatch, tmp_path: Path) -> None:
    def _boom(*_a, **_k):
        raise RuntimeError("hits exploded")

    monkeypatch.setattr(lh, "_collect_hits", _boom)
    payload = collect_loop_health(
        db_url=tmp_path / "platform.db",
        market_db=tmp_path / "nope.db",
        perf_log=tmp_path / "missing.jsonl",
        asof="2026-10-14",
    )
    assert payload["hits"]["status"] == "unavailable"
    assert "hits exploded" in payload["hits"]["reason"]
    # 其余段照常产出
    assert payload["coverage"]["status"] == "unavailable"
    assert payload["performance"]["status"] == "empty"
    assert payload["symbolMaster"]["status"] == "empty"


# ---------------------------------------------------------------------------
# 5. 裁决规则（纯函数，表驱动）
# ---------------------------------------------------------------------------


def _sections(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "coverage": {"status": "ok", "latestTradeDate": "2026-10-14"},
        "latestBrief": {"status": "ok", "asof": "2026-10-14"},
        "hits": {"status": "ok", "totalCodeCount": 5, "totalCumulativeHits": 9},
        "performance": {
            "status": "ok",
            "settledCount": 25,
            "minMeaningfulSample": 20,
            "sampleSufficient": True,
        },
        "symbolMaster": {"status": "ok", "total": 5200},
    }
    base.update(over)
    return base


def test_verdict_all_green() -> None:
    verdict = roll_up_verdict(_sections())
    assert verdict["status"] == VERDICT_OK
    assert verdict["failed"] == []
    assert verdict["warned"] == []


@pytest.mark.parametrize("cov_status", ["stale", "thin"])
def test_verdict_coverage_stale_or_thin_is_degraded(cov_status: str) -> None:
    verdict = roll_up_verdict(_sections(coverage={"status": cov_status}))
    assert verdict["status"] == VERDICT_DEGRADED
    assert "coverage" in verdict["warned"]


@pytest.mark.parametrize("cov_status", ["unavailable", "missing_table", "empty"])
def test_verdict_coverage_hard_failures_block(cov_status: str) -> None:
    verdict = roll_up_verdict(_sections(coverage={"status": cov_status}))
    assert verdict["status"] == VERDICT_BLOCKED
    assert "coverage" in verdict["failed"]


def test_verdict_brief_lag_warns() -> None:
    verdict = roll_up_verdict(
        _sections(
            coverage={"status": "ok", "latestTradeDate": "2026-10-14"},
            latestBrief={"status": "ok", "asof": "2026-10-09"},
        )
    )
    assert verdict["status"] == VERDICT_DEGRADED
    assert "latestBrief" in verdict["warned"]


def test_verdict_small_sample_warns_not_fails() -> None:
    verdict = roll_up_verdict(
        _sections(
            performance={
                "status": "ok",
                "settledCount": 3,
                "minMeaningfulSample": 20,
                "sampleSufficient": False,
            }
        )
    )
    assert verdict["status"] == VERDICT_DEGRADED
    assert "performance" in verdict["warned"]


def test_verdict_missing_brief_blocks() -> None:
    verdict = roll_up_verdict(_sections(latestBrief={"status": "empty"}))
    assert verdict["status"] == VERDICT_BLOCKED
    assert "latestBrief" in verdict["failed"]


# ---------------------------------------------------------------------------
# 6. 渲染
# ---------------------------------------------------------------------------


def test_render_markdown_has_core_sections(tmp_path: Path) -> None:
    payload = collect_loop_health(
        db_url=tmp_path / "platform.db",
        market_db=tmp_path / "nope.db",
        perf_log=tmp_path / "missing.jsonl",
        asof="2026-10-14",
    )
    md = render_loop_health_markdown(payload)
    for needle in ("# 日用循环健康度", "## 裁决明细", "## 六路信号", "## 缺失/异常说明"):
        assert needle in md
    assert "阻断" in md  # 空库 → blocked


def test_render_handles_empty_payload() -> None:
    md = render_loop_health_markdown({})
    assert isinstance(md, str)
    assert "# 日用循环健康度" in md


# ---------------------------------------------------------------------------
# 7. providers 懒导入（模块顶层零硬依赖）
# ---------------------------------------------------------------------------


def test_providers_imported_lazily_only() -> None:
    src = Path(lh.__file__).read_text(encoding="utf-8")
    hits = [ln for ln in src.splitlines() if "stock_platform_providers" in ln]
    assert hits, "expected at least one lazy providers import"
    assert all(ln[:1].isspace() for ln in hits), (
        "stock_platform_providers must be imported inside functions, never at module top"
    )


# ---------------------------------------------------------------------------
# 8. CLI
# ---------------------------------------------------------------------------


def test_cli_writes_artifacts(tmp_path: Path) -> None:
    from stock_platform_research.loop_health_cli import main

    out_dir = tmp_path / "health"
    rc = main(
        [
            "--db",
            str(tmp_path / "platform.db"),
            "--market-db",
            str(tmp_path / "nope.db"),
            "--perf-log",
            str(tmp_path / "missing.jsonl"),
            "--asof",
            "2026-10-14",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == 0
    assert (out_dir / "loop_health.json").is_file()
    assert (out_dir / "loop_health.md").is_file()


def test_cli_no_write_writes_nothing(tmp_path: Path) -> None:
    from stock_platform_research.loop_health_cli import main

    out_dir = tmp_path / "health"
    rc = main(
        [
            "--db",
            str(tmp_path / "platform.db"),
            "--market-db",
            str(tmp_path / "nope.db"),
            "--perf-log",
            str(tmp_path / "missing.jsonl"),
            "--no-write",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == 0
    assert not out_dir.exists()
