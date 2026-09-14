"""Brief batch tests (deterministic fixtures; no public net)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from stock_platform_research import brief_to_orders, build_premarket_brief, write_brief_csv


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


def test_build_premarket_brief_topn(tmp_path: Path) -> None:
    brief = build_premarket_brief(asof="2026-09-02", panel=_panel(), top_n=2)
    assert brief["asof"] == "2026-09-02"
    assert brief["market"] == "CN"
    assert brief["environment"] == "SIMULATE"
    assert len(brief["picks"]) <= 2
    assert brief["picks"]
    assert "reason" in brief["picks"][0]
    assert brief["picks"][0]["composite_score"] is not None

    csv_path = write_brief_csv(brief, tmp_path / "brief.csv")
    assert csv_path.exists()
    orders = brief_to_orders(brief, qty=200)
    assert orders
    assert orders[0]["side"] == "buy"
    assert orders[0]["qty"] == 200
