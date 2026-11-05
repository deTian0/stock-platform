"""S2-P1 daily event/theme snapshot: idempotent, budgeted, fail-soft, PIT-only (no network)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from stock_platform_research.shadow_board.s2_snapshot import (
    BUDGET_LEDGER_NAME,
    collect_s2_snapshot,
    load_s2_snapshot,
    s2_hooks_from_snapshot,
    s2_snapshot_enabled,
    snapshot_path,
)
from stock_platform_research.shadow_board.schools import run_round1, school_s2_theme

ASOF = "2026-11-05"
# 2026-11-05 15:00 Asia/Shanghai
TS_ASOF = 1793862000
# 2026-11-04 15:00 Asia/Shanghai (stale vs ASOF)
TS_PREV = TS_ASOF - 86400


class FakeEm:
    """Mocked EM JSON transport counting logical requests."""

    def __init__(self, *, board_ts: int = TS_ASOF, fail: set[str] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.board_ts = board_ts
        self.fail = fail or set()

    def __call__(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        p = dict(params or {})
        self.calls.append((url, p))
        if "datacenter" in url:
            report = p.get("reportName")
            if report == "RPT_DAILYBILLBOARD_DETAILSNEW":
                if "lhb" in self.fail:
                    raise ConnectionError("lhb down")
                return {
                    "result": {
                        "pages": 1,
                        "data": [
                            {"TRADE_DATE": f"{ASOF} 00:00:00", "SECURITY_CODE": "600519",
                             "SECURITY_NAME_ABBR": "贵州茅台", "EXPLANATION": "涨幅偏离7%",
                             "BILLBOARD_NET_AMT": 1e8},
                        ],
                    }
                }
            if report == "RPT_LIFT_STAGE":
                if "unlock" in self.fail:
                    raise ConnectionError("unlock down")
                return {
                    "result": {
                        "pages": 1,
                        "data": [
                            {"SECURITY_CODE": "000858", "FREE_DATE": "2026-11-20 00:00:00",
                             "FREE_RATIO": 0.12, "FREE_SHARES": 1000.0},
                        ],
                    }
                }
        if "clist" in url:
            if "boards" in self.fail:
                raise ConnectionError("clist down")
            concept = p.get("fs") == "m:90+t:3"
            return {
                "data": {
                    "total": 1,
                    "diff": [
                        {"f3": 2.0, "f12": "BK1001" if concept else "BK0477",
                         "f14": "白酒概念" if concept else "白酒",
                         "f62": 5e8, "f124": self.board_ts,
                         "f128": "测试", "f140": "601318" if concept else "600519"},
                    ],
                }
            }
        raise AssertionError(f"unexpected url {url}")


def _uni() -> list[dict[str, Any]]:
    base = {"amount": 5e7, "rev_chg": -0.05, "rs20": -1.0, "vol20": 0.02, "pct_chg": 1.0}
    return [
        {**base, "code": "600519", "name": "贵州茅台", "industry": "白酒"},
        {**base, "code": "000858", "name": "五粮液", "industry": "白酒"},
        {**base, "code": "601318", "name": "中国平安", "industry": "保险"},
        {**base, "code": "600036", "name": "招商银行", "industry": "银行"},
    ]


def _collect(tmp_path: Path, em: FakeEm, **kw: Any) -> dict[str, Any]:
    return collect_s2_snapshot(
        ASOF, shadow_dir=tmp_path, get_json=em, enabled=True,
        today=date(2026, 11, 5), **kw,
    )


def test_snapshot_written_ok_and_request_count(tmp_path: Path) -> None:
    em = FakeEm()
    snap = _collect(tmp_path, em)
    assert snap["status"] == "ok"
    assert snap["written"] is True
    assert snap["transport"] == "em_get"
    assert len(em.calls) == 4  # lhb + concept + industry + unlock
    assert snap["budget"]["usedThisRun"] == 4
    path = snapshot_path(ASOF, tmp_path)
    assert path.is_file()
    assert path.parent.name == "s2_snapshots"
    assert not list(path.parent.glob("*.tmp"))
    assert load_s2_snapshot(ASOF, tmp_path)["asof"] == ASOF


def test_same_day_rerun_is_idempotent_zero_network(tmp_path: Path) -> None:
    _collect(tmp_path, FakeEm())
    first = snapshot_path(ASOF, tmp_path).read_text(encoding="utf-8")
    em2 = FakeEm()
    again = _collect(tmp_path, em2)
    assert again["reused"] is True and again["written"] is False
    assert em2.calls == []
    assert snapshot_path(ASOF, tmp_path).read_text(encoding="utf-8") == first
    assert len(list((tmp_path / "s2_snapshots").glob("s2_snapshot_*.json"))) == 1


def test_partial_snapshot_refetched_and_overwritten(tmp_path: Path) -> None:
    snap = _collect(tmp_path, FakeEm(fail={"lhb"}))
    assert snap["status"] == "partial"
    assert snap["sources"]["lhb"]["status"] == "failed"
    healed = _collect(tmp_path, FakeEm())
    assert healed["status"] == "ok" and healed["reused"] is False
    assert load_s2_snapshot(ASOF, tmp_path)["status"] == "ok"


def test_all_sources_fail_is_soft(tmp_path: Path) -> None:
    snap = _collect(tmp_path, FakeEm(fail={"lhb", "unlock", "boards"}))
    assert snap["status"] == "failed"
    assert s2_hooks_from_snapshot(snap).keys() == {"s2_snapshot_meta"}


def test_transport_exception_type_never_raises(tmp_path: Path) -> None:
    def boom(url: str, params: Any = None) -> Any:
        raise RuntimeError("em exploded")

    snap = collect_s2_snapshot(ASOF, shadow_dir=tmp_path, get_json=boom, enabled=True)
    assert snap["status"] == "failed"


def test_budget_cap_enforced_across_reruns(tmp_path: Path) -> None:
    em = FakeEm()
    snap = _collect(tmp_path, em, daily_budget=2)
    assert len(em.calls) == 2
    assert snap["budget"]["exceeded"] is True
    assert snap["status"] == "partial"
    statuses = {s["status"] for s in snap["sources"].values()}
    assert "budget_exceeded" in statuses
    ledger = json.loads((tmp_path / "s2_snapshots" / BUDGET_LEDGER_NAME).read_text("utf-8"))
    assert ledger["2026-11-05"] == 2
    # Rerun same day: budget already used → zero further requests.
    em2 = FakeEm()
    again = _collect(tmp_path, em2, daily_budget=2)
    assert em2.calls == []
    assert again["budget"]["usedToday"] == 2


def test_budget_zero_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCK_PLATFORM_S2_EM_BUDGET", "0")
    em = FakeEm()
    snap = _collect(tmp_path, em)
    assert em.calls == []
    assert snap["status"] == "failed"


def test_disabled_without_file_no_network(tmp_path: Path) -> None:
    em = FakeEm()
    snap = collect_s2_snapshot(ASOF, shadow_dir=tmp_path, get_json=em, enabled=False)
    assert snap["status"] == "disabled"
    assert em.calls == []
    assert not snapshot_path(ASOF, tmp_path).exists()


def test_enabled_default_off_under_pytest_and_replay() -> None:
    assert s2_snapshot_enabled(None, env={"PYTEST_CURRENT_TEST": "x"}) is False
    assert s2_snapshot_enabled(None, env={"STOCK_PLATFORM_PROVIDER_PRESET": "replay"}) is False
    assert s2_snapshot_enabled(None, env={}) is True
    assert s2_snapshot_enabled(None, env={"STOCK_PLATFORM_S2_SNAPSHOT": "0"}) is False


def test_hooks_feed_s2_non_empty_pool(tmp_path: Path) -> None:
    snap = _collect(tmp_path, FakeEm())
    hooks = s2_hooks_from_snapshot(snap)
    assert hooks["lhb"] == [{"symbol": "600519"}]
    assert hooks["unlock"][0]["symbol"] == "000858"  # 12% float → soft exclude
    pool = school_s2_theme(_uni(), top_k=5, **hooks)
    assert pool["status"] == "ok"
    codes = {c["code"] for c in pool["candidates"]}
    assert "600519" in codes  # lhb + hot industry
    assert "601318" in codes  # concept lead
    assert "000858" not in codes  # heavy unlock excluded
    assert pool["snapshot"]["status"] == "ok"


def test_stale_board_rank_not_used_pit(tmp_path: Path) -> None:
    snap = _collect(tmp_path, FakeEm(board_ts=TS_PREV))
    assert snap["sources"]["concept_rank"]["status"] == "stale"
    assert snap["sources"]["concept_rank"]["pitOk"] is False
    hooks = s2_hooks_from_snapshot(snap)
    assert "concept_blocks" not in hooks and "sector_fund_flow" not in hooks
    assert "lhb" in hooks


def test_no_snapshot_s2_empty_no_error() -> None:
    pools = run_round1(_uni(), top_k=3)
    assert pools["S2"]["status"] == "empty"
    assert "snapshot" not in pools["S2"]
    meta_only = school_s2_theme(_uni(), s2_snapshot_meta={"status": "failed"})
    assert meta_only["status"] == "empty"
    assert "status=failed" in meta_only["reason"]


def test_daily_hook_injects_snapshot_and_reports(tmp_path: Path) -> None:
    from stock_platform_research.shadow_board.daily_hook import run_shadow_board_daily

    # Pre-land the snapshot (as a production run would); hook reuses it offline.
    _collect(tmp_path, FakeEm())
    out = run_shadow_board_daily(asof=ASOF, panel=_uni(), shadow_dir=tmp_path)
    assert out["ok"] is True
    assert out["s2Snapshot"]["status"] == "ok"
    assert out["s2Snapshot"]["reused"] is True
    assert out["s2Snapshot"]["s2PoolStatus"] == "ok"
    assert out["s2Snapshot"]["s2Candidates"] >= 1
    board = json.loads((tmp_path / f"final_board_{ASOF}.json").read_text("utf-8"))
    assert board["schools"]["S2"]["snapshot"]["status"] == "ok"


def test_daily_hook_without_snapshot_s2_empty(tmp_path: Path) -> None:
    from stock_platform_research.shadow_board.daily_hook import run_shadow_board_daily

    out = run_shadow_board_daily(asof=ASOF, panel=_uni(), shadow_dir=tmp_path)
    assert out["ok"] is True
    assert out["s2Snapshot"]["status"] == "disabled"  # pytest → no network
    assert out["s2Snapshot"]["s2PoolStatus"] == "empty"


def test_daily_hook_snapshot_crash_never_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from stock_platform_research.shadow_board import daily_hook, s2_snapshot

    def boom(*a: Any, **k: Any) -> Any:
        raise RuntimeError("snapshot exploded")

    monkeypatch.setattr(s2_snapshot, "collect_s2_snapshot", boom)
    out = daily_hook.run_shadow_board_daily(asof=ASOF, panel=_uni(), shadow_dir=tmp_path)
    assert out["ok"] is True
    assert out["s2Snapshot"]["status"] == "failed"
    assert out["schools"]["S3"]["status"] == "ok"
