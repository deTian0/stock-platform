"""Universe + cross-section panel tests (injected providers; no public net)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from stock_platform_research import (
    UniverseEmptyError,
    build_cross_section_panel,
    default_universe_fixture_path,
    load_universe,
    panel_to_csv,
)


def _synth_bars(symbol: str, asof: date, n: int = 70, base: float = 10.0) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    # Walk backwards on calendar days; skip weekends for a denser trading-ish series.
    d = asof
    closes: list[tuple[date, float]] = []
    while len(closes) < n:
        if d.weekday() < 5:
            # Mild drift + mean-reversion friendly path.
            idx = n - len(closes)
            px = base + 0.02 * idx + (0.15 if idx % 7 == 0 else 0.0)
            closes.append((d, px))
        d -= timedelta(days=1)
    closes.reverse()
    for day, px in closes:
        rows.append(
            {
                "symbol": symbol,
                "date": day.isoformat(),
                "open": px * 0.99,
                "high": px * 1.01,
                "low": px * 0.98,
                "close": px,
                "volume": 1_000_000,
                "amount": px * 1_000_000,
            }
        )
    return rows


class _FakeDaily:
    name = "fake_daily"

    def __init__(self, by_sym: dict[str, list[dict[str, Any]]]) -> None:
        self.by_sym = by_sym

    def get_daily(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        asset_type: str = "stock",
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for sym in symbols:
            for row in self.by_sym.get(sym, []):
                day = date.fromisoformat(str(row["date"])[:10])
                if start and day < start:
                    continue
                if end and day > end:
                    continue
                out.append(row)
        return out


class _FakeFundFlow:
    def get_fund_flow(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        limit: int = 120,
    ) -> list[dict[str, Any]]:
        asof = end or date(2026, 9, 2)
        return [
            {
                "symbol": sym,
                "date": asof.isoformat(),
                "main_net": 1.0e6,
                "small_net": -1.0e5,
                "mid_net": 0.0,
                "large_net": 5.0e5,
                "super_net": 5.0e5,
            }
            for sym in symbols
        ]


def test_load_universe_fixture_and_fail_closed(tmp_path: Path) -> None:
    path = default_universe_fixture_path()
    univ = load_universe(path)
    assert "600519" in univ
    assert load_universe(symbols=["SH600519", "600519", "bad"]) == ["600519"]

    empty = tmp_path / "empty.json"
    empty.write_text('{"symbols": []}', encoding="utf-8")
    with pytest.raises(UniverseEmptyError):
        load_universe(empty)
    with pytest.raises(UniverseEmptyError):
        load_universe(symbols=[])


def test_build_cross_section_panel_features(tmp_path: Path) -> None:
    asof = date(2026, 9, 2)
    bars_a = _synth_bars("600519", asof, n=70, base=1400.0)
    bars_b = _synth_bars("000001", asof, n=70, base=11.0)
    # Make 000001 look like a stronger reversal (recent dip).
    for row in bars_b[-5:]:
        row["close"] = float(row["close"]) * 0.92
        row["open"] = float(row["open"]) * 0.92

    provider = _FakeDaily({"600519": bars_a, "000001": bars_b})
    panel = build_cross_section_panel(
        asof=asof,
        symbols=["600519", "000001"],
        daily_provider=provider,
        fund_flow_provider=_FakeFundFlow(),
        adjust_kind=None,
    )
    assert len(panel) == 2
    assert set(panel["symbol"]) == {"600519", "000001"}
    for col in ("vol20", "rev_chg", "ma20", "ma60", "trend_up", "rs20", "main_net"):
        assert col in panel.columns
    assert panel["ma20"].notna().all()
    assert panel["ma60"].notna().all()

    out = panel_to_csv(panel, tmp_path / "panel.csv")
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "composite_score" not in text  # panel only; scoring is separate
    assert "600519" in text


def test_panel_requires_daily_and_asof_bar() -> None:
    asof = date(2026, 9, 2)
    with pytest.raises(ValueError, match="daily"):
        build_cross_section_panel(asof=asof, symbols=["600519"])

    # History exists but no bar on asof → empty panel (strict PIT).
    earlier = asof - timedelta(days=1)
    while earlier.weekday() >= 5:
        earlier -= timedelta(days=1)
    bars = _synth_bars("600519", earlier, n=70)
    provider = _FakeDaily({"600519": bars})
    panel = build_cross_section_panel(
        asof=asof,
        symbols=["600519"],
        daily_provider=provider,
        adjust_kind=None,
    )
    assert panel.empty
