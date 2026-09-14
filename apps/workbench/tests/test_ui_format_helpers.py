"""Static checks that Workbench format helpers stay present and coherent.

Browser JS is not executed here; we assert the progressive-enhancement helpers
shipped in app.js so regressions (deleted formatters / missing realtime) fail CI.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "src" / "stock_platform_workbench" / "static" / "app.js"
HTML = ROOT / "src" / "stock_platform_workbench" / "templates" / "index.html"


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
        "renderRealtimeCards",
        "renderNewsList",
    ):
        assert f"function {name}" in js_text


def test_format_money_uses_yi_wan() -> None:
    js_text = JS.read_text(encoding="utf-8")
    assert '+"亿"' in js_text or '+ "亿"' in js_text
    assert '+"万"' in js_text or '+ "万"' in js_text


def test_format_pct_multiplies_decimal() -> None:
    assert "n * 100" in JS.read_text(encoding="utf-8")


def test_realtime_and_news_wired() -> None:
    html = HTML.read_text(encoding="utf-8")
    assert 'id="realtime-form"' in html
    assert 'id="realtime-cards"' in html
    assert 'id="news-list"' in html
    js = JS.read_text(encoding="utf-8")
    assert 'addEventListener("submit", loadRealtime)' in js
    assert "/api/market/realtime" in js
