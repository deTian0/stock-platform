"""X3 hit tracking — cycle rule, dedup, three cumulative queries (zero network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from stock_platform_research.hit_tracking import (
    POST_MARKET,
    PRE_MARKET,
    HitTrackingConfig,
    SqliteHitTrackingRepository,
    apply_hit,
    format_hit_report,
    hit_tracking_snapshot,
    norm_hit_code,
    track_brief_hits,
)


@pytest.fixture()
def repo(tmp_path: Path) -> SqliteHitTrackingRepository:
    return SqliteHitTrackingRepository(tmp_path / "hits.db")


def _rec(repo, code, day, *, session=PRE_MARKET, name=None, category=None):
    return repo.record(
        code=code, session_type=session, pick_date=day, name=name, category=category
    )


# ---------------------------------------------------------------------------
# pure rule (single definition)
# ---------------------------------------------------------------------------


def test_first_hit_starts_a_cycle() -> None:
    state, is_start = apply_hit(
        None, code="600519", name="贵州茅台", session_type=PRE_MARKET, pick_date="2026-09-01"
    )
    assert is_start is True
    assert state["cumulative_hits"] == 1
    assert state["active_cycle_id"] == "2026-09-01"
    assert state["active_cycle_start"] == "2026-09-01"
    assert state["active_cycle_end"] == "2026-09-15"  # +14 calendar days
    assert state["active_cycle_hits"] == 1
    assert state["total_cycles"] == 1


def test_in_window_rehit_slides_the_window() -> None:
    base, _ = apply_hit(
        None, code="600519", name="x", session_type=PRE_MARKET, pick_date="2026-09-01"
    )
    state, is_start = apply_hit(
        base, code="600519", name="x", session_type=PRE_MARKET, pick_date="2026-09-10"
    )
    assert is_start is False
    assert state["cumulative_hits"] == 2
    assert state["active_cycle_hits"] == 2
    assert state["total_cycles"] == 1
    assert state["active_cycle_id"] == "2026-09-01"  # cycle identity unchanged
    assert state["active_cycle_end"] == "2026-09-24"  # 09-10 + 14 (slid)
    assert state["last_pick_date"] == "2026-09-10"


def test_rehit_exactly_on_cycle_end_is_in_window() -> None:
    base, _ = apply_hit(
        None, code="600519", name="x", session_type=PRE_MARKET, pick_date="2026-09-01"
    )
    state, is_start = apply_hit(
        base, code="600519", name="x", session_type=PRE_MARKET, pick_date="2026-09-15"
    )
    assert is_start is False  # pd <= cycle_end counts as inside
    assert state["active_cycle_hits"] == 2


def test_rehit_after_window_starts_a_new_cycle() -> None:
    base, _ = apply_hit(
        None, code="600519", name="x", session_type=PRE_MARKET, pick_date="2026-09-01"
    )
    state, is_start = apply_hit(
        base, code="600519", name="x", session_type=PRE_MARKET, pick_date="2026-09-16"
    )
    assert is_start is True
    assert state["cumulative_hits"] == 2
    assert state["active_cycle_hits"] == 1
    assert state["total_cycles"] == 2
    assert state["active_cycle_id"] == "2026-09-16"
    assert state["active_cycle_end"] == "2026-09-30"


def test_cycle_calendar_days_is_configurable() -> None:
    cfg = HitTrackingConfig(cycle_calendar_days=7)
    state, _ = apply_hit(
        None,
        code="000001",
        name=None,
        session_type=PRE_MARKET,
        pick_date="2026-09-01",
        config=cfg,
    )
    assert state["active_cycle_end"] == "2026-09-08"


# ---------------------------------------------------------------------------
# repository behavior
# ---------------------------------------------------------------------------


def test_same_day_same_session_dedup(repo: SqliteHitTrackingRepository) -> None:
    first = _rec(repo, "600519", "2026-09-01")
    assert first is not None and first["cumulative"] == 1
    again = _rec(repo, "600519", "2026-09-01")
    assert again is None  # counted once
    state = repo.get_state("600519", PRE_MARKET)
    assert state is not None and state["cumulative_hits"] == 1


def test_pre_and_post_sessions_are_independent(repo: SqliteHitTrackingRepository) -> None:
    _rec(repo, "600519", "2026-09-01", session=PRE_MARKET)
    _rec(repo, "600519", "2026-09-01", session=POST_MARKET)
    assert repo.get_state("600519", PRE_MARKET)["cumulative_hits"] == 1
    assert repo.get_state("600519", POST_MARKET)["cumulative_hits"] == 1


def test_cycle_slides_across_a_sequence(repo: SqliteHitTrackingRepository) -> None:
    assert _rec(repo, "600519", "2026-09-01")["cycleEnd"] == "2026-09-15"
    d2 = _rec(repo, "600519", "2026-09-10")
    assert d2["isCycleStart"] is False and d2["cycleHits"] == 2
    assert d2["cycleEnd"] == "2026-09-24"
    d3 = _rec(repo, "600519", "2026-09-24")  # still inside slid window
    assert d3["cycleHits"] == 3 and d3["cycleEnd"] == "2026-10-08"
    d4 = _rec(repo, "600519", "2026-10-09")  # window closed → new cycle
    assert d4["isCycleStart"] is True and d4["cycleHits"] == 1 and d4["cumulative"] == 4
    state = repo.get_state("600519", PRE_MARKET)
    assert state["total_cycles"] == 2


def test_code_is_normalized(repo: SqliteHitTrackingRepository) -> None:
    _rec(repo, "600519.SH", "2026-09-01")
    _rec(repo, "sh600519", "2026-09-02")  # same 6-digit core → same key
    state = repo.get_state("600519", PRE_MARKET)
    assert state is not None and state["cumulative_hits"] == 2


def test_invalid_session_is_rejected(repo: SqliteHitTrackingRepository) -> None:
    with pytest.raises(ValueError):
        repo.record(code="600519", session_type="midday", pick_date="2026-09-01")


def test_norm_hit_code() -> None:
    assert norm_hit_code("600519.SH") == "600519"
    assert norm_hit_code("sh600519") == "600519"
    assert norm_hit_code("1") == "000001"
    assert norm_hit_code("") == ""


def test_record_many_batches(repo: SqliteHitTrackingRepository) -> None:
    out = repo.record_many(
        [
            {"code": "600519", "category": "②A_质量榜"},
            {"code": "000001", "category": "②A_质量榜"},
            {"code": "600519", "category": "②A_质量榜"},  # dupe within batch
        ],
        session_type=PRE_MARKET,
        pick_date="2026-09-01",
    )
    assert out["recorded"] == 2
    assert out["skipped"] == 1


# ---------------------------------------------------------------------------
# three cumulative queries (acceptance)
# ---------------------------------------------------------------------------


def test_snapshot_reports_three_cumulative_views(repo: SqliteHitTrackingRepository) -> None:
    _rec(repo, "600519", "2026-09-01", session=PRE_MARKET)
    _rec(repo, "600519", "2026-09-10", session=PRE_MARKET)
    _rec(repo, "000001", "2026-09-02", session=PRE_MARKET)
    _rec(repo, "600519", "2026-09-01", session=POST_MARKET)

    snap = hit_tracking_snapshot(repo, asof="2026-09-11")
    assert snap["environment"] == "SIMULATE"
    assert snap["pre_market"]["codeCount"] == 2
    assert snap["pre_market"]["cumulativeHits"] == 3  # 600519×2 + 000001×1
    assert snap["post_market"]["codeCount"] == 1
    assert snap["post_market"]["cumulativeHits"] == 1
    # pre_market_in_cycle: only codes whose window is still open at asof
    assert snap["pre_market_in_cycle"]["codeCount"] == 2
    assert snap["pre_market_in_cycle"]["cycleHits"] == 3


def test_snapshot_excludes_closed_cycles(repo: SqliteHitTrackingRepository) -> None:
    _rec(repo, "600519", "2026-01-02")  # window long closed by asof
    snap = hit_tracking_snapshot(repo, asof="2026-09-11")
    assert snap["pre_market"]["cumulativeHits"] == 1  # cumulative still counted
    assert snap["pre_market_in_cycle"]["codeCount"] == 0  # but not in-cycle


def test_empty_repo_snapshot_is_zeroed(repo: SqliteHitTrackingRepository) -> None:
    snap = hit_tracking_snapshot(repo, asof="2026-09-11")
    for key in ("pre_market", "post_market", "pre_market_in_cycle"):
        assert snap[key]["codeCount"] == 0
    assert snap["pre_market"]["cumulativeHits"] == 0


def test_report_markdown_has_all_sections(repo: SqliteHitTrackingRepository) -> None:
    _rec(repo, "600519", "2026-09-01")
    text = format_hit_report(repo, asof="2026-09-02")
    assert "盘前累计命中" in text
    assert "盘后累计命中" in text
    assert "盘前周期内命中" in text
    assert "600519" in text


def test_details_filters(repo: SqliteHitTrackingRepository) -> None:
    _rec(repo, "600519", "2026-09-01", category="②A_质量榜")
    _rec(repo, "600519", "2026-09-10", category="②B_短线榜")
    assert len(repo.details(code="600519")) == 2
    assert len(repo.details(category="②B_短线榜")) == 1
    assert len(repo.details(start="2026-09-05")) == 1


# ---------------------------------------------------------------------------
# brief integration
# ---------------------------------------------------------------------------


def _brief(asof: str, quality: list[dict], short: list[dict] | None = None) -> dict:
    return {
        "asof": asof,
        "picks": quality,
        "rankings": {
            "boards": {
                "quality": {"key": "②A_质量榜", "items": quality},
                "short_term": {"key": "②B_短线榜", "items": short or []},
            }
        },
    }


def test_track_brief_hits_maps_boards_to_categories(repo: SqliteHitTrackingRepository) -> None:
    brief = _brief(
        "2026-09-01",
        quality=[{"symbol": "600519", "rank": 1}, {"symbol": "000001", "rank": 2}],
        short=[{"symbol": "300750", "rank": 1}],
    )
    out = track_brief_hits(repo, brief, boards=("quality", "short_term"))
    assert out["recorded"] == 3
    assert repo.get_state("600519", PRE_MARKET)["cumulative_hits"] == 1
    tags = {d["code"]: d["category"] for d in repo.details()}
    assert tags["600519"] == "②A_质量榜"
    assert tags["300750"] == "②B_短线榜"


def test_track_brief_hits_default_board_is_quality(repo: SqliteHitTrackingRepository) -> None:
    brief = _brief("2026-09-01", quality=[{"symbol": "600519"}], short=[{"symbol": "300750"}])
    out = track_brief_hits(repo, brief)
    assert out["recorded"] == 1
    assert repo.get_state("300750", PRE_MARKET) is None


def test_track_brief_hits_idempotent_same_day(repo: SqliteHitTrackingRepository) -> None:
    brief = _brief("2026-09-01", quality=[{"symbol": "600519"}])
    track_brief_hits(repo, brief)
    second = track_brief_hits(repo, brief)
    assert second["recorded"] == 0
    assert second["skipped"] == 1
    assert repo.get_state("600519", PRE_MARKET)["cumulative_hits"] == 1
