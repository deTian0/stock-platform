"""Secondary pick: units, missing fields, and the two profiles."""

from __future__ import annotations

from stock_platform_research.secondary_pick import select_secondary


def _row(symbol: str, **overrides):
    base = {
        "symbol": symbol,
        "name": f"名称{symbol}",
        "close": 10.0,
        "vol20": 0.02,
        "rev_chg": -0.10,
        "ma20": 10.0,
        "rs20": 0.0,
        "amount": 80_000_000.0,
        "composite_score": 0.5,
        "reasonSummary": "原因",
    }
    base.update(overrides)
    return base


def test_st_is_rejected_by_both_profiles():
    rows = [
        _row("600001", name="ST能特"),
        _row("600002"),
        _row("600003", rs20=4.0),
    ]
    for profile in ("quality", "short"):
        out = select_secondary(rows, profile=profile, top_k=5)
        symbols = {row["symbol"] for row in out["selected"]}
        assert "600001" not in symbols
        rejected = next(row for row in out["rejected"] if row["symbol"] == "600001")
        assert "风险警示" in rejected["rejectReason"]


def test_amount_threshold_is_yuan():
    rows = [
        _row("600001", amount=9_999_999),
        _row("600002", amount=10_000_000),
        _row("600003", amount=10_000_000, rs20=1.0),
    ]
    out = select_secondary(rows, profile="quality", top_k=5)
    rejected = next(row for row in out["rejected"] if row["symbol"] == "600001")
    assert "1000 万元" in rejected["rejectReason"]
    assert "600001" not in {row["symbol"] for row in out["selected"]}
    kept = {row["symbol"] for row in out["selected"]}
    assert "600002" in kept and "600003" in kept


def test_rev_floors_use_plan_units():
    deep = select_secondary(
        [_row("600001", rev_chg=-0.26), _row("600002"), _row("600003")],
        profile="quality",
    )
    edge = select_secondary(
        [_row("600001", rev_chg=-0.25), _row("600002"), _row("600003")],
        profile="quality",
    )
    assert any(row["symbol"] == "600001" and "20 日收益低于 −25%" in row["rejectReason"] for row in deep["rejected"])
    assert all(row["symbol"] != "600001" or "−25%" not in row.get("rejectReason", "") for row in edge["rejected"])

    deep_short = select_secondary(
        [_row("600001", rev_chg=-0.16), _row("600002"), _row("600003")],
        profile="short",
    )
    assert any(row["symbol"] == "600001" and "20 日收益低于 −15%" in row["rejectReason"] for row in deep_short["rejected"])


def test_rs20_below_ma20_is_not_a_hard_rejection():
    """The lvrev kernel selects names below MA20 by construction.

    An absolute rs20 floor killed the whole ②B board on 2026-10-27 (10 in, 0 out),
    so rs20 must stay a scoring dimension only.
    """
    rows = [_row(f"60000{i}", rs20=-6.0 + i * 0.1) for i in range(6)]
    out = select_secondary(rows, profile="short", top_k=5)
    assert len(out["selected"]) == 5
    # 唯一落选者是「得分未进前 5」，不是因为跌破 MA20 被硬拒
    assert len(out["rejected"]) == 1
    assert "MA20" not in out["rejected"][0]["rejectReason"]
    assert "得分未进入前" in out["rejected"][0]["rejectReason"]


def test_does_not_pad_when_fewer_than_top_k_remain():
    rows = [_row(f"60000{i}") for i in range(4)] + [
        _row("600010", name="ST甲"),
        _row("600011", name="*ST乙"),
    ]
    out = select_secondary(rows, profile="quality", top_k=5)
    assert len(out["selected"]) == 4
    assert out["stats"]["note"] == "剔除后仅 4 只符合条件，按规则不补齐"
    assert "600010" not in {row["symbol"] for row in out["selected"]}


def test_profiles_rank_the_same_input_differently():
    rows = [
        _row("600001", vol20=0.01, rev_chg=-0.10, rs20=0.0, amount=80_000_000),
        _row("600002", vol20=0.03, rev_chg=-0.02, rs20=4.0, amount=90_000_000),
        _row("600003", vol20=0.02, rev_chg=-0.08, rs20=1.0, amount=60_000_000),
        _row("600004", vol20=0.04, rev_chg=-0.12, rs20=2.0, amount=50_000_000),
    ]
    quality = [row["symbol"] for row in select_secondary(rows, profile="quality")["selected"]]
    short = [row["symbol"] for row in select_secondary(rows, profile="short")["selected"]]
    assert quality[0] != short[0]


def test_quality_penalizes_rs20_far_from_ma20():
    rows = [
        _row("600001", rs20=0.0),
        _row("600002", rs20=8.0),
        _row("600003", rs20=1.0),
    ]
    selected = {row["symbol"]: row for row in select_secondary(rows, profile="quality")["selected"]}
    assert selected["600001"]["dimensionScores"]["趋势位置"] > selected["600002"]["dimensionScores"]["趋势位置"]


def test_missing_field_is_rejected_instead_of_renormalized():
    rows = [
        _row("600001", rs20=None, vol20=0.001, amount=500_000_000, rev_chg=-0.10),
        _row("600002", rs20=0.0, vol20=0.05, amount=40_000_000),
        _row("600003", rs20=1.0, vol20=0.05, amount=40_000_000),
    ]
    out = select_secondary(rows, profile="quality", top_k=1)
    assert "600001" not in {row["symbol"] for row in out["selected"]}
    missing = next(row for row in out["rejected"] if row["symbol"] == "600001")
    assert missing["rejectReason"].startswith("缺 ")


def test_fewer_than_two_scoreable_rows_does_not_rank():
    out = select_secondary(
        [_row("600001"), _row("600002", name="ST甲")],
        profile="quality",
        top_k=5,
    )
    assert out["selected"] == []
    assert out["stats"]["note"] == "可评分样本不足 2，不做有效排名"
