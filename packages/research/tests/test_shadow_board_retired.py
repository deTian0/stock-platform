"""S4/S5 retirement (ADR 0093 增补 2): default empty pools, explicit re-enable restores behaviour."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stock_platform_research.shadow_board.schools import (
    DEFAULT_ENABLED_SCHOOLS,
    ENV_SHADOW_SCHOOLS,
    RETIRED_REASON,
    RETIRED_SCHOOLS,
    resolve_enabled_schools,
    run_round1,
    school_s4_short,
    school_s5_flow,
)


def _row(code: str, name: str, *, rev_chg: float, industry: str, vol20: float = 0.02) -> dict:
    return {
        "code": code,
        "name": name,
        "amount": 50_000_000,
        "rev_chg": rev_chg,
        "rs20": -1.0,
        "vol20": vol20,
        "pct_chg": 1.0,
        "industry": industry,
    }


def _universe() -> list[dict]:
    return [
        _row("600519", "贵州茅台", rev_chg=-0.10, industry="白酒"),
        _row("000858", "五粮液", rev_chg=-0.09, industry="白酒"),
        _row("600036", "招商银行", rev_chg=-0.05, industry="银行", vol20=0.015),
        _row("601318", "中国平安", rev_chg=-0.06, industry="保险", vol20=0.018),
        _row("300750", "宁德时代", rev_chg=0.12, industry="电池", vol20=0.04),
        _row("002594", "比亚迪", rev_chg=0.08, industry="汽车", vol20=0.035),
    ]


@pytest.fixture(autouse=True)
def _no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_SHADOW_SCHOOLS, raising=False)


def test_factory_table_retires_s4_s5_only() -> None:
    assert RETIRED_SCHOOLS == frozenset({"S4", "S5"})
    assert DEFAULT_ENABLED_SCHOOLS == ("S1", "S2", "S3")
    assert resolve_enabled_schools() == DEFAULT_ENABLED_SCHOOLS


def test_default_round1_s4_s5_empty_with_reason() -> None:
    pools = run_round1(_universe(), top_k=3)
    for sid in ("S4", "S5"):
        assert pools[sid]["status"] == "empty"
        assert pools[sid]["candidates"] == []
        assert pools[sid]["reason"] == RETIRED_REASON
        assert pools[sid]["retired"] is True
    # S3 untouched.
    assert pools["S3"]["status"] == "ok"
    assert "retired" not in pools["S3"]


def test_explicit_enable_matches_direct_runner() -> None:
    uni = _universe()
    pools = run_round1(uni, top_k=3, enabled_schools=["S1", "S2", "S3", "S4", "S5"])
    assert pools["S4"] == school_s4_short(uni, top_k=3)
    assert pools["S5"] == school_s5_flow(uni, top_k=3)
    assert pools["S4"]["status"] == "ok" and pools["S5"]["status"] == "ok"


def test_env_re_enables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_SHADOW_SCHOOLS, "s1, s2,S3,S4,S5")
    pools = run_round1(_universe(), top_k=3)
    assert pools["S4"]["status"] == "ok"
    assert pools["S5"]["status"] == "ok"


def test_explicit_beats_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_SHADOW_SCHOOLS, "S1,S2,S3,S4,S5")
    pools = run_round1(_universe(), top_k=3, enabled_schools="S3")
    assert pools["S4"]["reason"] == RETIRED_REASON
    assert pools["S1"]["reason"] == RETIRED_REASON


def test_unknown_school_id_raises() -> None:
    with pytest.raises(ValueError):
        resolve_enabled_schools("S3,S9")


def test_backtest_board_respects_retirement() -> None:
    import numpy as np
    import pandas as pd

    from stock_platform_research.book_replay import ReplayParams
    from stock_platform_research.shadow_board.backtest import compare_shadow_vs_lvrev, prepare_shadow_frame

    rng = np.random.default_rng(3)
    days = pd.bdate_range("2025-01-02", periods=90)
    rows = []
    for i in range(16):
        px = 10.0 + i
        for d in days:
            pct = max(min(float(rng.normal(0.05, 1.8)), 9.0), -9.0)
            px *= 1.0 + pct / 100.0
            rows.append({"code": f"{600000 + i:06d}.SH", "date": d.date().isoformat(),
                         "close": round(px, 3), "pct_chg": round(pct, 4), "amount": 5e7})
    feats = prepare_shadow_frame(
        pd.DataFrame(rows), industry_map={f"{600000 + i:06d}": f"行业{i % 4}" for i in range(16)}
    )
    names = {f"{600000 + i:06d}": f"样本{i}" for i in range(16)}
    out = compare_shadow_vs_lvrev(feats, name_map=names, params=ReplayParams(max_positions=5))
    sh = out["shadow"]["shadow"]
    assert sh["schoolCoverage"]["S4"] == {"nonEmptyDays": 0, "seats": 0}
    assert sh["schoolCoverage"]["S5"] == {"nonEmptyDays": 0, "seats": 0}
    assert sh["enabledSchools"] == ["S1", "S2", "S3"]
    assert any(RETIRED_REASON in x for x in out["limitations"])


def test_loop_health_ok_when_s4_s5_retired(tmp_path: Path) -> None:
    from stock_platform_research.loop_health import _collect_shadow_board
    from stock_platform_research.shadow_board.pipeline import run_shadow_board

    payload = run_shadow_board(_universe(), asof="2026-11-06", shadow_dir=tmp_path, write=True)
    assert payload["schools"]["S4"]["reason"] == RETIRED_REASON
    rec = json.loads((tmp_path / "final_board.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert rec["status"] in {"ok", "empty"}
    sec = _collect_shadow_board(tmp_path)
    assert sec["status"] == "ok"
    assert "reason" not in sec
