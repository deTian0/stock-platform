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
    SECTION_EMPTY,
    SECTION_UNAVAILABLE,
    VERDICT_BLOCKED,
    VERDICT_DEGRADED,
    VERDICT_OK,
    append_history,
    collect_loop_health,
    read_history,
    render_loop_health_markdown,
    roll_up_verdict,
    summarize_history,
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
        "briefContinuity": {"status": "ok", "windowDays": 5, "missingDays": []},
        "hits": {"status": "ok", "totalCodeCount": 5, "totalCumulativeHits": 9},
        "performance": {
            "status": "ok",
            "settledCount": 25,
            "minMeaningfulSample": 20,
            "sampleSufficient": True,
        },
        "symbolMaster": {"status": "ok", "total": 5200},
        "opsLedger": {"status": "ok", "failingTasks": [], "taskCount": 3, "totalRuns": 9},
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


@pytest.mark.parametrize("cov_status", ["error", "unconfigured"])
def test_verdict_coverage_error_and_unconfigured_block(cov_status: str) -> None:
    """T1 / v4.9.0 修正：``error``（库不可读）与 ``unconfigured`` 曾被误判为 ok。"""
    verdict = roll_up_verdict(_sections(coverage={"status": cov_status}))
    assert verdict["status"] == VERDICT_BLOCKED
    assert "coverage" in verdict["failed"]
    check = next(c for c in verdict["checks"] if c["id"] == "coverage")
    assert check["level"] == "fail"


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
    for needle in (
        "# 日用循环健康度",
        "## 裁决明细",
        "## 信号明细",
        "## brief 连续性（近 N 个交易日）",
        "## 调度执行台账",
        "## 缺失/异常说明",
    ):
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


# ---------------------------------------------------------------------------
# 9. 趋势台账（T1 / v4.9.0）—— 追加只是锦上添花，摘要含本次、同日去重
# ---------------------------------------------------------------------------


def _collect(tmp_path: Path, asof: str, history_path: Path | None):
    return collect_loop_health(
        db_url=tmp_path / "platform.db",
        market_db=tmp_path / "nope.db",
        perf_log=tmp_path / "missing.jsonl",
        asof=asof,
        history_path=history_path,
    )


def _hist_path(tmp_path: Path) -> Path:
    return tmp_path / "health" / "history.jsonl"


def test_history_empty_then_first_record(tmp_path: Path) -> None:
    hp = _hist_path(tmp_path)
    payload = _collect(tmp_path, "2026-10-10", hp)
    hist = payload["history"]
    assert hist["status"] == SECTION_EMPTY
    assert hist["daysRecorded"] == 0
    assert hist["notOkStreak"] == 1  # 含本次（空库 → blocked）
    assert str(hist["path"]).endswith("history.jsonl")

    result = append_history(payload, hp)
    assert result["appended"] is True
    assert hp.is_file()
    assert len(read_history(hp)) == 1
    rec = read_history(hp)[0]
    assert rec["asof"] == "2026-10-10"
    assert rec["status"] == VERDICT_BLOCKED
    assert rec["failed"] == ["coverage", "latestBrief"]


def test_history_streak_dedupes_same_day(tmp_path: Path) -> None:
    hp = _hist_path(tmp_path)
    for day in ("2026-10-09", "2026-10-12", "2026-10-13"):
        append_history(_collect(tmp_path, day, hp), hp)
    payload = _collect(tmp_path, "2026-10-13", hp)  # 同日重跑
    hist = payload["history"]
    assert hist["daysRecorded"] == 3  # 去重后仍 3 天
    assert hist["notOkStreak"] == 3
    assert len(read_history(hp)) == 3  # 摘要层去重，不重写已落行
    append_history(payload, hp)
    assert len(read_history(hp)) == 4
    assert _collect(tmp_path, "2026-10-13", hp)["history"]["notOkStreak"] == 3


@pytest.mark.parametrize(
    "records,asof,status,degraded,not_ok,since",
    [
        ([], "2026-10-14", "ok", 0, 0, None),
        ([], "2026-10-14", "degraded", 1, 1, "2026-10-14"),
        (
            [{"asof": "2026-10-13", "ts": "1", "status": "ok"}],
            "2026-10-14", "degraded", 1, 1, "2026-10-14",
        ),
        (
            [{"asof": "2026-10-13", "ts": "1", "status": "degraded"}],
            "2026-10-14", "degraded", 2, 2, "2026-10-13",
        ),
        (
            [
                {"asof": "2026-10-12", "ts": "1", "status": "degraded"},
                {"asof": "2026-10-13", "ts": "2", "status": "blocked"},
            ],
            "2026-10-14", "degraded", 1, 3, "2026-10-12",
        ),
        (
            [{"asof": "2026-10-13", "ts": "1", "status": "degraded"}],
            "2026-10-14", "ok", 0, 0, None,
        ),
    ],
)
def test_summarize_history_is_pure_table(
    records: list[dict], asof: str, status: str, degraded: int, not_ok: int, since: str | None
) -> None:
    summary = summarize_history(records, asof=asof, status=status)
    assert summary["degradedStreak"] == degraded
    assert summary["notOkStreak"] == not_ok
    assert summary["streakSince"] == since
    assert summary["recent"][0]["asof"] == asof


def test_append_history_never_raises_on_unwritable_target(tmp_path: Path) -> None:
    as_dir = tmp_path / "as_dir"
    as_dir.mkdir()
    result = append_history({"asof": "2026-10-14", "verdict": {"status": "ok"}}, as_dir)
    assert result["appended"] is False
    assert result["reason"]


def test_append_history_trims_to_max(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(lh, "HISTORY_MAX_RECORDS", 3)
    hp = _hist_path(tmp_path)
    for i in range(5):
        append_history({"asof": f"2026-10-{i + 1:02d}", "verdict": {"status": "ok"}}, hp)
    records = read_history(hp)
    assert len(records) == 3
    assert records[-1]["asof"] == "2026-10-05"  # 保留最近
    assert records[0]["asof"] == "2026-10-03"


def test_read_history_tolerates_junk_lines(tmp_path: Path) -> None:
    hp = _hist_path(tmp_path)
    hp.parent.mkdir(parents=True, exist_ok=True)
    hp.write_text(
        '{"asof":"2026-10-14","status":"ok"}\nnot json\n\n{"nope":1}\n',
        encoding="utf-8",
    )
    records = read_history(hp)
    assert len(records) == 1
    assert records[0]["asof"] == "2026-10-14"


def test_read_history_missing_file_is_empty(tmp_path: Path) -> None:
    assert read_history(tmp_path / "nope" / "history.jsonl") == []


def test_history_failure_is_isolated_from_verdict(monkeypatch, tmp_path: Path) -> None:
    def _boom(*_a, **_k):
        raise RuntimeError("history exploded")

    monkeypatch.setattr(lh, "read_history", _boom)
    payload = _collect(tmp_path, "2026-10-14", _hist_path(tmp_path))
    assert payload["history"]["status"] == SECTION_UNAVAILABLE
    assert "history exploded" in payload["history"]["reason"]
    # 裁决仍只看六路信号
    assert payload["verdict"]["status"] == VERDICT_BLOCKED
    assert payload["verdict"]["failed"] == ["coverage", "latestBrief"]


def test_render_includes_history_trend(tmp_path: Path) -> None:
    hp = _hist_path(tmp_path)
    payload = _collect(tmp_path, "2026-10-14", hp)
    append_history(payload, hp)
    md = render_loop_health_markdown(payload)
    assert "## 趋势（历史台账）" in md
    assert "连续：degraded" in md
    assert "| 时点 | 裁决 | warn |" in md


def test_render_history_unavailable_branch(tmp_path: Path) -> None:
    md = render_loop_health_markdown({"history": {"status": SECTION_UNAVAILABLE, "reason": "炸了"}})
    assert "历史台账不可用" in md


def test_cli_appends_history_unless_disabled(tmp_path: Path) -> None:
    from stock_platform_research.loop_health_cli import main

    out_dir = tmp_path / "health"
    base = [
        "--db", str(tmp_path / "platform.db"),
        "--market-db", str(tmp_path / "nope.db"),
        "--perf-log", str(tmp_path / "missing.jsonl"),
        "--asof", "2026-10-14",
        "--out-dir", str(out_dir),
    ]
    assert main(base) == 0
    hp = out_dir / "history.jsonl"
    assert hp.is_file()
    assert len(read_history(hp)) == 1

    assert main(base) == 0
    assert len(read_history(hp)) == 2  # 台账只追加，不去重（去重在摘要层）
    assert main(base + ["--no-history"]) == 0
    assert len(read_history(hp)) == 2
    assert main(base + ["--no-write"]) == 0
    assert len(read_history(hp)) == 2


# ---------------------------------------------------------------------------
# 10. 调度执行台账 + brief 连续性（T2 / v4.9.1）
# ---------------------------------------------------------------------------


def _trading_days(asof: str, count: int) -> list[str]:
    """``asof``（含）往前 ``count`` 个交易日，**升序**（与 ``_recent_trading_days`` 一致）。"""
    from stock_platform_providers import get_trading_calendar

    cal = get_trading_calendar("CN")
    cursor = date.fromisoformat(asof)
    days: list[str] = []
    while len(days) < count:
        if cal.is_trading_day(cursor):
            days.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    days.reverse()
    return days


def _save_briefs(path: Path, asofs: list[str]) -> None:
    repo = SqliteBriefRepository(path)
    for asof in asofs:
        repo.save(
            {
                "asof": asof,
                "provider": "replay",
                "picks": [{"symbol": "600519"}],
                "environment": "SIMULATE",
            }
        )


def test_section_constants_align_with_ops_ledger() -> None:
    """两个模块各自定义 ``SECTION_*`` 字面量 —— 钉住它们**不漂移**（无循环导入的代价）。"""
    from stock_platform_research import ops_ledger as ol

    assert ol.SECTION_OK == lh.SECTION_OK == "ok"
    assert ol.SECTION_EMPTY == lh.SECTION_EMPTY == "empty"
    assert ol.SECTION_UNAVAILABLE == lh.SECTION_UNAVAILABLE == "unavailable"


def test_brief_continuity_flags_missing_days(tmp_path: Path) -> None:
    """近 5 个交易日只写了 2 天 brief → 缺 3 日，**逐个列出**。"""
    days = _trading_days("2026-10-14", 5)
    db = tmp_path / "platform.db"
    _save_briefs(db, days[-2:])
    payload = collect_loop_health(
        db_url=db,
        market_db=tmp_path / "nope.db",  # 供数不可用 → 窗口锚在体检时点
        perf_log=tmp_path / "missing.jsonl",
        asof="2026-10-14",
        brief_window_days=5,
    )
    bc = payload["briefContinuity"]
    assert bc["status"] == "incomplete"
    assert bc["windowDays"] == 5
    assert bc["missingDays"] == days[:3]
    assert bc["coveredDays"] == days[-2:]
    assert bc["coverageRatio"] == pytest.approx(0.4)
    assert "缺" in bc["reason"]


def test_brief_continuity_all_covered_is_ok(tmp_path: Path) -> None:
    days = _trading_days("2026-10-14", 5)
    db = tmp_path / "platform.db"
    _save_briefs(db, days)
    payload = collect_loop_health(
        db_url=db,
        market_db=tmp_path / "nope.db",
        perf_log=tmp_path / "missing.jsonl",
        asof="2026-10-14",
        brief_window_days=5,
    )
    bc = payload["briefContinuity"]
    assert bc["status"] == "ok"
    assert bc["missingDays"] == []
    assert "reason" not in bc


def test_brief_continuity_calendar_unavailable(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(lh, "_recent_trading_days", lambda *_a, **_k: None)
    payload = lh._collect_brief_continuity(
        tmp_path / "platform.db", end_day="2026-10-14", window_days=5
    )
    assert payload["status"] == SECTION_UNAVAILABLE
    assert "日历" in payload["reason"]


def test_verdict_brief_continuity_missing_warns_not_blocks() -> None:
    verdict = roll_up_verdict(
        _sections(
            briefContinuity={
                "status": "incomplete",
                "windowDays": 5,
                "missingDays": ["2026-10-13", "2026-10-14"],
            }
        )
    )
    assert verdict["status"] == VERDICT_DEGRADED
    assert "briefContinuity" in verdict["warned"]
    assert verdict["failed"] == []


def test_verdict_ops_ledger_unavailable_warns_not_blocks() -> None:
    """台账缺失是**观测面缺口**：fail-closed（不假装 ok）但**不阻断**日用循环。"""
    verdict = roll_up_verdict(_sections(opsLedger={"status": SECTION_UNAVAILABLE}))
    assert verdict["status"] == VERDICT_DEGRADED
    assert verdict["warned"] == ["opsLedger"]
    assert verdict["failed"] == []


def test_verdict_ops_ledger_failing_tasks_warn() -> None:
    verdict = roll_up_verdict(
        _sections(
            opsLedger={
                "status": "ok",
                "taskCount": 3,
                "totalRuns": 9,
                "failingTasks": ["marketdb-backfill"],
            }
        )
    )
    assert verdict["status"] == VERDICT_DEGRADED
    assert verdict["warned"] == ["opsLedger"]
    check = next(c for c in verdict["checks"] if c["id"] == "opsLedger")
    assert "marketdb-backfill" in check["detail"]


def test_ops_ledger_segment_reads_ledger(tmp_path: Path) -> None:
    from stock_platform_research.ops_ledger import record_run

    led = tmp_path / "logs" / "runs.jsonl"
    record_run(task="daily", exit_code=0, path=led)
    payload = collect_loop_health(
        db_url=tmp_path / "platform.db",
        market_db=tmp_path / "nope.db",
        perf_log=tmp_path / "missing.jsonl",
        asof="2026-10-14",
        ops_ledger_path=led,
    )
    ops = payload["opsLedger"]
    assert ops["status"] == "ok"
    assert ops["totalRuns"] == 1
    assert ops["failingTasks"] == []
    assert ops["tasks"][0]["label"] == "盘前选股"


def test_render_includes_continuity_and_ops_blocks(tmp_path: Path) -> None:
    days = _trading_days("2026-10-14", 5)
    db = tmp_path / "platform.db"
    _save_briefs(db, days[-2:])
    from stock_platform_research.ops_ledger import record_run

    led = tmp_path / "logs" / "runs.jsonl"
    record_run(task="marketdb-backfill", exit_code=1, path=led)
    record_run(task="marketdb-backfill", exit_code=1, path=led)
    payload = collect_loop_health(
        db_url=db,
        market_db=tmp_path / "nope.db",
        perf_log=tmp_path / "missing.jsonl",
        asof="2026-10-14",
        ops_ledger_path=led,
    )
    md = render_loop_health_markdown(payload)
    assert "## brief 连续性（近 N 个交易日）" in md
    assert "## 调度执行台账" in md
    for miss in days[:3]:
        assert f"`{miss}`" in md  # 缺日逐个列出
    assert "**2**" in md  # 连续失败 2 次加粗
