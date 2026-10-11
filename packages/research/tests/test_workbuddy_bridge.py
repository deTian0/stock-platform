"""Tests for the WorkBuddy MCP bridge (offline — no subprocess, no network).

The real ``westock`` CLI is exercised once by hand (see
``docs/contracts/data-source-adapters.md`` §3 for the recorded figures); here
every test injects a *runner* so parsing, the writer hand-off and the failure
paths are covered deterministically.
"""

from __future__ import annotations

import json

import pytest

from stock_platform_research.workbuddy_bridge import (
    ENV_WESTOCK_BIN,
    ENV_WORKBUDDY_CACHE_DIR,
    BridgeReport,
    kline_row_to_bar,
    load_symbols_file,
    parse_markdown_tables,
    quote_row_to_quote,
    resolve_westock_bin,
    rows_from_table,
    run_bridge,
)

@pytest.fixture()
def fake_bin(tmp_path, monkeypatch):
    """A real on-disk stub standing in for the westock executable.

    Tests must not depend on the host having `westock` on PATH (this repo's CI
    and dev shells both vary), so every `run_bridge` test points `--bin` at an
    actual file and injects a fake runner for the subprocess itself.
    """
    exe = tmp_path / "westock-stub.exe"
    exe.write_text("", encoding="utf-8")
    return str(exe)


# Real shape captured from `westock kline sh600519 --period day --limit 5`.
KLINE_SINGLE = """| date | open | last | high | low | volume | amount | exchange | change_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-09 | 1255.42 | 1263 | 1282 | 1255.42 | 35111 | 4453220000 | 0.28 | 0.5741405808 |
| 2026-10-08 | 1252.9 | 1255.79 | 1258 | 1242 | 25168 | 3145410000 | 0.2 | -0.2248494383 |
"""

# Real shape from `westock kline sh600519,sz000001 --period day --limit 2`:
# a [Batch] status line then one table carrying a leading `code` column.
KLINE_BATCH = """
[Batch] 状态: success | 总数: 2 | 成功: 2 | 失败: 0

| code | date | open | last | high | low | volume | amount | exchange | change_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sz000001 | 2026-10-09 | 11.78 | 11.59 | 11.89 | 11.58 | 1078106 | 1259720000 | 0.56 | -1.6129032258 |
| sz000001 | 2026-10-08 | 11.57 | 11.78 | 11.87 | 11.54 | 1481686 | 1743400000 | 0.76 | 1.8150388937 |
| sh600519 | 2026-10-09 | 1255.42 | 1263 | 1282 | 1255.42 | 35111 | 4453220000 | 0.28 | 0.5741405808 |
| sh600519 | 2026-10-08 | 1252.9 | 1255.79 | 1258 | 1242 | 25168 | 3145410000 | 0.2 | -0.2248494383 |
"""

QUOTE_SINGLE = """| code | market_type | name | symbol | price | prev_close | open | high | low | volume | amount | change | change_percent | turnover_rate | time | pe_ratio | pb_ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sh600519 | 1 | 贵州茅台 | sh600519 | 1263 | 1255.79 | 1255.42 | 1282 | 1255.42 | 35111 | 4453223189 | 7.21 | 0.57 | 0.28 | 2026-10-09 | 19.39 | 6.28 |
"""


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #
def test_parse_single_table() -> None:
    tables = parse_markdown_tables(KLINE_SINGLE)
    assert len(tables) == 1
    assert tables[0]["columns"][0] == "date"
    assert "last" in tables[0]["columns"]
    assert len(tables[0]["rows"]) == 2


def test_parse_batch_skips_status_line() -> None:
    tables = parse_markdown_tables(KLINE_BATCH)
    assert len(tables) == 1
    assert tables[0]["columns"][0] == "code"
    assert len(tables[0]["rows"]) == 4


def test_rows_from_table_pads_short_rows() -> None:
    table = {"columns": ["a", "b", "c"], "rows": [["1", "2"]]}
    assert rows_from_table(table) == [{"a": "1", "b": "2", "c": ""}]


def test_parse_handles_empty_and_noise() -> None:
    assert parse_markdown_tables("") == []
    assert parse_markdown_tables("no table here\njust prose") == []


# --------------------------------------------------------------------------- #
# field mapping
# --------------------------------------------------------------------------- #
def test_kline_row_maps_last_to_close_and_flags_percent() -> None:
    row = rows_from_table(parse_markdown_tables(KLINE_SINGLE)[0])[0]
    bar = kline_row_to_bar(row, symbol="600519")
    assert bar["close"] == 1263.0
    assert bar["open"] == 1255.42
    assert bar["high"] == 1282.0
    assert bar["low"] == 1255.42
    assert bar["date"] == "2026-10-09"
    assert bar["change_pct"] == pytest.approx(0.5741405808)
    # percent is flagged so the normalizer divides by 100.
    assert bar["pct_unit"] == "percent"
    # `exchange` is a turnover rate, not an exchange code — never smuggled in.
    assert "exchange" not in bar
    assert bar["symbol"] == "600519"


def test_quote_row_maps_contract_fields() -> None:
    row = rows_from_table(parse_markdown_tables(QUOTE_SINGLE)[0])[0]
    quote = quote_row_to_quote(row, symbol="600519")
    assert quote["price"] == 1263.0
    assert quote["prev_close"] == 1255.79
    assert quote["change_amount"] == 7.21
    assert quote["change_pct"] == pytest.approx(0.57)
    assert quote["pct_unit"] == "percent"
    assert quote["time"] == "2026-10-09"
    # extras survive for future datasets without breaking the contract
    assert quote["pe_ratio"] == "19.39"


# --------------------------------------------------------------------------- #
# binary resolution
# --------------------------------------------------------------------------- #
def test_resolve_westock_bin_env_override(tmp_path) -> None:
    fake = tmp_path / "westock.exe"
    fake.write_text("", encoding="utf-8")
    assert resolve_westock_bin({ENV_WESTOCK_BIN: str(fake)}) == str(fake)


def test_resolve_westock_bin_missing_override_returns_none(monkeypatch) -> None:
    """A bogus *path* override must not silently resolve to a PATH binary."""
    monkeypatch.setattr(
        "stock_platform_research.workbuddy_bridge.shutil.which",
        lambda name: None,
    )
    assert resolve_westock_bin({ENV_WESTOCK_BIN: "C:/nope/westock.exe"}) is None


def test_resolve_westock_bin_bare_name_uses_path(monkeypatch) -> None:
    """A bare command name is a PATH lookup, not a CWD path."""
    monkeypatch.setattr(
        "stock_platform_research.workbuddy_bridge.shutil.which",
        lambda name: "/fake/bin/westock" if name == "westock" else None,
    )
    assert resolve_westock_bin({ENV_WESTOCK_BIN: "westock"}) == "/fake/bin/westock"


# --------------------------------------------------------------------------- #
# run_bridge (injected runner — no subprocess)
# --------------------------------------------------------------------------- #
def _runner_factory(payload_by_cmd):
    calls = []

    def runner(binary, args):
        calls.append((binary, list(args)))
        cmd = args[0]
        text = payload_by_cmd.get(cmd, "")
        # an unknown code yields no rows
        return (0, text)

    runner.calls = calls  # type: ignore[attr-defined]
    return runner


def test_run_bridge_daily_writes_cache(tmp_path, fake_bin) -> None:
    runner = _runner_factory({"kline": KLINE_SINGLE})
    rep = run_bridge(
        ["sh600519"],
        cache_dir=tmp_path,
        binary=fake_bin,
        datasets=["daily"],
        limit=5,
        runner=runner,
    )
    assert rep.success
    assert rep.ok_count == 1
    assert rep.bar_count == 2
    cache_file = tmp_path / "daily_600519.json"
    assert cache_file.is_file()
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert payload["symbol"] == "600519"
    assert len(payload["bars"]) == 2
    assert payload["bars"][0]["close"] == 1263.0
    # the batch flag reached the CLI
    _, args = runner.calls[0]
    assert args[:3] == ["kline", "sh600519", "--period"]


def test_run_bridge_batch_splits_symbols(tmp_path, fake_bin) -> None:
    runner = _runner_factory({"kline": KLINE_BATCH})
    rep = run_bridge(
        ["sh600519", "sz000001"],
        cache_dir=tmp_path,
        binary=fake_bin,
        datasets=["daily"],
        runner=runner,
    )
    assert rep.ok_count == 2
    assert (tmp_path / "daily_600519.json").is_file()
    assert (tmp_path / "daily_000001.json").is_file()
    # bare codes, no exchange prefix — matches the provider's file naming
    assert not (tmp_path / "daily_sh600519.json").exists()


def test_run_bridge_unknown_symbol_is_a_failure_not_a_crash(tmp_path, fake_bin) -> None:
    """A single-symbol table carries no `code` column, so a 2-symbol batch
    cannot be attributed. The rows must be reported as a warning and no bars
    written — never silently assigned to the first symbol."""
    runner = _runner_factory({"kline": KLINE_SINGLE})  # no `code` column anywhere
    rep = run_bridge(
        ["sh600519", "sz000001"],
        cache_dir=tmp_path,
        binary=fake_bin,
        datasets=["daily"],
        runner=runner,
    )
    assert not rep.success
    assert rep.ok_count == 0
    assert {f.symbol for f in rep.failures} == {"sh600519", "sz000001"}
    assert any("not attributable" in w for w in rep.warnings)
    assert not list(tmp_path.glob("*.json"))


def test_run_bridge_single_symbol_without_code_column(tmp_path, fake_bin) -> None:
    """A lone symbol is still attributable when the response omits `code`."""
    runner = _runner_factory({"kline": KLINE_SINGLE})
    rep = run_bridge(
        ["sh600519"],
        cache_dir=tmp_path,
        binary=fake_bin,
        datasets=["daily"],
        runner=runner,
    )
    assert rep.success
    assert (tmp_path / "daily_600519.json").is_file()


def test_run_bridge_realtime(tmp_path, fake_bin) -> None:
    runner = _runner_factory({"quote": QUOTE_SINGLE})
    rep = run_bridge(
        ["sh600519"],
        cache_dir=tmp_path,
        binary=fake_bin,
        datasets=["realtime"],
        runner=runner,
    )
    assert rep.ok_count == 1
    payload = json.loads((tmp_path / "realtime_600519.json").read_text(encoding="utf-8"))
    assert payload["price"] == 1263.0
    assert payload["symbol"] == "600519"


def test_run_bridge_dry_run_writes_nothing(tmp_path, fake_bin) -> None:
    runner = _runner_factory({"kline": KLINE_SINGLE})
    rep = run_bridge(
        ["sh600519"],
        cache_dir=tmp_path,
        binary=fake_bin,
        datasets=["daily"],
        runner=runner,
        dry_run=True,
    )
    assert rep.ok_count == 1
    assert rep.bar_count == 2
    assert not list(tmp_path.glob("*.json"))


def test_run_bridge_requires_binary(tmp_path) -> None:
    # An explicitly-absent binary must fail loudly rather than silently
    # falling back to whatever happens to be on PATH.
    with pytest.raises(SystemExit):
        run_bridge(
            ["600519"],
            cache_dir=tmp_path,
            binary=str(tmp_path / "nope-westock.exe"),
            runner=lambda b, a: (0, ""),
            env={},
        )


def test_run_bridge_discovers_binary_when_not_specified(tmp_path, monkeypatch) -> None:
    """With no --bin and no env override, discovery is used (and may fail)."""
    monkeypatch.setattr(
        "stock_platform_research.workbuddy_bridge.resolve_westock_bin",
        lambda env=None: None,
    )
    with pytest.raises(SystemExit):
        run_bridge(["600519"], cache_dir=tmp_path, runner=lambda b, a: (0, ""), env={})


def test_run_bridge_requires_cache_dir(tmp_path, fake_bin) -> None:
    with pytest.raises(SystemExit):
        run_bridge(
            ["600519"],
            cache_dir=None,
            binary=fake_bin,
            runner=lambda b, a: (0, ""),
            env={},
        )


def test_run_bridge_reports_version_and_provenance(tmp_path, fake_bin) -> None:
    runner = _runner_factory({"kline": KLINE_SINGLE})
    rep = run_bridge(
        ["sh600519"],
        cache_dir=tmp_path,
        binary=fake_bin,
        datasets=["daily"],
        runner=runner,
    )
    # version probe uses the same injected runner -> empty payload, but the
    # binary path is always recorded.
    assert rep.binary == fake_bin
    assert rep.to_dict()["cacheDir"] == str(tmp_path)


# --------------------------------------------------------------------------- #
# symbols file
# --------------------------------------------------------------------------- #
def test_load_symbols_file(tmp_path) -> None:
    f = tmp_path / "watchlist.txt"
    f.write_text("# comment\nsh600519\n\nsz000001  # inline\n", encoding="utf-8")
    assert load_symbols_file(f) == ["sh600519", "sz000001"]


def test_bridge_report_defaults() -> None:
    rep = BridgeReport(cache_dir="x", binary="westock")
    assert not rep.success  # nothing done yet
    assert rep.to_dict()["itemCount"] == 0


def test_collision_sh000001_vs_sz000001_is_refused(tmp_path, fake_bin) -> None:
    """sh000001 (index) and sz000001 (stock) share one bare code → refuse."""
    runner = _runner_factory({"kline": KLINE_SINGLE})
    rep = run_bridge(
        ["sh000001", "sz000001"],
        cache_dir=tmp_path,
        binary=fake_bin,
        datasets=["daily"],
        runner=runner,
    )
    assert rep.items == []
    assert any("code collision on 000001" in w for w in rep.warnings)
    assert not list(tmp_path.glob("*.json"))
    # nothing was even fetched
    assert runner.calls == []


def test_collision_does_not_block_unambiguous_symbols(tmp_path, fake_bin) -> None:
    """A colliding pair is dropped; the rest still bridges."""
    runner = _runner_factory({"kline": KLINE_BATCH})
    rep = run_bridge(
        ["sh600519", "sh000001", "sz000001"],
        cache_dir=tmp_path,
        binary=fake_bin,
        datasets=["daily"],
        runner=runner,
    )
    assert (tmp_path / "daily_600519.json").is_file()
    assert any("code collision on 000001" in w for w in rep.warnings)
