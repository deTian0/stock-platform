"""Shadow Final Board as an opt-in Y1 adoption candidate (ADR 0093 增补)."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from stock_platform_research import adoption_gate as ag
from stock_platform_research import adoption_gate_cli as cli
from stock_platform_research.shadow_board.backtest import prepare_shadow_frame


def _bars(periods: int = 160, codes: int = 8) -> pd.DataFrame:
    days = pd.bdate_range("2024-01-01", periods=periods)
    rows = []
    for i in range(codes):
        code = f"{600000 + i:06d}.SH"
        price = 12.0 + i
        for j, d in enumerate(days):
            pct = -0.0006 + 0.00035 * i + 0.012 * ((j + i) % 7 - 3) / 3.0
            price = max(1.0, price * (1.0 + pct))
            rows.append(
                {
                    "code": code,
                    "date": d.date().isoformat(),
                    "close": round(price, 4),
                    "pct_chg": round(pct * 100.0, 4),
                    "amount": 5e8 + 1e7 * i,
                }
            )
    return pd.DataFrame(rows)


def _names() -> dict[str, str]:
    return {f"{600000 + i:06d}": f"测试股{i}" for i in range(8)}


def test_shadow_candidate_is_opt_in_not_default():
    assert ag.SHADOW_CANDIDATE_NAME not in ag.CANDIDATE_REGISTRY
    assert all(c.engine == "screener" for c in ag.DEFAULT_CANDIDATES)
    assert ag.SHADOW_CANDIDATE_SPEC.engine == "shadow"
    assert ag.BASELINE_SPEC.engine == "screener"


def test_resolve_candidates_include_shadow_appends_once():
    plain = cli._resolve_candidates("")
    with_shadow = cli._resolve_candidates("", include_shadow=True)
    assert len(with_shadow) == len(plain) + 1
    assert with_shadow[-1].name == ag.SHADOW_CANDIDATE_NAME
    only = cli._resolve_candidates("none", include_shadow=True)
    assert [c.name for c in only] == [ag.SHADOW_CANDIDATE_NAME]


def test_summary_carries_engine_and_never_serialises_name_map():
    spec = replace(ag.SHADOW_CANDIDATE_SPEC, name_map=_names())
    summary = spec.to_summary()
    assert summary["engine"] == "shadow"
    assert "name_map" not in summary and "nameMap" not in summary
    # name_map is data, not a knob: equality ignores it.
    assert spec == ag.SHADOW_CANDIDATE_SPEC


def test_run_candidate_shadow_engine_returns_metrics_and_coverage():
    feats = prepare_shadow_frame(_bars())
    spec = replace(ag.SHADOW_CANDIDATE_SPEC, name_map=_names())
    out = ag.run_candidate(feats, spec)
    assert set(ag.AB_METRIC_KEYS) <= set(out["metrics"])
    assert out["nDays"] > 0
    assert "emptyBoardRatio" in out["shadow"]


def test_unknown_engine_raises():
    import pytest

    bad = replace(ag.BASELINE_SPEC, engine="nope")
    with pytest.raises(ValueError, match="unknown candidate engine"):
        ag.run_candidate(prepare_shadow_frame(_bars()), bad)


def test_evaluate_adoption_with_shadow_candidate_and_unchanged_screener():
    feats = prepare_shadow_frame(_bars())
    days = sorted(pd.to_datetime(feats["trade_date"]).dt.strftime("%Y-%m-%d").unique())
    wins = [{"label": "w1", "start": days[65], "end": days[-1]}]
    shadow = replace(ag.SHADOW_CANDIDATE_SPEC, name_map=_names())
    gate = ag.CANDIDATE_REGISTRY["gate_070"]
    with_shadow = ag.evaluate_adoption(feats, candidates=[gate, shadow], windows=wins)
    without = ag.evaluate_adoption(feats, candidates=[gate], windows=wins)
    assert with_shadow["ok"] is True
    names = [b["name"] for b in with_shadow["candidates"]]
    assert names == ["gate_070", ag.SHADOW_CANDIDATE_NAME]
    # Adding the shadow candidate must not move the screener candidate's verdict.
    assert (
        with_shadow["candidates"][0]["decision"]["windows"][0]["candidate"]
        == without["candidates"][0]["decision"]["windows"][0]["candidate"]
    )
    verdict = with_shadow["candidates"][1]["decision"]["verdict"]
    assert verdict in {ag.VERDICT_ADOPT, ag.VERDICT_REJECT, ag.VERDICT_INSUFFICIENT}
