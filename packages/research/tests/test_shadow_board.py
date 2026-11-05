"""Shadow Final Board MVP — isolation + hard gates + empty board (ADR 0093)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stock_platform_research.shadow_board import (
    SCHOOL_PRIORITY,
    apply_round2_set_a,
    run_round1,
    run_shadow_board,
    write_shadow_ledger,
)
from stock_platform_research.shadow_board.ledger import FORBIDDEN_BASENAMES
from stock_platform_research.shadow_board.round2 import set_b_cannot_override_hard_reject


def _row(
    code: str,
    *,
    name: str | None = None,
    amount: float = 50_000_000,
    rev_chg: float = -0.08,
    rs20: float = -1.0,
    vol20: float = 0.02,
    pct_chg: float = 1.0,
    industry: str = "白酒",
) -> dict:
    return {
        "code": code,
        "name": name or f"测试{code}",
        "amount": amount,
        "rev_chg": rev_chg,
        "rs20": rs20,
        "vol20": vol20,
        "pct_chg": pct_chg,
        "industry": industry,
    }


def _universe() -> list[dict]:
    # Need ≥2 scoreable rows per secondary_pick profile.
    return [
        _row("600519", name="贵州茅台", rev_chg=-0.10, industry="白酒"),
        _row("000858", name="五粮液", rev_chg=-0.09, industry="白酒"),
        _row("600036", name="招商银行", rev_chg=-0.05, industry="银行", vol20=0.015),
        _row("601318", name="中国平安", rev_chg=-0.06, industry="保险", vol20=0.018),
        _row("300750", name="宁德时代", rev_chg=0.12, industry="电池", vol20=0.04),
        _row("002594", name="比亚迪", rev_chg=0.08, industry="汽车", vol20=0.035),
    ]


def test_round1_s3_s4_ok_stubs_empty() -> None:
    pools = run_round1(_universe(), top_k=3)
    assert pools["S1"]["status"] == "empty"
    assert pools["S2"]["status"] == "empty"
    assert pools["S5"]["status"] == "empty"
    assert pools["S3"]["status"] == "ok"
    assert pools["S4"]["status"] == "ok"
    assert len(pools["S3"]["candidates"]) >= 1
    assert len(pools["S4"]["candidates"]) >= 1


def test_empty_universe_legal_empty_board(tmp_path: Path) -> None:
    payload = run_shadow_board([], asof="2026-11-05", shadow_dir=tmp_path, write=True)
    assert payload["status"] == "empty"
    assert payload["finalBoard"] == []
    assert payload["excludedFromPerformance"] is True
    assert payload["shadowOnly"] is True
    snap = Path(payload["ledgerPath"])
    assert snap.parent == tmp_path
    assert snap.exists()


def test_hard_gate_rejects_st_and_limit_up() -> None:
    pools = {
        "S3": {
            "candidates": [
                {
                    **_row("600001", name="*ST示例", amount=80_000_000),
                    "school": "S3",
                    "score": 0.9,
                    "holdingPeriod": "10 日",
                    "trigger": "t",
                    "expectation": "e",
                    "invalidation": "i",
                    "sourceFields": {"amount": 80_000_000, "pct_chg": 1.0},
                },
                {
                    **_row("600002", name="涨停票", pct_chg=10.0, amount=80_000_000),
                    "school": "S3",
                    "score": 0.8,
                    "holdingPeriod": "10 日",
                    "trigger": "t",
                    "expectation": "e",
                    "invalidation": "i",
                    "sourceFields": {"amount": 80_000_000, "pct_chg": 10.0},
                },
                {
                    **_row("600003", name="正常票", amount=80_000_000, pct_chg=1.0),
                    "school": "S3",
                    "score": 0.7,
                    "holdingPeriod": "10 日",
                    "trigger": "t",
                    "expectation": "e",
                    "invalidation": "i",
                    "sourceFields": {"amount": 80_000_000, "pct_chg": 1.0},
                },
            ]
        }
    }
    out = apply_round2_set_a(pools)
    codes = {r["code"] for r in out["passed"]}
    assert "600003" in codes
    assert "600001" not in codes
    assert "600002" not in codes
    reasons = " ".join(r["reason"] for r in out["rejected"])
    assert "ST" in reasons or "风险警示" in reasons
    assert "涨停" in reasons


def test_school_priority_arbitration() -> None:
    assert SCHOOL_PRIORITY[0] == "S3"
    pools = {
        "S3": {
            "candidates": [
                {
                    **_row("600519", name="贵州茅台"),
                    "school": "S3",
                    "score": 0.5,
                    "holdingPeriod": "a",
                    "trigger": "t",
                    "expectation": "e",
                    "invalidation": "i",
                    "sourceFields": {"amount": 50_000_000, "pct_chg": 1.0},
                }
            ]
        },
        "S4": {
            "candidates": [
                {
                    **_row("600519", name="贵州茅台"),
                    "school": "S4",
                    "score": 0.99,
                    "holdingPeriod": "a",
                    "trigger": "t",
                    "expectation": "e",
                    "invalidation": "i",
                    "sourceFields": {"amount": 50_000_000, "pct_chg": 1.0},
                }
            ]
        },
    }
    out = apply_round2_set_a(pools)
    assert len(out["passed"]) == 1
    assert out["passed"][0]["school"] == "S3"


def test_set_b_cannot_admit_hard_rejects() -> None:
    rejected = [{"code": "600001", "reason": "ST"}]
    allowed = set_b_cannot_override_hard_reject(rejected, ["600001", "600519"])
    assert allowed == ["600519"]


def test_ledger_isolation_from_production_names(tmp_path: Path) -> None:
    prod = tmp_path / "prod"
    prod.mkdir()
    shadow = tmp_path / "shadow"
    payload = {
        "schemaVersion": 1,
        "asof": "2026-11-05",
        "status": "empty",
        "finalBoard": [],
        "excludedFromPerformance": True,
        "shadowOnly": True,
    }
    paths = write_shadow_ledger(payload, shadow_dir=shadow, asof="2026-11-05")
    assert Path(paths["json"]).is_relative_to(shadow) or str(paths["json"]).startswith(
        str(shadow)
    )
    # Must not create production ledger filenames.
    for name in FORBIDDEN_BASENAMES:
        assert not (prod / name).exists()
        assert not (shadow / name).exists()
    # JSONL append under shadow only.
    assert (shadow / "final_board.jsonl").exists()
    line = (shadow / "final_board.jsonl").read_text(encoding="utf-8").strip()
    assert json.loads(line)["shadowOnly"] is True


def test_write_refuses_forbidden_basename(tmp_path: Path) -> None:
    # Direct path escape via forging is blocked by basename check when name matches.
    from stock_platform_research.shadow_board.ledger import _assert_shadow_path

    with pytest.raises(ValueError, match="禁止写入生产账本"):
        _assert_shadow_path(tmp_path / "recommend_decisions.jsonl", shadow_root=tmp_path)


def test_pipeline_writes_only_shadow(tmp_path: Path) -> None:
    prod_marker = tmp_path / "recommend_decisions.jsonl"
    prod_marker.write_text("DO_NOT_TOUCH\n", encoding="utf-8")
    shadow = tmp_path / "shadow"
    payload = run_shadow_board(
        _universe(),
        asof="2026-11-05",
        shadow_dir=shadow,
        write=True,
        enable_advisory_b=True,
    )
    assert payload["status"] in {"ok", "empty"}
    assert payload["advisoryB"] is not None
    assert payload["advisoryB"]["excludedFromPerformance"] is True
    assert prod_marker.read_text(encoding="utf-8") == "DO_NOT_TOUCH\n"
    assert (shadow / "final_board_2026-11-05.json").exists()
    if payload["finalBoard"]:
        row = payload["finalBoard"][0]
        for key in ("holdingPeriod", "trigger", "expectation", "invalidation"):
            assert row.get(key)


def test_no_pad_to_n() -> None:
    """Single survivor must not be padded to a fixed N."""
    pools = {
        "S3": {
            "candidates": [
                {
                    **_row("600519", name="贵州茅台"),
                    "school": "S3",
                    "score": 0.8,
                    "holdingPeriod": "a",
                    "trigger": "t",
                    "expectation": "e",
                    "invalidation": "i",
                    "sourceFields": {"amount": 50_000_000, "pct_chg": 1.0},
                }
            ]
        }
    }
    out = apply_round2_set_a(pools, max_board_size=10)
    assert len(out["passed"]) == 1
