"""Round2 seat-arbitration experiment knob (docs/plans/multi-strategy-final-board.md §11).

The factory mode is ``d``; ``a`` / ``b`` are offline experiments. These tests pin
three things: (1) the default is unchanged bit-for-bit, (2) hard gates survive
every mode, (3) ``a`` / ``b`` actually give the starved schools seats.
"""

from __future__ import annotations

import pytest

from stock_platform_research.shadow_board.round2 import (
    ARBITRATION_MODES,
    DEFAULT_ARBITRATION,
    MAX_BOARD_SIZE,
    apply_round2_set_a,
    school_score_percentiles,
)


def _cand(
    code: str,
    *,
    school: str,
    score: float,
    industry: str,
    name: str | None = None,
    amount: float = 80_000_000,
    pct_chg: float = 1.0,
) -> dict:
    return {
        "code": code,
        "name": name or f"样本{code}",
        "school": school,
        "score": score,
        "industry": industry,
        "holdingPeriod": "10 日",
        "trigger": "t",
        "expectation": "e",
        "invalidation": "i",
        "sourceFields": {"amount": amount, "pct_chg": pct_chg},
    }


def _pools(top_k: int = 8) -> dict:
    """S3/S4 pools alone can fill all 10 seats — the starvation shape from §11.

    Industries are spread wide enough that the ``MAX_PER_INDUSTRY=2`` cap is not
    what decides the outcome; seat allocation is.
    """
    pools: dict[str, dict] = {}
    # Score bands are deliberately non-overlapping across schools so the
    # factory ordering (priority first) and a score ordering differ.
    bands = {"S3": 0.90, "S4": 0.70, "S5": 0.50, "S1": 0.30}
    for si, (school, base) in enumerate(bands.items()):
        cands = []
        for i in range(top_k):
            cands.append(
                _cand(
                    f"{600000 + si * 100 + i:06d}",
                    school=school,
                    score=base - i * 0.01,
                    industry=f"行业{si * 100 + i}",
                )
            )
        pools[school] = {"candidates": cands}
    pools["S2"] = {"candidates": [], "status": "empty"}
    return pools


# --- 1. the default must not move ------------------------------------------


def test_default_mode_is_d_and_omits_experiment_keys() -> None:
    assert DEFAULT_ARBITRATION == "d"
    assert ARBITRATION_MODES[0] == "d"
    out = apply_round2_set_a(_pools())
    assert "arbitration" not in out  # factory payload shape untouched
    assert "normalization" not in out
    assert "minSeats" not in out
    assert set(out) == {"arbiter", "rejected", "passed", "stats"}


def test_explicit_d_equals_no_argument_byte_for_byte() -> None:
    pools = _pools()
    implicit = apply_round2_set_a(pools)
    explicit = apply_round2_set_a(pools, arbitration="d")
    assert explicit["passed"] == implicit["passed"]
    assert explicit["rejected"] == implicit["rejected"]
    assert explicit["stats"] == implicit["stats"]


def test_d_reproduces_the_documented_starvation() -> None:
    """§11's root cause: S3/S4 fill all 10 seats, S5/S1 get none."""
    out = apply_round2_set_a(_pools())
    seats = {}
    for row in out["passed"]:
        seats[row["school"]] = seats.get(row["school"], 0) + 1
    assert len(out["passed"]) == MAX_BOARD_SIZE
    assert seats == {"S3": 8, "S4": 2}
    assert "S5" not in seats and "S1" not in seats


def test_d_order_is_priority_then_score_then_code() -> None:
    out = apply_round2_set_a(_pools())
    schools = [r["school"] for r in out["passed"]]
    assert schools == ["S3"] * 8 + ["S4"] * 2
    s3_scores = [r["score"] for r in out["passed"][:8]]
    assert s3_scores == sorted(s3_scores, reverse=True)


# --- 2. mode a: priority only for same-code dedupe -------------------------


def test_mode_a_spreads_seats_across_schools() -> None:
    out = apply_round2_set_a(_pools(), arbitration="a")
    seats: dict[str, int] = {}
    for row in out["passed"]:
        seats[row["school"]] = seats.get(row["school"], 0) + 1
    assert out["arbitration"] == "a"
    assert out["normalization"] == "school_score_percentile"
    # Equal-size pools → equal percentiles → every non-empty school is represented.
    assert set(seats) == {"S1", "S3", "S4", "S5"}
    assert sum(seats.values()) == MAX_BOARD_SIZE
    assert seats["S1"] > 0 and seats["S5"] > 0


def test_mode_a_ignores_raw_score_scale() -> None:
    """A school whose raw scores are tiny must still place its best name.

    This is the whole point of normalising: S1's 0.3 band would otherwise lose
    to every S3 name on a global raw-score sort too.
    """
    pools = _pools()
    for cand in pools["S1"]["candidates"]:
        cand["score"] = cand["score"] / 1000.0
    out = apply_round2_set_a(pools, arbitration="a")
    assert any(r["school"] == "S1" for r in out["passed"])


def test_mode_a_still_uses_priority_for_same_code_conflict() -> None:
    pools = {
        "S3": {"candidates": [_cand("600519", school="S3", score=0.10, industry="白酒")]},
        "S4": {"candidates": [_cand("600519", school="S4", score=0.99, industry="白酒")]},
    }
    out = apply_round2_set_a(pools, arbitration="a")
    assert len(out["passed"]) == 1
    assert out["passed"][0]["school"] == "S3"  # contract §2 literal
    assert any("同票冲突" in r["reason"] for r in out["rejected"])


def test_school_score_percentiles_are_scale_free() -> None:
    rows = [
        _cand("600001", school="S3", score=100.0, industry="x"),
        _cand("600002", school="S3", score=1.0, industry="x"),
        _cand("600003", school="S1", score=0.02, industry="x"),
        _cand("600004", school="S1", score=0.01, industry="x"),
    ]
    pct = school_score_percentiles(rows)
    assert pct["600001"] == 1.0
    assert pct["600003"] == 1.0  # school best regardless of raw magnitude
    assert pct["600002"] == 0.5
    assert pct["600004"] == 0.5


# --- 3. mode b: per-school floor -------------------------------------------


def test_mode_b_gives_every_non_empty_school_its_floor() -> None:
    out = apply_round2_set_a(_pools(), arbitration="b", min_seats=1)
    seats: dict[str, int] = {}
    for row in out["passed"]:
        seats[row["school"]] = seats.get(row["school"], 0) + 1
    assert out["arbitration"] == "b"
    assert out["minSeats"] == 1
    for sid in ("S3", "S4", "S5", "S1"):
        assert seats.get(sid, 0) >= 1
    assert sum(seats.values()) == MAX_BOARD_SIZE


def test_mode_b_does_not_reserve_for_empty_pools() -> None:
    """No pad-to-N: a school with no survivor gets nothing."""
    out = apply_round2_set_a(_pools(), arbitration="b", min_seats=2)
    assert not any(r["school"] == "S2" for r in out["passed"])


def test_mode_b_reserved_seats_lead_the_board() -> None:
    """Order matters: the loop buys the head of the board, not the tail."""
    out = apply_round2_set_a(_pools(), arbitration="b", min_seats=1)
    head = [r["school"] for r in out["passed"][:4]]
    assert head == ["S3", "S4", "S5", "S1"]


def test_mode_b_min_seats_zero_equals_default() -> None:
    pools = _pools()
    base = apply_round2_set_a(pools)
    out = apply_round2_set_a(pools, arbitration="b", min_seats=0)
    assert out["passed"] == base["passed"]


def test_mode_b_walks_down_a_school_when_industry_cap_blocks_its_best() -> None:
    """S5's better names sit in an industry S3 already filled; its floor uses the third."""
    pools = {
        "S3": {"candidates": [_cand("600001", school="S3", score=0.9, industry="白酒")]},
        "S5": {
            "candidates": [
                _cand("600101", school="S5", score=0.5, industry="白酒"),
                _cand("600102", school="S5", score=0.4, industry="白酒"),
                _cand("600103", school="S5", score=0.3, industry="银行"),
            ]
        },
    }
    # max_per_industry=1 → 白酒 is full once S3's name is seated.
    out = apply_round2_set_a(pools, arbitration="b", min_seats=1, max_per_industry=1)
    by_school = {r["school"]: r["code"] for r in out["passed"]}
    assert by_school.get("S3") == "600001"
    assert by_school.get("S5") == "600103"
    # The skipped names are still reported as industry-cap rejects, exactly once each.
    caps = [r for r in out["rejected"] if "集中度上限" in r["reason"]]
    assert {r["code"] for r in caps} == {"600101", "600102"}
    assert len(caps) == 2


def test_mode_b_never_exceeds_board_size_with_large_min_seats() -> None:
    out = apply_round2_set_a(_pools(), arbitration="b", min_seats=99)
    assert len(out["passed"]) <= MAX_BOARD_SIZE


# --- 4. hard gates hold in every mode --------------------------------------


@pytest.mark.parametrize("mode", ARBITRATION_MODES)
def test_hard_gates_hold_in_every_mode(mode: str) -> None:
    """ST / liquidity / limit-up must never ride in on a reserved seat."""
    pools = {
        "S1": {
            "candidates": [
                _cand("600001", school="S1", score=0.99, industry="a", name="*ST垃圾"),
                _cand("600002", school="S1", score=0.98, industry="b", amount=1_000),
                _cand("600003", school="S1", score=0.97, industry="c", pct_chg=10.0),
                _cand("600004", school="S1", score=0.10, industry="d"),
            ]
        },
        "S5": {"candidates": [_cand("600101", school="S5", score=0.5, industry="e")]},
    }
    out = apply_round2_set_a(pools, arbitration=mode, min_seats=3)
    codes = {r["code"] for r in out["passed"]}
    assert codes == {"600004", "600101"}
    reasons = " ".join(r["reason"] for r in out["rejected"])
    assert "ST" in reasons or "风险警示" in reasons
    assert "流动性" in reasons
    assert "涨停" in reasons


@pytest.mark.parametrize("mode", ARBITRATION_MODES)
def test_industry_cap_holds_in_every_mode(mode: str) -> None:
    pools = {
        sid: {
            "candidates": [
                _cand(f"{600000 + i * 10 + si:06d}", school=sid, score=0.9 - i * 0.1, industry="白酒")
                for i in range(4)
            ]
        }
        for si, sid in enumerate(("S3", "S4", "S5"))
    }
    out = apply_round2_set_a(pools, arbitration=mode, min_seats=2)
    assert len(out["passed"]) <= 2  # one industry, cap 2
    assert all(r["industry"] == "白酒" for r in out["passed"])


@pytest.mark.parametrize("mode", ARBITRATION_MODES)
def test_no_pad_to_n_in_any_mode(mode: str) -> None:
    pools = {"S3": {"candidates": [_cand("600519", school="S3", score=0.8, industry="白酒")]}}
    out = apply_round2_set_a(pools, arbitration=mode, min_seats=5)
    assert len(out["passed"]) == 1


@pytest.mark.parametrize("mode", ARBITRATION_MODES)
def test_empty_pools_stay_empty_in_any_mode(mode: str) -> None:
    out = apply_round2_set_a({"S3": {"candidates": []}}, arbitration=mode)
    assert out["passed"] == []
    assert out["stats"]["passed"] == 0


@pytest.mark.parametrize("mode", ARBITRATION_MODES)
def test_every_input_is_either_passed_or_rejected_once(mode: str) -> None:
    """No name may be silently dropped or double-counted by the reserve pass."""
    pools = _pools()
    out = apply_round2_set_a(pools, arbitration=mode, min_seats=2)
    n_in = out["stats"]["input"]
    assert n_in == sum(len(p["candidates"]) for p in pools.values())
    assert out["stats"]["passed"] + out["stats"]["rejected"] == n_in
    passed_codes = [r["code"] for r in out["passed"]]
    rejected_codes = [r["code"] for r in out["rejected"]]
    assert len(set(passed_codes)) == len(passed_codes)
    assert not (set(passed_codes) & set(rejected_codes))


def test_unknown_mode_is_fail_closed() -> None:
    with pytest.raises(ValueError, match="arbitration must be one of"):
        apply_round2_set_a(_pools(), arbitration="z")
