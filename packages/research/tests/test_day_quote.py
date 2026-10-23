"""``day_quote`` 单元测试：四价派生、四轴归因、汇总与渲染口径。"""

from __future__ import annotations

from datetime import date, timedelta

from stock_platform_research.day_quote import (
    OHLC_MISSING,
    OHLC_PROVIDER,
    build_day_quote,
    classify_row,
    explain_row,
    render_day_quote_markdown,
)

ASOF = "2026-10-22"


def _bars(closes: list[float], *, vols: list[float] | None = None, start: date | None = None):
    """构造升序日线；``vols`` 缺省全 1000。"""
    start = start or date(2026, 9, 1)
    outs = []
    for i, close in enumerate(closes):
        outs.append(
            {
                "symbol": "600000",
                "date": (start + timedelta(days=i)).isoformat(),
                "close": close,
                "volume": (vols[i] if vols and i < len(vols) else 1000.0),
            }
        )
    return outs


def _flat(n: int, price: float, vol: float = 1000.0) -> list[dict]:
    """连续 n 根等价横盘 bar，保证 asof 落在最后一根。"""
    start = date(2026, 1, 1)
    return [
        {
            "symbol": "600000",
            "date": (start + timedelta(days=i)).isoformat(),
            "close": price,
            "volume": vol,
        }
        for i in range(n)
    ]


# --------------------------------------------------------------------------- #
# 四价派生
# --------------------------------------------------------------------------- #
def test_gap_and_intraday_use_prev_close_and_open():
    bars = _flat(25, 10.0)
    bars.append({"symbol": "600000", "date": ASOF, "close": 10.5, "volume": 1000.0})
    payload = build_day_quote(
        [{"symbol": "600000", "name": "浦发银行", "bucket": "pick"}],
        asof=ASOF,
        bars_by_symbol={"600000": bars},
        benchmark_symbol="000905",
        benchmark_bars=[],
        ohlc_by_symbol={"600000": {"open": 9.8, "high": 10.6, "low": 9.7, "close": 10.5}},
        ohlc_sources={"600000": OHLC_PROVIDER},
    )
    row = payload["rows"][0]
    assert row["prevClose"] == 10.0
    assert row["open"] == 9.8
    assert row["close"] == 10.5
    assert abs(row["pct"] - 0.05) < 1e-9
    assert abs(row["gap"] - (-0.02)) < 1e-9
    assert abs(row["intraday"] - (10.5 / 9.8 - 1)) < 1e-9
    assert abs(row["amplitude"] - (0.9 / 10.0)) < 1e-9
    assert row["ohlcSource"] == OHLC_PROVIDER


def test_missing_ohlc_degrades_without_zeros():
    bars = _flat(25, 10.0)
    bars.append({"symbol": "600000", "date": ASOF, "close": 10.5, "volume": 1000.0})
    payload = build_day_quote(
        [{"symbol": "600000", "name": "浦发银行", "bucket": "pick"}],
        asof=ASOF,
        bars_by_symbol={"600000": bars},
        benchmark_symbol="000905",
        ohlc_by_symbol={},
    )
    row = payload["rows"][0]
    assert row["open"] is None and row["high"] is None and row["low"] is None
    assert row["ohlcSource"] == OHLC_MISSING
    assert row["gap"] is None and row["intraday"] is None and row["amplitude"] is None
    assert "缺失" in row["reason"]
    assert payload["summary"]["missingOhlc"] == 1


def test_no_bars_yields_honest_empty_row():
    payload = build_day_quote(
        [{"symbol": "588080", "name": "科创板50", "bucket": "holding"}],
        asof=ASOF,
        bars_by_symbol={},
        benchmark_symbol="000905",
    )
    row = payload["rows"][0]
    assert row["close"] is None and row["pct"] is None
    assert row["reason"] == "无当日行情（停牌/未入库），不计涨跌"
    assert payload["summary"]["counted"] == 0


def test_vol_ratio_excludes_asof_bar():
    """当日爆量不应摊薄自己的基准：分母只取前 20 根。"""
    bars = _flat(25, 10.0, vol=1000.0)
    bars.append({"symbol": "600000", "date": ASOF, "close": 10.5, "volume": 2000.0})
    payload = build_day_quote(
        [{"symbol": "600000", "name": "浦发银行", "bucket": "pick"}],
        asof=ASOF,
        bars_by_symbol={"600000": bars},
        benchmark_symbol="000905",
    )
    assert abs(payload["rows"][0]["volRatio"] - 2.0) < 1e-9


def test_ma20_needs_full_window():
    bars = _flat(10, 10.0)
    bars.append({"symbol": "600000", "date": ASOF, "close": 10.5, "volume": 1000.0})
    payload = build_day_quote(
        [{"symbol": "600000", "name": "浦发银行", "bucket": "pick"}],
        asof=ASOF,
        bars_by_symbol={"600000": bars},
        benchmark_symbol="000905",
    )
    row = payload["rows"][0]
    assert row["ma20"] is None and row["vsMa20"] is None
    assert "站上20日线" not in row["tags"] and "20日线下方" not in row["tags"]


def test_stale_bar_flagged():
    """asof 当日无 K 线（停牌）：不装成当日行情，只标记。"""
    bars = _flat(25, 10.0)
    payload = build_day_quote(
        [{"symbol": "600000", "name": "浦发银行", "bucket": "pick"}],
        asof=ASOF,
        bars_by_symbol={"600000": bars},
        benchmark_symbol="000905",
    )
    row = payload["rows"][0]
    assert row["staleBars"] == 1
    assert "当日无K线" in row["tags"]


# --------------------------------------------------------------------------- #
# 四轴归因
# --------------------------------------------------------------------------- #
def _row(**kw):
    base = {
        "pct": 0.02,
        "gap": 0.0,
        "intraday": 0.02,
        "high": 10.2,
        "low": 10.0,
        "close": 10.2,
        "prevClose": 10.0,
        "volRatio": 1.0,
        "dayAlpha": 0.0,
        "vsMa20": 0.01,
    }
    base.update(kw)
    return base


def test_low_open_high_close_with_heavy_volume():
    tags = classify_row(_row(pct=0.02, gap=-0.015, intraday=0.036, volRatio=1.8))
    assert "低开高走" in tags
    assert "放量上涨" in tags
    assert "站上20日线" in tags


def test_high_open_low_close():
    tags = classify_row(_row(pct=-0.02, gap=0.015, intraday=-0.034, volRatio=1.6))
    assert "高开低走" in tags
    assert "放量下跌" in tags


def test_upper_wick_fade():
    """冲高回落：上影 >=1% 且收盘落在全天区间下三分之一。"""
    tags = classify_row(_row(pct=0.005, gap=0.0, intraday=0.005, high=10.5, low=10.0, close=10.05))
    assert "冲高回落" in tags


def test_lower_wick_recovery():
    tags = classify_row(_row(pct=0.01, gap=0.0, intraday=0.01, high=10.15, low=9.5, close=10.1))
    assert "探底回升" in tags


def test_flat_band():
    tags = classify_row(_row(pct=0.002, gap=0.0, intraday=0.002, high=10.02, low=9.99, close=10.02))
    assert "窄幅整理" in tags


def test_relative_benchmark_tags():
    assert "强于基准" in classify_row(_row(pct=0.03, dayAlpha=0.02))
    assert "弱于基准" in classify_row(_row(pct=-0.03, dayAlpha=-0.02))
    assert "随基准" in classify_row(_row(pct=0.01, dayAlpha=0.001))


def test_explain_row_mentions_driver():
    text = explain_row({**_row(pct=0.02, gap=-0.01, intraday=0.03, volRatio=1.9, dayAlpha=0.015), "tags": classify_row(_row(pct=0.02, gap=-0.01, intraday=0.03, volRatio=1.9, dayAlpha=0.015))})
    assert "上涨" in text
    assert "放量" in text
    assert "⇒" in text


def test_explain_row_no_ohlc_states_it():
    text = explain_row({"close": 10.0, "pct": 0.01, "tags": [], "open": None})
    assert "开/高/低缺失" in text


# --------------------------------------------------------------------------- #
# 汇总 / 渲染
# --------------------------------------------------------------------------- #
def _payload_two_rows():
    bars_a = _flat(25, 10.0)
    bars_a.append({"symbol": "600000", "date": ASOF, "close": 10.5, "volume": 1000.0})
    bars_b = _flat(25, 20.0)
    bars_b.append({"symbol": "600001", "date": ASOF, "close": 19.6, "volume": 1000.0})
    bench = _flat(25, 8.0)
    bench.append({"symbol": "000905", "date": ASOF, "close": 7.92, "volume": 1000.0})
    return build_day_quote(
        [
            {"symbol": "600000", "name": "浦发银行", "bucket": "pick"},
            {"symbol": "600001", "name": "邯郸钢铁", "bucket": "holding"},
            {"symbol": "600000", "name": "浦发银行", "bucket": "pick"},  # 重复应去重
        ],
        asof=ASOF,
        bars_by_symbol={"600000": bars_a, "600001": bars_b},
        benchmark_symbol="000905",
        benchmark_bars=bench,
    )


def test_summary_counts_and_benchmark_excluded():
    payload = _payload_two_rows()
    assert len(payload["rows"]) == 2  # 去重
    s = payload["summary"]
    assert s["counted"] == 2
    assert s["upCount"] == 1 and s["downCount"] == 1
    assert s["best"]["symbol"] == "600000"
    assert s["worst"]["symbol"] == "600001"
    # 基准单独成行，不参与涨跌家数
    assert payload["benchmark"]["symbol"] == "000905"
    assert abs(payload["benchmark"]["pct"] - (-0.01)) < 1e-9


def test_day_alpha_relative_to_benchmark():
    payload = _payload_two_rows()
    rows = {r["symbol"]: r for r in payload["rows"]}
    assert abs(rows["600000"]["dayAlpha"] - (0.05 - (-0.01))) < 1e-9


def test_benchmark_row_has_no_alpha():
    payload = _payload_two_rows()
    assert payload["benchmark"]["dayAlpha"] is None


def test_render_contains_required_sections():
    md = render_day_quote_markdown(_payload_two_rows())
    assert "基准背景" in md
    assert "涨跌概况" in md
    assert "逐只明细" in md
    assert "涨跌原因" in md
    assert "量化归因" in md
    assert "非投资建议" in md


def test_render_surfaces_benchmark_warning():
    payload = _payload_two_rows()
    payload["benchmarkWarning"] = "基准是个股"
    md = render_day_quote_markdown(payload)
    assert "基准提醒" in md and "基准是个股" in md


def test_attribution_kind_is_quantitative():
    payload = _payload_two_rows()
    assert payload["attributionKind"] == "quantitative"
    assert payload["liveTradingEnabled"] is False
