"""Static checks that Workbench format helpers stay present and coherent.

Browser JS is not executed here; we assert the progressive-enhancement helpers
shipped in app.js so regressions (deleted formatters / missing realtime) fail CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "src" / "stock_platform_workbench" / "static" / "app.js"
HTML = ROOT / "src" / "stock_platform_workbench" / "templates" / "index.html"


@pytest.mark.unit
def test_format_helpers_defined() -> None:
    js_text = JS.read_text(encoding="utf-8")
    for name in (
        "formatPrice",
        "formatPct",
        "formatMoney",
        "formatVolume",
        "formatFactor",
        "formatSharesWan",
        "formatSentiment",
        "signedClass",
        "emptyTable",
        "setRawJson",
        "marketMeta",
        "formatErrorMessage",
        "formatBriefError",
        "setRecommendBusy",
        "renderRealtimeCards",
        "renderNewsList",
    ):
        assert f"function {name}" in js_text


@pytest.mark.unit
def test_recommend_ui_has_result_header_and_loading() -> None:
    html = HTML.read_text(encoding="utf-8")
    assert 'id="recommend-kv"' in html
    assert 'id="recommend-loading"' in html
    assert "今日选股结果" in html
    assert "写入纸面（SIMULATE）" in html
    assert "关键理由" in html
    assert 'id="recommend-history-table"' in html
    assert "历史推荐" in html
    assert "wizard-checklist" in html
    assert "主流程 · 第 1 步" in html
    assert "主流程 · 第 2 步" in html
    assert "主流程 · 第 3 步" in html
    assert 'href="#wizard"' in html
    assert "① 向导" in html
    js = JS.read_text(encoding="utf-8")
    assert "universeSize" in js
    assert "gatesRelaxed" in js
    assert "generatedAt" in js
    assert "__recommendLoadingHint" in js
    assert 'value || "10"' in js or '|| "10"' in js
    assert "loadRecommendHistory" in js
    assert "/api/research/briefs" in js
    assert "暂无历史推荐" in js
    assert "fail-closed" in js


@pytest.mark.unit
def test_format_money_uses_yi_wan() -> None:
    js_text = JS.read_text(encoding="utf-8")
    assert '+"亿"' in js_text or '+ "亿"' in js_text
    assert '+"万"' in js_text or '+ "万"' in js_text


@pytest.mark.unit
def test_format_pct_multiplies_decimal() -> None:
    assert "n * 100" in JS.read_text(encoding="utf-8")


@pytest.mark.unit
def test_realtime_and_news_wired() -> None:
    html = HTML.read_text(encoding="utf-8")
    assert 'id="realtime-form"' in html
    assert 'id="realtime-cards"' in html
    assert 'id="news-list"' in html
    js = JS.read_text(encoding="utf-8")
    assert 'addEventListener("submit", loadRealtime)' in js
    assert "/api/market/realtime" in js


@pytest.mark.unit
def test_portfolio_backtest_chart_is_wired_without_new_deps() -> None:
    """B6: net-value curve + drawdown band + linked daily table stay in app.js."""
    html = HTML.read_text(encoding="utf-8")
    for el_id in (
        'id="pf-form"',
        'id="pf-chart"',
        'id="pf-chart-wrap"',
        'id="pf-table"',
        'id="pf-table-wrap"',
        'id="pf-json"',
    ):
        assert el_id in html
    js = JS.read_text(encoding="utf-8")
    for name in (
        "function renderPortfolioChart",
        "function renderPortfolioTable",
        "function pfHighlight",
        "function runPortfolioBacktest",
        "function pfPrefillRange",
    ):
        assert name in js
    assert "/api/research/backtest/portfolio" in js
    # Chart is hand-rolled SVG — no plotting library is imported.
    assert 'createElementNS("http://www.w3.org/2000/svg"' in js
    for lib in ("chart.js", "Chart.js", "cdn.jsdelivr.net", "echarts", "plotly", "d3."):
        assert lib not in js
    # Form + prefill are registered at boot.
    assert '$("pf-form").addEventListener("submit", runPortfolioBacktest)' in js
    # Curve, band and table all read the same `daily` array (index == day).
    assert "pfState.daily = daily" in js
