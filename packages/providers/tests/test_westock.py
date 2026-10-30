"""WeStock CLI adapter — parser + provider, fully offline (injected runner)."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

import pytest

from stock_platform_providers import westock as ws

# ---------------------------------------------------------------- fixtures ---
# Trimmed from live payloads (2026-10-30); column ORDER is intentionally the same
# as the vendor for the first case and scrambled for the header-lookup case.
QUOTE_TABLE = """| code | market_type | market_name | name | symbol | price | prev_close | open | high | low | volume | amount | change | change_percent | turnover_rate | range_pct | time | pe_ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sh600519 | 1 | 上海主板 | 贵州茅台 | sh600519 | 1392.05 | 1354 | 1363 | 1393.37 | 1352.98 | 59927 | 8257381777.99 | 38.05 | 2.81 | 0.48 | 2.98 | 2026-10-30 | 21.37 |
| sz000533 | 51 | 深圳主板 | 顺钠股份 | sz000533 | 8.36 | 8.66 | 8.32 | 8.76 | 8.32 | 180089 | 152685916 | -0.3 | -3.46 | 2.63 | 5.08 | 2026-10-30 | 56.65 |
"""

QUOTE_STALE = """| symbol | price | prev_close | open | high | low | volume | amount | time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sh600519 | 1392.05 | 1354 | 1363 | 1393.37 | 1352.98 | 59927 | 8257381777 | 2026-10-29 |
"""

QUOTE_SUSPENDED = """| symbol | price | prev_close | open | high | low | volume | amount | time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sh600519 | 1392.05 | 1354 | 1363 | 1393.37 | 1352.98 | 59927 | 8257381777 | 2026-10-30 |
| sz000533 | 0 | 8.66 | 0 | 0 | 0 | 0 | 0 | 2026-10-30 |
"""

QUOTE_SHUFFLED = """| time | low | price | open | symbol | high | volume | amount | prev_close |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-30 | 1330.01 | 1354 | 1349.99 | sh600519 | 1356 | 42992 | 5797980000 | 1330.75 |
"""

KLINE_MULTI = """[Batch] 状态: success | 总数: 2 | 成功: 2 | 失败: 0

| code | date | open | last | high | low | volume | amount | exchange | change_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sh600519 | 2026-10-29 | 1349.99 | 1354 | 1356 | 1330.01 | 42992 | 5797980000 | 0.34 | 1.7471350742062748 |
| sh600519 | 2026-10-28 | 1354.98 | 1330.75 | 1354.98 | 1322.6 | 38805 | 5187320000 | 0.31 | -1.8548565528431367 |
| sz000533 | 2026-10-29 | 8.92 | 8.66 | 9.03 | 8.65 | 203724 | 179550000 | 2.97 | -1.8140589569161012 |
"""

KLINE_SINGLE = """| date | open | last | high | low | volume | amount | exchange | change_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-30 | 1363 | 1392.05 | 1393.37 | 1352.98 | 59927 | 8257381777.99 | 0.48 | 2.810192023633675 |
| 2026-10-29 | 1349.99 | 1354 | 1356 | 1330.01 | 42992 | 5797980000 | 0.34 | 1.7471350742062748 |
"""


# ------------------------------------------------------------- table parser ---
def test_parse_md_table_splits_header_and_rows():
    head, rows = ws.parse_md_table(QUOTE_TABLE)
    assert head[:3] == ["code", "market_type", "market_name"]
    assert len(rows) == 2
    assert rows[0][head.index("symbol")] == "sh600519"


def test_parse_md_table_skips_separator_and_noise():
    text = "[Batch] 状态: success\n\n" + KLINE_MULTI
    head, rows = ws.parse_md_table(text)
    assert head[0] == "code"
    assert len(rows) == 3


def test_parse_md_table_returns_empty_without_table():
    assert ws.parse_md_table("查询dayK线失败：service error") == ([], [])
    assert ws.parse_md_table("") == ([], [])


# ------------------------------------------------------------- quote parser ---
def test_parse_quote_rows_reads_by_header_name():
    rows = ws.parse_quote_rows(QUOTE_TABLE, "2026-10-30")
    assert set(rows) == {"600519", "000533"}
    assert rows["600519"] == {"open": 1363.0, "high": 1393.37, "low": 1352.98, "close": 1392.05}
    assert rows["000533"]["close"] == 8.36


def test_parse_quote_rows_survives_reordered_columns():
    rows = ws.parse_quote_rows(QUOTE_SHUFFLED, "2026-10-30")
    assert rows["600519"] == {"open": 1349.99, "high": 1356.0, "low": 1330.01, "close": 1354.0}


def test_parse_quote_rows_drops_stale_session():
    assert ws.parse_quote_rows(QUOTE_STALE, "2026-10-30") == {}


def test_parse_quote_rows_drops_suspended_rows():
    rows = ws.parse_quote_rows(QUOTE_SUSPENDED, "2026-10-30")
    assert set(rows) == {"600519"}  # 停牌行 open/close=0，整行丢弃，绝不补零


# ------------------------------------------------------------- kline parser ---
def test_parse_kline_rows_multi_code_uses_code_column():
    parsed = ws.parse_kline_rows(KLINE_MULTI)
    assert set(parsed) == {"600519", "000533"}
    assert [b["date"] for b in parsed["600519"]] == ["2026-10-29", "2026-10-28"]
    first = parsed["600519"][0]
    assert first["close"] == 1354.0
    assert first["volume"] == 42992.0
    assert first["amount"] == 5797980000.0
    assert first["pct_unit"] == "percent"


def test_parse_kline_rows_single_code_falls_back_to_symbols():
    parsed = ws.parse_kline_rows(KLINE_SINGLE, symbols=["600519"])
    assert set(parsed) == {"600519"}
    assert parsed["600519"][0]["date"] == "2026-10-30"


def test_parse_kline_rows_single_code_without_hint_is_empty():
    assert ws.parse_kline_rows(KLINE_SINGLE) == {}


def test_parse_kline_rows_ambiguous_hint_is_empty():
    assert ws.parse_kline_rows(KLINE_SINGLE, symbols=["600519", "000533"]) == {}


# ------------------------------------------------------- fetch_day_snapshot ---
def test_fetch_day_snapshot_uses_injected_runner():
    seen: list[list[str]] = []

    def _runner(args):
        seen.append(list(args))
        return QUOTE_TABLE

    rows, note = ws.fetch_day_snapshot(["600519", "000533"], "2026-10-30", runner=_runner)
    assert set(rows) == {"600519", "000533"}
    assert note is None
    assert seen[0][0] == "quote"
    assert seen[0][-2:] == ["--date", "2026-10-30"]


def test_fetch_day_snapshot_reports_missing_rows():
    def _runner(args):
        return QUOTE_TABLE

    rows, note = ws.fetch_day_snapshot(["600519", "600000"], "2026-10-30", runner=_runner)
    assert set(rows) == {"600519"}
    assert note and "缺 1/2" in note


def test_fetch_day_snapshot_never_raises():
    def _boom(args):
        raise RuntimeError("westock quote 失败：service error")

    rows, note = ws.fetch_day_snapshot(["600519"], "2026-10-30", runner=_boom)
    assert rows == {}
    assert note and "全部失败" in note


def test_fetch_day_snapshot_rejects_bad_date():
    rows, note = ws.fetch_day_snapshot(["600519"], "not-a-date", runner=lambda a: QUOTE_TABLE)
    assert rows == {}
    assert note and "非法交易日" in note


def test_fetch_day_snapshot_chunks_large_batches(monkeypatch):
    monkeypatch.setattr(ws, "QUOTE_CHUNK", 1)
    calls: list[int] = []

    def _runner(args):
        calls.append(len(args[1].split(",")))
        return QUOTE_TABLE

    ws.fetch_day_snapshot(["600519", "000533"], "2026-10-30", runner=_runner)
    assert calls == [1, 1]


# ---------------------------------------------------------------- provider ---
def test_provider_get_daily_requests_qfq(monkeypatch):
    seen: list[list[str]] = []

    def _runner(args):
        seen.append(list(args))
        return KLINE_MULTI

    provider = ws.WestockProvider(runner=_runner)
    rows = provider.get_daily(["600519", "000533"], start=date(2026, 10, 28), end=date(2026, 10, 29))

    assert seen and seen[0][0] == "kline"
    assert "--fq" in seen[0] and seen[0][seen[0].index("--fq") + 1] == "qfq"
    assert len(rows) == 3
    assert {r["symbol"] for r in rows} == {"600519", "000533"}
    assert rows[0]["symbol"] == "000533"  # 按 (symbol, date) 排序
    assert all(r["source"] == "westock" for r in rows)
    top = next(r for r in rows if r["symbol"] == "600519" and r["date"] == "2026-10-29")
    assert top["open"] == 1349.99
    assert top["close"] == 1354.0
    assert round(top["change_pct"], 6) == 0.017471  # percent → decimal


def test_provider_get_daily_backfills_pre_close():
    provider = ws.WestockProvider(runner=lambda args: KLINE_MULTI)
    rows = provider.get_daily(["600519"], start=date(2026, 10, 28), end=date(2026, 10, 29))
    by_date = {r["date"]: r for r in rows}
    assert by_date["2026-10-28"]["pre_close"] is None  # 窗口首根无前值
    assert by_date["2026-10-29"]["pre_close"] == 1330.75  # 取上一根 close


def test_provider_get_daily_filters_window(monkeypatch):
    provider = ws.WestockProvider(runner=lambda args: KLINE_MULTI)
    rows = provider.get_daily(["600519"], start=date(2026, 10, 29), end=date(2026, 10, 29))
    assert [r["date"] for r in rows] == ["2026-10-29"]


def test_provider_get_realtime_maps_quote_columns():
    provider = ws.WestockProvider(runner=lambda args: QUOTE_TABLE)
    rows = provider.get_realtime(["600519", "000533"])
    assert len(rows) == 2
    top = next(r for r in rows if r["symbol"] == "600519")
    assert top["name"] == "贵州茅台"
    assert top["price"] == 1392.05
    assert top["prev_close"] == 1354.0
    assert top["change_amount"] == 38.05
    assert round(top["change_pct"], 4) == 0.0281  # percent → decimal
    assert round(top["amplitude"], 4) == 0.0298
    expected = int(
        datetime(2026, 10, 30, 15, tzinfo=timezone(timedelta(hours=8))).timestamp() * 1000
    )
    assert top["asof_ts"] == expected  # 厂商只给日期，按北京时间 15:00 收盘定点


def test_provider_get_realtime_skips_rows_without_time():
    text = """| symbol | price | prev_close | name | volume | amount |
| --- | --- | --- | --- | --- | --- |
| sh600519 | 1392.05 | 1354 | 贵州茅台 | 59927 | 8257381777 |
"""
    rows = ws.WestockProvider(runner=lambda args: text).get_realtime(["600519"])
    assert rows == []


def test_provider_fails_closed_without_binary(monkeypatch):
    monkeypatch.setattr(ws, "resolve_westock_bin", lambda env=None: None)
    monkeypatch.delenv(ws.ENV_WESTOCK_BIN, raising=False)
    provider = ws.WestockProvider()
    with pytest.raises(RuntimeError) as excinfo:
        provider.get_daily(["600519"])
    assert "未找到 westock CLI" in str(excinfo.value)


def test_resolve_westock_bin_respects_env_override(tmp_path):
    fake = tmp_path / ("westock.exe" if os.name == "nt" else "westock")
    fake.write_text("", encoding="utf-8")
    assert ws.resolve_westock_bin({ws.ENV_WESTOCK_BIN: str(fake)}) == fake
    assert ws.resolve_westock_bin({ws.ENV_WESTOCK_BIN: str(tmp_path / "nope")}) is None


def test_run_cli_surfaces_vendor_error(monkeypatch, tmp_path):
    fake = tmp_path / ("westock.exe" if os.name == "nt" else "westock")
    fake.write_text("", encoding="utf-8")

    class _Proc:
        returncode = 1
        stdout = b""
        stderr = "查询dayK线失败：[code=1620053001] msg=service error".encode("utf-8")

    monkeypatch.setattr(ws.subprocess, "run", lambda *a, **k: _Proc())
    with pytest.raises(RuntimeError) as excinfo:
        ws.run_cli(["kline", "sh600519", "--fq", "bfq"], bin_path=fake)
    assert "1620053001" in str(excinfo.value)


def test_run_cli_without_binary_raises(monkeypatch):
    monkeypatch.setattr(ws, "resolve_westock_bin", lambda env=None: None)
    with pytest.raises(RuntimeError) as excinfo:
        ws.run_cli(["quote", "sh600519"])
    assert "未找到 westock CLI" in str(excinfo.value)
