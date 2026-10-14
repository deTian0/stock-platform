"""当日战绩（1 日窗口）聚合：口径正确性 + pending 诚实性 + 渲染格式。"""

from __future__ import annotations

from datetime import date

import pytest

from stock_platform_research.sameday import (
    render_sameday_markdown,
    summarize_sameday,
)

_BARS = {
    "600519": [
        {"date": "2026-09-02", "close": 100.0},
        {"date": "2026-09-03", "close": 110.0},  # +10%
    ],
    "000001": [
        {"date": "2026-09-02", "close": 10.0},
        {"date": "2026-09-03", "close": 9.5},  # -5%
    ],
    "000002": [
        {"date": "2026-09-02", "close": 20.0},  # 无后续 bar → pending
    ],
    "000905": [
        {"date": "2026-09-02", "close": 1000.0},
        {"date": "2026-09-03", "close": 900.0},  # -10%
    ],
}


def _get_daily(symbols, *, start: date, end: date):
    out = []
    for sym in symbols:
        for bar in _BARS.get(str(sym), []):
            d = date.fromisoformat(bar["date"])
            if start <= d <= end:
                out.append(dict(bar))
    return out


def _records():
    return [
        {
            "asof": "2026-09-02",
            "picks": [{"symbol": "600519"}, {"symbol": "000001"}, {"symbol": "000002"}],
        }
    ]


def test_summarize_sameday_one_day_window() -> None:
    out = summarize_sameday(_records(), get_daily=_get_daily, benchmark_symbol="000905")
    assert out["holding"] == "1d"
    assert out["pickCount"] == 3
    assert out["settledCount"] == 2
    assert out["pendingCount"] == 1  # 000002 没有次日 bar → 不填 0
    assert abs(out["avgRawReturn"] - 0.025) < 1e-9  # (10% + -5%) / 2
    assert abs(out["upRate"] - 0.5) < 1e-9
    assert out["best"] == pytest.approx(0.10) and out["worst"] == pytest.approx(-0.05)
    day = out["days"][0]
    assert day["benchmarkRawReturn"] is not None and abs(day["benchmarkRawReturn"] + 0.10) < 1e-9
    # alpha = raw − bench(-10%) → 20% 与 5%
    assert abs(out["avgAlpha"] - 0.125) < 1e-9
    assert abs(out["beatBenchmarkRate"] - 1.0) < 1e-9


def test_summarize_sameday_marks_noisy_sample() -> None:
    out = summarize_sameday(_records(), get_daily=_get_daily)
    assert out["sampleCount"] == 2
    assert out["sampleNote"] and "do not over-interpret" in out["sampleNote"]


def test_summarize_sameday_without_benchmark_leaves_alpha_empty() -> None:
    out = summarize_sameday(
        _records(), get_daily=_get_daily, with_benchmark=False, benchmark_symbol="000905"
    )
    assert out["avgAlpha"] is None
    assert out["benchmarkSampleCount"] == 0


def test_render_sameday_markdown_formats_rates_without_sign() -> None:
    md = render_sameday_markdown(summarize_sameday(_records(), get_daily=_get_daily))
    assert "| 胜率 upRate | 50.00% |" in md
    assert "+50.00%" not in md  # 比率不带正号
    assert "+2.50%" in md  # 收益带正号
    assert "当日战绩 ≠ 命中追踪" in md
    assert "2026-09-02" in md
