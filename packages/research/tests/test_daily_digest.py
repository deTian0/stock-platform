"""Offline tests for the user-readable daily digest."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stock_platform_research.daily_digest import (
    build_digest,
    build_digest_text,
    performance_summary,
    write_ths_import,
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
    assert "# 每日简报 · 盘前 · 2026-10-09" in text
    assert "600519" in text and "0.8929" in text
    assert "非投资建议" in text
    assert "SIMULATE" in text
    assert "绩效台账" in text


def test_build_digest_text_title_uses_run_date_with_basis_note(env):
    """标题的日期是运行日（报告服务的那一天），asof 只作选股基准括注。"""
    from stock_platform_research.persistence import open_brief_repository

    record = open_brief_repository().save(BRIEF, symbols=BRIEF["symbols"])
    text = build_digest_text(record, hits_repo=None, session="post", run_date="2026-10-12")
    first = text.splitlines()[0]
    assert first == "# 每日简报 · 盘后 · 2026-10-12（选股基准 2026-10-09）"
    # 同日运行不应出现多余括注
    same = build_digest_text(record, hits_repo=None, session="pre", run_date="2026-10-09")
    assert same.splitlines()[0] == "# 每日简报 · 盘前 · 2026-10-09"


def test_build_digest_names_files_by_run_date(env):
    """文件名跟标题同一天，不再用 asof 命名。"""
    _save_brief_with_rankings()  # 带短线池，才能同时校验 *_short.txt 的命名
    result = build_digest(
        out_dir=env / "digests", session="pre", run_date="2026-10-12", emit_ths=True
    )
    assert result["asof"] == "2026-10-09"
    assert result["reportDate"] == "2026-10-12"
    assert Path(result["digestPath"]).name == "2026-10-12-pre.md"
    assert Path(result["aliasPath"]).name == "2026-10-12.md"
    # 同花顺导入 txt 也按报告日命名，不跟 asof
    assert Path(result["thsPath"]).name == "2026-10-12.txt"
    assert Path(result["thsShortPath"]).name == "2026-10-12_short.txt"


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


def test_build_digest_emits_ths_txt(env):
    _save_brief(env)
    result = build_digest(out_dir=env / "digests", emit_ths=True)
    # default dir = a ths_import **sibling** of the digest dir (mirrors data/digests + data/ths_import)
    ths = Path(result["thsPath"])
    latest = Path(result["latestThsPath"])
    assert ths == env / "ths_import" / "2026-10-09.txt"
    assert ths.is_file() and latest.is_file()
    assert ths.read_text(encoding="utf-8") == "600519\n000001\n"
    assert latest.read_text(encoding="utf-8") == "600519\n000001\n"
    assert result["thsCount"] == 2


def test_build_digest_ths_off_by_default(env):
    _save_brief(env)
    result = build_digest(out_dir=env / "digests")
    assert "thsPath" not in result
    assert not (env / "ths_import").exists()


def test_build_digest_ths_dir_override(env):
    _save_brief(env)
    result = build_digest(out_dir=env / "digests", emit_ths=True, ths_dir=env / "custom_ths")
    assert Path(result["thsPath"]) == env / "custom_ths" / "2026-10-09.txt"


def test_write_ths_import_removes_stale_sel(tmp_path):
    out = tmp_path / "ths_import"
    out.mkdir()
    (out / "old.sel").write_bytes(b"\x00\x00")
    res = write_ths_import(["600519"], day="2026-10-09", out_dir=out)
    assert res is not None
    assert not list(out.glob("*.sel"))
    assert (out / "latest.txt").read_text(encoding="utf-8") == "600519\n"


def test_write_ths_import_none_when_no_codes(tmp_path):
    assert write_ths_import([], day="2026-10-09", out_dir=tmp_path) is None
    assert not (tmp_path / "latest.txt").exists()


def test_digest_cli_emits_ths_by_default(env):
    _save_brief(env)
    from stock_platform_research.daily_digest_cli import main as cli_main

    rc = cli_main(["--out-dir", str(env / "digests"), "--no-html"])
    assert rc == 0
    latest = env / "ths_import" / "latest.txt"
    assert latest.is_file()
    assert latest.read_text(encoding="utf-8") == "600519\n000001\n"


def test_digest_cli_does_not_invent_today_as_run_date(env):
    from datetime import date

    from stock_platform_research.daily_digest_cli import main as cli_main

    _save_brief(env)
    rc = cli_main(["--out-dir", str(env / "digests"), "--no-html", "--no-ths"])
    assert rc == 0
    text = (env / "digests" / "2026-10-09-pre.md").read_text(encoding="utf-8")
    assert "未提供运行日，未取行情" in text
    assert f"运行日 {date.today().isoformat()}" not in text


def test_digest_cli_no_ths_flag(env):
    _save_brief(env)
    from stock_platform_research.daily_digest_cli import main as cli_main

    rc = cli_main(["--out-dir", str(env / "digests"), "--no-html", "--no-ths"])
    assert rc == 0
    assert not (env / "ths_import").exists()


# ---------------------------------------------------------------------------
# 双线代码块：长线（当日推荐）+ 短线（②B 短线榜）都要「可直接复制」
# ---------------------------------------------------------------------------

RANKINGS = {
    "asof": "2026-10-09",
    "counts": {"quality": 1, "short_term": 2, "holdings": 0, "actions": 0, "watchlist": 0},
    "boards": {
        "quality": {
            "key": "②A_质量榜",
            "label": "②A_质量榜",
            "slug": "quality",
            "items": [
                {
                    "rank": 1,
                    "symbol": "600519",
                    "name": "贵州茅台",
                    "composite_score": 0.9,
                    "close": 1253.8,
                    "reasons": [],
                    "reasonSummary": "x",
                }
            ],
        },
        "short_term": {
            "key": "②B_短线榜",
            "label": "②B_短线榜",
            "slug": "short_term",
            "items": [
                {
                    "rank": 1,
                    "symbol": "002392.SZ",
                    "name": "北京利尔",
                    "composite_score": 0.8,
                    "close": 5.0,
                    "reasons": [],
                    "reasonSummary": "y",
                },
                {
                    "rank": 2,
                    "symbol": "002227",
                    "name": "*ST特迅",
                    "composite_score": 0.7,
                    "close": 3.0,
                    "reasons": [],
                    "reasonSummary": "z",
                },
            ],
        },
        "holdings": {"key": "③A_持仓", "slug": "holdings", "items": []},
        "actions": {"key": "③B_操作建议", "slug": "actions", "items": []},
        "watchlist": {"key": "③C_观察名单", "slug": "watchlist", "items": []},
    },
}


def _save_brief_with_rankings() -> None:
    from stock_platform_research.persistence import open_brief_repository

    brief = {**BRIEF, "rankings": RANKINGS}
    open_brief_repository().save(brief, symbols=brief["symbols"])


def test_digest_labels_both_lines_and_short_gets_a_copy_paste_block(env):
    from stock_platform_research.persistence import open_brief_repository

    brief = {**BRIEF, "rankings": RANKINGS}
    record = open_brief_repository().save(brief, symbols=brief["symbols"])
    text = build_digest_text(record, hits_repo=None)

    assert "同花顺导入 · 长线" in text
    assert "同花顺导入 · 短线" in text

    # 短线块落在「②B 短线榜」段落里（不再只有一张表）
    assert text.index("②B 短线榜") < text.index("同花顺导入 · 短线")
    seg = (
        text.split("同花顺导入 · 短线", 1)[1]
        .split("```text", 1)[1]
        .split("```", 1)[0]
        .strip()
    )
    assert seg == "002392 002227"  # 去交易所后缀 + 6 位裸码，一行整块复制


def test_digest_short_block_absent_when_short_board_empty(env):
    from stock_platform_research.persistence import open_brief_repository

    rankings = json.loads(json.dumps(RANKINGS))
    rankings["boards"]["short_term"]["items"] = []
    brief = {**BRIEF, "rankings": rankings}
    record = open_brief_repository().save(brief, symbols=brief["symbols"])
    text = build_digest_text(record, hits_repo=None)
    assert "同花顺导入 · 长线" in text
    assert "同花顺导入 · 短线" not in text


def test_actions_board_shows_hold_verdicts_instead_of_an_empty_line() -> None:
    """③B lists only exit/trim, so an all-hold book used to render as
    "_空（fail-closed）_" — which reads like a data failure rather than the
    actual answer ("3 只全部继续持有"). Render the verdicts instead.
    """
    from stock_platform_research.daily_digest import _rankings_section

    payload = {
        "rankings": {
            "counts": {"quality": 0, "short_term": 0, "holdings": 2, "actions": 0, "watchlist": 0},
            "boards": {
                "quality": {"key": "②A_质量榜", "slug": "quality", "items": []},
                "short_term": {"key": "②B_短线榜", "slug": "short_term", "items": []},
                "holdings": {
                    "key": "③A_持仓",
                    "slug": "holdings",
                    "items": [
                        {"rank": 1, "symbol": "000533", "name": "顺钠股份"},
                        {"rank": 2, "symbol": "588080", "name": "科创板50"},
                    ],
                },
                "actions": {"key": "③B_操作建议", "slug": "actions", "items": []},
                "watchlist": {"key": "③C_观察名单", "slug": "watchlist", "items": []},
            },
            "holdingsReview": {
                "counts": {"exit": 0, "trim": 0, "add": 0, "hold": 2, "pending": 0},
                "rows": [
                    {"code": "000533", "held_days": 10, "ret_pct": -6.98, "action": "hold"},
                    {"code": "588080", "held_days": 3, "ret_pct": -1.63, "action": "hold"},
                ],
            },
        }
    }
    text = "\n".join(_rankings_section(payload))

    assert "## 五、③B 操作建议（0 需操作 · 2 只已复核）" in text
    assert "当日无需减仓：2 只持仓全部继续持有" in text
    # 中文名从 ③A 补全，动作翻成中文
    assert "| 1 | 000533 | 顺钠股份 | 10 | -6.98 | 继续持有 |" in text
    assert "| 2 | 588080 | 科创板50 | 3 | -1.63 | 继续持有 |" in text
    # ③B 段内不得再出现「空」的措辞
    actions_block = text.split("## 五、③B 操作建议")[1].split("\n## ")[0]
    assert "fail-closed" not in actions_block


def test_actions_board_stays_fail_closed_when_every_holding_is_pending() -> None:
    """No price anywhere ⇒ still an explicit fail-closed line, never a fake verdict."""
    from stock_platform_research.daily_digest import _rankings_section

    payload = {
        "rankings": {
            "boards": {
                "quality": {"key": "②A_质量榜", "slug": "quality", "items": []},
                "short_term": {"key": "②B_短线榜", "slug": "short_term", "items": []},
                "holdings": {"key": "③A_持仓", "slug": "holdings", "items": []},
                "actions": {"key": "③B_操作建议", "slug": "actions", "items": []},
                "watchlist": {"key": "③C_观察名单", "slug": "watchlist", "items": []},
            },
            "holdingsReview": {
                "counts": {"exit": 0, "trim": 0, "add": 0, "hold": 0, "pending": 1},
                "rows": [{"code": "000533", "held_days": None, "ret_pct": None, "action": "pending"}],
            },
        }
    }
    actions_block = (
        "\n".join(_rankings_section(payload)).split("## 五、③B 操作建议")[1].split("\n## ")[0]
    )
    assert "fail-closed" in actions_block
    assert "当日无需减仓" not in actions_block


def test_build_digest_emits_short_ths_txt(env):
    _save_brief_with_rankings()
    result = build_digest(out_dir=env / "digests", emit_ths=True)
    ths = Path(result["thsShortPath"])
    latest = Path(result["latestThsShortPath"])
    assert ths == env / "ths_import" / "2026-10-09_short.txt"
    assert ths.read_text(encoding="utf-8") == "002392\n002227\n"
    assert latest.read_text(encoding="utf-8") == "002392\n002227\n"
    assert result["thsShortCount"] == 2
    # 长线 txt 仍只含长线代码，两池互不混淆
    assert Path(result["thsPath"]).read_text(encoding="utf-8") == "600519\n000001\n"


def test_pre_and_post_files_both_remain(env):
    _save_brief(env)
    pre = build_digest(out_dir=env / "digests", session="pre", ohlc=False)
    post = build_digest(out_dir=env / "digests", session="post", ohlc=False)
    pre_path = env / "digests" / "2026-10-09-pre.md"
    post_path = env / "digests" / "2026-10-09-post.md"
    alias = env / "digests" / "2026-10-09.md"
    latest = env / "digests" / "latest.md"
    assert pre_path.is_file() and post_path.is_file()
    assert "盘前" in pre_path.read_text(encoding="utf-8")
    assert "盘后" in post_path.read_text(encoding="utf-8")
    assert alias.read_text(encoding="utf-8") == post_path.read_text(encoding="utf-8")
    assert latest.read_text(encoding="utf-8") == post_path.read_text(encoding="utf-8")
    assert pre["digestPath"].endswith("2026-10-09-pre.md")
    assert post["session"] == "post"


def test_pre_quote_columns_are_blank_without_run_date(env):
    _save_brief(env)
    text = Path(build_digest(out_dir=env / "digests")["digestPath"]).read_text(encoding="utf-8")
    assert "未提供运行日，未取行情" in text
    assert "开盘(—)" in text
    assert "盘后报告补齐" in text


def test_long_reason_is_not_truncated(env):
    from stock_platform_research.persistence import open_brief_repository

    reason = "完整理由" + ("甲" * 80)
    brief = {
        **BRIEF,
        "picks": [{**BRIEF["picks"][0], "reasonSummary": reason}],
    }
    record = open_brief_repository().save(brief, symbols=brief["symbols"])
    text = build_digest_text(record, hits_repo=None)
    assert reason in text
    assert "..." not in text


def test_post_return_uses_external_close_over_asof_close():
    from stock_platform_research.persistence import BriefRecord

    record = BriefRecord(
        id=1,
        asof="2026-10-09",
        provider="market_db",
        universe_tier="watch",
        symbols=["600519"],
        picks=[{"rank": 1, "symbol": "600519", "name": "贵州茅台", "composite_score": 0.9, "close": 100.0, "reasonSummary": "长"}],
        soft_gates=False,
        gates_relaxed=False,
        data_note=None,
        generated_at="2026-10-10T07:30:00+00:00",
        environment="SIMULATE",
        payload={"market": "CN", "universeSize": 1, "panelSize": 1, "topN": 1},
        created_at="",
        updated_at="",
    )
    text = build_digest_text(
        record,
        hits_repo=None,
        session="post",
        run_date="2026-10-10",
        quote_date="2026-10-10",
        show_quotes=True,
        quotes={"600519": {"open": 101.0, "close": 110.0}, "000905": {"open": 10.0, "close": 11.0}},
        benchmark_name="厦门港务",
        benchmark_asof_close=10.0,
    )
    assert "110.00" in text
    assert "+10.00%" in text
    assert "厦门港务" in text
    assert "不能读作指数超额" in text
    assert "跑赢中证500" not in text


def test_same_day_quote_does_not_use_asof_close_as_denominator():
    from stock_platform_research.persistence import BriefRecord

    record = BriefRecord(
        id=1,
        asof="2026-10-09",
        provider="market_db",
        universe_tier="watch",
        symbols=["600519"],
        picks=[{"rank": 1, "symbol": "600519", "name": "贵州茅台", "composite_score": 0.9, "close": 100.0, "reasonSummary": "长"}],
        soft_gates=False,
        gates_relaxed=False,
        data_note=None,
        generated_at=None,
        environment="SIMULATE",
        payload={"market": "CN"},
        created_at="",
        updated_at="",
    )
    text = build_digest_text(
        record,
        hits_repo=None,
        session="post",
        run_date="2026-10-11",
        quote_date="2026-10-09",
        show_quotes=True,
        quotes={"600519": {"open": 90.0, "close": 90.0}},
        prior_closes={"600519": 80.0},
    )
    assert "+12.50%" in text
    assert "-10.00%" not in text


def test_html_has_a_single_h1(env):
    _save_brief(env)
    result = build_digest(out_dir=env / "digests", emit_html=True, session="pre", ohlc=False)
    html = Path(result["htmlPath"]).read_text(encoding="utf-8")
    assert html.count("<h1>") == 1
    assert html.count("</h1>") == 1


def test_action_detail_uses_sellable_counts_and_skips_t1_for_etf():
    from stock_platform_research.daily_digest import _rankings_section

    payload = {
        "market": "CN",
        "rankings": {
            "boards": {
                "quality": {"items": []},
                "short_term": {"items": []},
                "holdings": {"items": []},
                "actions": {
                    "items": [
                        {
                            "symbol": "588080",
                            "name": "科创50ETF",
                            "action": "exit",
                            "suggestQty": 100,
                            "price": 1.2,
                            "suggestAmount": 120,
                            "weightPct": 0.5,
                            "weightAfterPct": 0.0,
                            "reason": "stop_loss(-12.3%)",
                            "ret_pct": -12.3,
                        }
                    ]
                },
                "watchlist": {"items": []},
            },
            "holdingsReview": {
                "exitPolicy": {"stop_loss": 8.0, "take_profit": 0, "min_hold": 45},
                "rows": [
                    {
                        "code": "588080",
                        "asset_class": "etf",
                        "entry_price": 1.4,
                        "price": 1.2,
                        "ret_pct": -12.3,
                        "held_days": 10,
                        "reason": "stop_loss(-12.3%)",
                        "action": "exit",
                    }
                ],
            },
            "positionSizing": {
                "capWeight": 0.2,
                "orders": [
                    {
                        "code": "588080",
                        "available": 100,
                        "unsellable": 50,
                        "heldQty": 150,
                        "weightBefore": 0.5,
                        "weightAfter": 0.0,
                    }
                ],
            },
        },
    }
    text = "\n".join(_rankings_section(payload))
    assert "触发规则" in text
    assert "持有 10 个交易日" in text
    assert "可卖 100 / 持仓 150，不可卖 50" in text
    assert "集中度" in text
    assert "无 T+1 冻结" not in text
    assert "T+1" not in text


def test_build_digest_no_short_ths_when_no_short_board(env):
    _save_brief(env)
    result = build_digest(out_dir=env / "digests", emit_ths=True)
    assert "thsShortPath" not in result
    assert not (env / "ths_import" / "latest_short.txt").exists()


# ---------------------------------------------------------------------------
# 二次精选自己也要「一键导入」：生产榜的代码块与二次精选取舍口径不同
# （②B 尤其如此），只给生产榜的块会逼人手动删改。
# ---------------------------------------------------------------------------

_QUALITY_ROWS = [
    {
        "rank": 1,
        "symbol": "600036.SH",
        "name": "招商银行",
        "composite_score": 0.90,
        "close": 40.0,
        "amount": 8.0e8,
        "rev_chg": -0.101,
        "rs20": -4.1,
        "vol20": 0.0125,
        "reasonSummary": "x",
    },
    {
        "rank": 2,
        "symbol": "601398.SH",
        "name": "工商银行",
        "composite_score": 0.88,
        "close": 6.5,
        "amount": 6.0e8,
        "rev_chg": -0.095,
        "rs20": -3.2,
        "vol20": 0.0118,
        "reasonSummary": "x",
    },
    {
        "rank": 3,
        "symbol": "000488.SZ",
        "name": "ST晨鸣",
        "composite_score": 0.86,
        "close": 1.91,
        "amount": 5.0e8,
        "rev_chg": -0.098,
        "rs20": -5.0,
        "vol20": 0.0124,
        "reasonSummary": "x",
    },
]

_SHORT_POOL = [
    {
        "rank": 1,
        "symbol": "002392.SZ",
        "name": "北京利尔",
        "composite_score": 0.80,
        "close": 5.0,
        "amount": 3.0e7,
        "rev_chg": -0.070,
        "rs20": -4.0,
        "vol20": 0.0168,
        "reasonSummary": "y",
    },
    {
        "rank": 2,
        "symbol": "002227",
        "name": "*ST特迅",
        "composite_score": 0.78,
        "close": 3.0,
        "amount": 2.0e7,
        "rev_chg": -0.060,
        "rs20": -3.0,
        "vol20": 0.0175,
        "reasonSummary": "z",
    },
    {
        "rank": 3,
        "symbol": "600000.SH",
        "name": "浦发银行",
        "composite_score": 0.76,
        "close": 9.0,
        "amount": 4.0e7,
        "rev_chg": -0.083,
        "rs20": -5.2,
        "vol20": 0.0147,
        "reasonSummary": "w",
    },
    {
        "rank": 4,
        "symbol": "601988.SH",
        "name": "中国银行",
        "composite_score": 0.74,
        "close": 4.4,
        "amount": 2.5e7,
        "rev_chg": -0.110,
        "rs20": -6.1,
        "vol20": 0.0131,
        "reasonSummary": "v",
    },
]


def _secondary_block(text: str, label: str) -> list[str]:
    """代码块里的裸码（排序后比较：块内顺序由二次精选得分决定，不是断言点）。"""
    seg = text.split(f"同花顺导入 · {label}", 1)[1].split("```text", 1)[1]
    return sorted(seg.split("```", 1)[0].split())


def _save_brief_with_secondary(env: Path, *, with_pool: bool = True) -> None:
    from stock_platform_research.persistence import open_brief_repository

    rankings = json.loads(json.dumps(RANKINGS))
    rankings["boards"]["quality"]["items"] = _QUALITY_ROWS
    rankings["boards"]["short_term"]["items"] = _SHORT_POOL[:2]
    if with_pool:
        rankings["boards"]["short_term"]["pool"] = _SHORT_POOL
    brief = {**BRIEF, "asof": "2026-10-09", "rankings": rankings}
    open_brief_repository().save(brief, symbols=BRIEF["symbols"])


def test_digest_secondary_lines_get_their_own_copy_paste_blocks(env):
    _save_brief_with_secondary(env)
    from stock_platform_research.persistence import open_brief_repository

    record = open_brief_repository().get_by_asof("2026-10-09")
    text = build_digest_text(record, hits_repo=None)

    # 长线的生产榜 = 「一、今日 Top10」的 picks；②A 二次精选剔 ST 后少一只
    assert _secondary_block(text, "长线") == ["000001", "600519"]
    assert _secondary_block(text, "二次精选（长线）") == ["600036", "601398"]
    # 短线：生产榜 2 只，二次精选从 pool(4) 里剔 ST 后取 3 只
    assert _secondary_block(text, "短线") == ["002227", "002392"]
    assert _secondary_block(text, "二次精选（短线）") == ["002392", "600000", "601988"]
    # 两块都要落在各自榜单段落里，不能串到别的章
    assert text.index("②A 二次精选") < text.index("同花顺导入 · 二次精选（长线）")
    assert text.index("同花顺导入 · 二次精选（长线）") < text.index("②B 短线榜")


def test_digest_secondary_block_absent_when_pool_missing(env):
    """无 pool ⇒ 未做二次精选 ⇒ 不生成短线二次精选块（fail-closed，无占位行）。"""
    _save_brief_with_secondary(env, with_pool=False)
    from stock_platform_research.persistence import open_brief_repository

    record = open_brief_repository().get_by_asof("2026-10-09")
    text = build_digest_text(record, hits_repo=None)
    assert "无候选池，未做二次精选" in text
    assert "同花顺导入 · 二次精选（短线）" not in text
    # 长线二次精选仍出块（quality 榜自带 items，不需要 pool）
    assert "同花顺导入 · 二次精选（长线）" in text


def test_build_digest_emits_secondary_ths_txt(env):
    _save_brief_with_secondary(env)
    result = build_digest(out_dir=env / "digests", emit_ths=True)

    assert Path(result["thsQualitySecPath"]) == env / "ths_import" / "2026-10-09_quality_sec.txt"
    assert sorted(
        Path(result["thsQualitySecPath"]).read_text(encoding="utf-8").split()
    ) == ["600036", "601398"]
    assert result["thsQualitySecCount"] == 2
    assert sorted(
        Path(result["latestThsQualitySecPath"]).read_text(encoding="utf-8").split()
    ) == ["600036", "601398"]

    assert Path(result["thsShortSecPath"]) == env / "ths_import" / "2026-10-09_short_sec.txt"
    assert sorted(
        Path(result["thsShortSecPath"]).read_text(encoding="utf-8").split()
    ) == ["002392", "600000", "601988"]
    # 生产榜的 txt 不受影响，三份文件互不覆盖
    assert (
        env / "ths_import" / "2026-10-09_short.txt"
    ).read_text(encoding="utf-8") == "002392\n002227\n"


def test_secondary_ths_txt_absent_when_nothing_selected(env):
    _save_brief(env)  # 无 rankings
    result = build_digest(out_dir=env / "digests", emit_ths=True)
    assert "thsQualitySecPath" not in result
    assert "thsShortSecPath" not in result

