"""Universe + readable brief reasons (M39)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from stock_platform_research.brief import (
    build_premarket_brief,
    build_reasons_for_row,
    reason_summary,
)
from stock_platform_research.universe import (
    UniverseEmptyError,
    default_daily_universe_path,
    default_universe_fixture_path,
    load_universe,
    load_universe_tiers,
    universe_size_guidance,
)


def test_layered_daily_universe_tiers() -> None:
    path = default_daily_universe_path()
    tiers = load_universe_tiers(path)
    assert len(tiers["core"]) >= 1
    assert len(tiers["watch"]) >= len(tiers["core"])
    assert len(tiers["full"]) >= len(tiers["watch"])
    assert load_universe(path, tier="core") == tiers["core"]
    assert load_universe(path, tier="watch") == tiers["watch"]


def test_flat_universe_still_works() -> None:
    path = default_universe_fixture_path()
    symbols = load_universe(path)
    assert "600519" in symbols
    # Flat file: tier argument still returns the same list.
    assert load_universe(path, tier="full") == symbols


def test_empty_universe_fail_closed(tmp_path: Path) -> None:
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"core": [], "watch": [], "full": []}), encoding="utf-8")
    with pytest.raises(UniverseEmptyError):
        load_universe(empty, tier="watch")
    with pytest.raises(UniverseEmptyError):
        load_universe(symbols=[])


def test_universe_size_guidance() -> None:
    g = universe_size_guidance("core")
    assert g["tier"] == "core"
    assert g["recommendedMaxSymbols"] == 50
    assert "EM_MIN_INTERVAL" in g["emMinIntervalHint"]


def _panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": ["2026-09-02"] * 4,
            "symbol": ["A", "B", "C", "D"],
            "open": [10, 10, 10, 10],
            "close": [10.5, 10.0, 9.5, 10.2],
            "vol20": [0.10, 0.12, 0.40, 0.11],
            "rev_chg": [-0.08, -0.06, 0.02, -0.04],
            "ma20": [10.0, 10.0, 10.0, 10.0],
            "ma60": [9.0, 9.0, 9.5, 9.2],
            "trend_up": [True, True, True, True],
            "rs20": [5.0, 0.0, -5.0, 2.0],
        }
    )


def test_brief_reasons_readable_nonempty() -> None:
    brief = build_premarket_brief(asof="2026-09-02", panel=_panel(), top_n=2)
    assert brief["picks"]
    pick = brief["picks"][0]
    assert isinstance(pick["reasons"], list)
    assert pick["reasons"]
    assert pick["reasonSummary"]
    assert "综合分" in pick["reasonSummary"] or "通过" in pick["reasonSummary"]
    assert pick["reason"]  # legacy string kept


def test_empty_gate_reasons() -> None:
    row = pd.Series({"symbol": "X"})
    reasons = build_reasons_for_row(row, gated=True)
    assert reasons
    assert reasons[0]["key"] == "gated_pass"
    assert reason_summary(reasons)


def test_soft_gates_relaxes_when_strict_empty() -> None:
    # All fail entry gates (ma20 <= ma60) but soft mode still returns scored ranks.
    panel = pd.DataFrame(
        {
            "trade_date": ["2026-09-02"] * 2,
            "symbol": ["A", "B"],
            "open": [10, 10],
            "close": [10, 10],
            "vol20": [0.2, 0.3],
            "rev_chg": [0.1, 0.2],
            "ma20": [9.0, 9.0],
            "ma60": [10.0, 10.0],
        }
    )
    strict = build_premarket_brief(asof="2026-09-02", panel=panel, top_n=2, soft_gates=False)
    assert strict["picks"] == []
    assert "emptyPicksMessage" in strict
    soft = build_premarket_brief(asof="2026-09-02", panel=panel, top_n=2, soft_gates=True)
    assert len(soft["picks"]) >= 1
    assert soft["gatesRelaxed"] is True
    assert "软化" in (soft.get("gatesNote") or "")
