"""Offline tests for the user-readable daily digest."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stock_platform_research.daily_digest import (
    build_digest,
    build_digest_text,
    performance_summary,
)
from stock_platform_research.persistence import reset_brief_repository_cache
from stock_platform_research.hit_tracking import reset_hit_repository_cache


BRIEF = {
    "asof": "2026-10-09",
    "provider": "market_db",
    "universeTier": "watch",
    "symbols": ["600519", "000001"],
    "picks": [
        {
            "rank": 1,
            "symbol": "600519",
            "composite_score": 0.8928571428571429,
            "close": 1253.8,
            "reasonSummary": "综合分 0.8929",
        },
        {
            "rank": 2,
            "symbol": "000001",
            "composite_score": 0.75,
            "close": 10.01,
            "reasonSummary": "综合分 0.7500",
        },
    ],
    "universeSize": 30,
    "panelSize": 29,
    "topN": 10,
    "softGates": True,
    "gatesRelaxed": False,
    "environment": "SIMULATE",
    "disclaimer": "Research brief only",
    "generatedAt": "2026-10-11T14:32:41+00:00",
}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCK_PLATFORM_DB_URL", f"sqlite:///{(tmp_path / 'briefs.db').as_posix()}")
    monkeypatch.setenv("STOCK_PLATFORM_PERFORMANCE_LOG", str(tmp_path / "perf.jsonl"))
    reset_brief_repository_cache()
    reset_hit_repository_cache()
    yield tmp_path
    reset_brief_repository_cache()
    reset_hit_repository_cache()


def _save_brief(tmp_path: Path) -> None:
    from stock_platform_research.persistence import open_brief_repository

    open_brief_repository().save(BRIEF, symbols=BRIEF["symbols"])


def test_performance_summary_counts_pending_and_settled(tmp_path, monkeypatch):
    log = tmp_path / "perf.jsonl"
    log.write_text(
        "\n".join(
            [
                json.dumps({"date": "2026-10-09", "symbol": "600519", "pending": True}),
                json.dumps({"date": "2026-10-09", "symbol": "000001", "pending": True}),
                json.dumps({"date": "2026-09-22", "symbol": "600519", "pending": False}),
                "not-json",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("STOCK_PLATFORM_PERFORMANCE_LOG", str(log))
    summary = performance_summary("2026-10-09")
    assert summary["available"] is True
    assert summary["total"] == 3
    assert summary["pending"] == 2
    assert summary["settled"] == 1
    assert summary["asofPending"] == 2


def test_performance_summary_missing_file_is_best_effort(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCK_PLATFORM_PERFORMANCE_LOG", str(tmp_path / "missing.jsonl"))
    summary = performance_summary()
    assert summary == {"available": False}


def test_build_digest_text_contains_picks_and_disclaimer(env):
    from stock_platform_research.persistence import open_brief_repository

    record = open_brief_repository().save(BRIEF, symbols=BRIEF["symbols"])
    text = build_digest_text(record, hits_repo=None)
    assert "# 每日简报 · 2026-10-09" in text
    assert "600519" in text and "0.8929" in text
    assert "非投资建议" in text
    assert "SIMULATE" in text
    assert "绩效台账" in text


def test_build_digest_writes_files_and_latest_pointer(env):
    _save_brief(env)
    result = build_digest(out_dir=env / "digests")
    assert result["found"] is True
    assert result["asof"] == "2026-10-09"
    digest = Path(result["digestPath"])
    latest = Path(result["latestPath"])
    assert digest.is_file() and latest.is_file()
    assert "600519" in digest.read_text(encoding="utf-8")
    assert digest.read_text(encoding="utf-8") == latest.read_text(encoding="utf-8")


def test_build_digest_latest_by_default(env):
    _save_brief(env)
    result = build_digest(out_dir=env / "digests")  # no asof -> latest
    assert result["asof"] == "2026-10-09"


def test_build_digest_stub_when_no_brief(env):
    result = build_digest(asof="2026-01-01", out_dir=env / "digests")
    assert result["found"] is False
    text = Path(result["digestPath"]).read_text(encoding="utf-8")
    assert "未找到该日期的 brief 存档" in text
    assert "600519" not in text


def test_build_digest_includes_hit_report(env):
    _save_brief(env)
    from stock_platform_research.hit_tracking import open_hit_repository, track_brief_hits

    repo = open_hit_repository()
    track_brief_hits(repo, BRIEF, session_type="pre_market")
    result = build_digest(out_dir=env / "digests")
    text = Path(result["digestPath"]).read_text(encoding="utf-8")
    assert "命中追踪" in text
    assert "600519" in text  # appears both in picks and hit table


def test_empty_picks_brief_renders_fail_closed_message(env):
    from stock_platform_research.persistence import open_brief_repository

    brief = dict(BRIEF)
    brief = {**BRIEF, "picks": [], "emptyPicksMessage": "当日无推荐（截面为空）"}
    open_brief_repository().save(brief, symbols=brief["symbols"])
    result = build_digest(out_dir=env / "digests")
    text = Path(result["digestPath"]).read_text(encoding="utf-8")
    assert "当日无推荐" in text
    assert "| # |" not in text


def test_performance_summary_includes_returns_overview(tmp_path, monkeypatch):
    log = tmp_path / "perf.jsonl"
    log.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "date": "2026-09-22",
                        "symbol": "600519",
                        "rating": "Buy",
                        "raw": "+0.38%",
                        "alpha": "+2.41%",
                        "holding": "5d",
                        "pending": False,
                    }
                ),
                json.dumps(
                    {
                        "date": "2026-09-02",
                        "symbol": "000001",
                        "rating": "Buy",
                        "raw": "-1.76%",
                        "alpha": "-7.72%",
                        "holding": "5d",
                        "pending": False,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("STOCK_PLATFORM_PERFORMANCE_LOG", str(log))
    summary = performance_summary("2026-09-22")
    assert summary["settled"] == 2
    ret = summary["returns"]
    assert ret["count"] == 2
    assert ret["winRate"] == pytest.approx(0.5)
    assert ret["best"] == pytest.approx(0.0038)
    assert ret["beatBenchmarkRate"] == pytest.approx(0.5)


def test_digest_renders_returns_overview(env):
    from stock_platform_research.persistence import open_brief_repository

    open_brief_repository().save(BRIEF, symbols=BRIEF["symbols"])
    log = env / "perf.jsonl"
    log.write_text(
        json.dumps(
            {
                "date": "2026-10-09",
                "symbol": "600519",
                "rating": "Buy",
                "raw": "+1.00%",
                "alpha": "+0.50%",
                "holding": "5d",
                "pending": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    record = open_brief_repository().get_by_asof("2026-10-09")
    text = build_digest_text(record, hits_repo=None)
    assert "收益概览" in text
    assert "胜率" in text


def test_digest_has_ths_import_line(env):
    from stock_platform_research.persistence import open_brief_repository

    record = open_brief_repository().save(BRIEF, symbols=BRIEF["symbols"])
    text = build_digest_text(record, hits_repo=None)
    assert "同花顺导入" in text
    seg = text.split("```text", 1)[1].split("```", 1)[0].strip()
    assert seg == "600519 000001"  # bare 6-digit codes, single-space separated


def test_digest_ths_import_chunks_by_five(env):
    from stock_platform_research.persistence import open_brief_repository

    picks = [
        {
            "rank": i,
            "symbol": f"{i:06d}",
            "composite_score": 1.0 - i / 100.0,
            "close": 10.0 + i,
            "reasonSummary": "x",
        }
        for i in range(1, 13)
    ]
    brief = {**BRIEF, "picks": picks, "topN": 12}
    open_brief_repository().save(brief, symbols=brief["symbols"])
    result = build_digest(out_dir=env / "digests")
    text = Path(result["digestPath"]).read_text(encoding="utf-8")
    assert "000001 000002 000003 000004 000005" in text
    assert "000006 000007 000008 000009 000010" in text
    assert "000011 000012" in text


def test_ths_import_strips_exchange_suffix(env):
    from stock_platform_research.persistence import open_brief_repository

    picks = [
        {"rank": 1, "symbol": "600519.SH", "composite_score": 0.9, "close": 1.0,
         "reasonSummary": "x"}
    ]
    brief = {**BRIEF, "picks": picks}
    open_brief_repository().save(brief, symbols=brief["symbols"])
    result = build_digest(out_dir=env / "digests")
    text = Path(result["digestPath"]).read_text(encoding="utf-8")
    seg = text.split("```text", 1)[1].split("```", 1)[0].strip()
    assert seg == "600519"


def test_ths_import_absent_when_no_picks(env):
    from stock_platform_research.persistence import open_brief_repository

    brief = {**BRIEF, "picks": [], "emptyPicksMessage": "当日无推荐（截面为空）"}
    open_brief_repository().save(brief, symbols=brief["symbols"])
    result = build_digest(out_dir=env / "digests")
    text = Path(result["digestPath"]).read_text(encoding="utf-8")
    assert "同花顺导入" not in text
