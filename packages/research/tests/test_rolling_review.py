"""Rolling recommend review (U7 light) — direction_accuracy 口径对齐."""

from __future__ import annotations

from datetime import date, timedelta

from stock_platform_research.rolling_review import (
    resolve_asof_window,
    run_rolling_recommend_review,
)


def _synthetic_bars(symbols: list[str], start: date, n_days: int = 80) -> list[dict]:
    """Deterministic up-trend bars so Buy picks settle directionOk=True often."""
    rows: list[dict] = []
    for i in range(n_days):
        d = start + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        for j, sym in enumerate(symbols):
            # Mild upward drift; symbol 0 slightly stronger.
            close = 10.0 + j + i * 0.05 + (0.02 if j == 0 else 0.0)
            rows.append(
                {
                    "symbol": sym,
                    "date": d.isoformat(),
                    "close": close,
                    "open": close * 0.99,
                    "volume": 1_000_000,
                }
            )
    return rows


def test_rolling_review_fail_closed_without_daily() -> None:
    out = run_rolling_recommend_review(get_daily=None, last_n=3)
    assert out["ok"] is False
    assert out["failClosed"] is True
    assert "ENGINE_MARKET_DB" in out["error"] or "日线" in out["error"]
    assert out["direction_accuracy"] is None if "direction_accuracy" in out else True


def test_rolling_review_aggregates_direction_accuracy() -> None:
    symbols = ["600519", "000001", "000858"]
    start = date(2026, 1, 2)
    all_bars = _synthetic_bars(symbols, start, n_days=90)

    def get_daily(syms: list[str], *, start: date, end: date) -> list[dict]:
        want = {str(s).zfill(6)[-6:] for s in syms}
        return [
            b
            for b in all_bars
            if b["symbol"] in want
            and start.isoformat() <= b["date"] <= end.isoformat()
        ]

    out = run_rolling_recommend_review(
        get_daily=get_daily,
        symbols=symbols,
        last_n=5,
        holding="1d",
        top_n=2,
        soft_gates=True,
        daily_source="fixture",
    )
    assert out["ok"] is True
    assert out["asofCount"] == 5
    assert out["settledCount"] >= 1
    assert out["direction_accuracy"] is not None
    assert out["directionAccuracy"] == out["direction_accuracy"]
    assert 0.0 <= float(out["direction_accuracy"]) <= 1.0
    assert len(out["days"]) == 5
    assert "pickSymbols" in out["days"][0]
    assert isinstance(out["days"][0]["pickSymbols"], list)


def test_resolve_asof_window_last_n() -> None:
    start = date(2026, 3, 1)
    bars = _synthetic_bars(["600519"], start, n_days=40)

    def get_daily(syms, *, start, end):
        return [
            b
            for b in bars
            if start.isoformat() <= b["date"] <= end.isoformat()
        ]

    dates = resolve_asof_window(get_daily, last_n=3)
    assert len(dates) == 3
    assert dates[0] < dates[-1]
