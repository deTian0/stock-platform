"""Batch cross-section scoring tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from stock_platform_research import score_cross_section, score_cross_section_csv
from stock_platform_research.batch import load_panel_csv


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


def test_load_panel_csv_keeps_zero_padded_codes(tmp_path: Path) -> None:
    """``000533`` must not be read back as ``533``.

    A bare ``pd.read_csv`` infers ``int64`` for a code column and strips the
    leading zeros; that both mangles printed codes and makes ③A/③B holdings
    matching miss the panel row. Regression: 2026-10-12 A2 report showed
    ``801`` / ``2658`` instead of ``000801`` / ``002658``.
    """
    path = tmp_path / "panel.csv"
    path.write_text(
        "trade_date,symbol,close,vol20,rev_chg,ma20,ma60\n"
        "2026-10-12,000533,9.78,0.03,-0.04,10.85,10.84\n"
        "2026-10-12,600963,3.30,0.02,-0.03,3.42,3.35\n",
        encoding="utf-8",
    )
    panel = load_panel_csv(path)
    assert panel["symbol"].tolist() == ["000533", "600963"]
    # dtype is object on classic pandas and StringDtype under PDEP-14; either way
    # the elements must be text, never ints.
    assert all(isinstance(s, str) for s in panel["symbol"])

    # and a write-back round-trip keeps them zero-padded on disk
    panel.to_csv(tmp_path / "roundtrip.csv", index=False)
    written = (tmp_path / "roundtrip.csv").read_text(encoding="utf-8")
    assert "000533" in written
    assert "600963" in written
