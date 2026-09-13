"""Batch cross-section scoring tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from stock_platform_research import score_cross_section, score_cross_section_csv


def test_score_cross_section_filters(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            "symbol": ["A", "B", "C"],
            "vol20": [0.1, 0.3, 0.5],
            "rev_chg": [-0.05, -0.02, 0.03],
                "close": [10, 10, 10],
                "ma20": [10, 10, 10],
                "ma60": [9, 9, 9],
        }
    )
    out = score_cross_section(df, top_n=10)
    assert "composite_score" in out.columns
    assert len(out) >= 1

    path = tmp_path / "x.csv"
    df.to_csv(path, index=False)
    out2 = score_cross_section_csv(path, output=tmp_path / "out.csv", top_n=1)
    assert len(out2) == 1
    assert (tmp_path / "out.csv").exists()
