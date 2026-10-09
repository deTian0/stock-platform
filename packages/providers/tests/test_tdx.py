"""Tests for the 通达信 (TDX) local .day provider (synthetic binary, zero network)."""

from __future__ import annotations

import struct
from datetime import date

import pytest

from stock_platform_providers.tdx import (
    ENV_TDX_ROOT,
    TdxProvider,
    parse_day_file,
    resolve_tdx_root,
)

_REC = struct.Struct("<IIIIIfII")


def _pack(ymd: int, o: int, h: int, l: int, c: int, amount: float, vol: int) -> bytes:
    return _REC.pack(ymd, o, h, l, c, amount, vol, 0)


def _write_day(tmp_path, code: str, records: bytes) -> None:
    prefix = {"600519": "sh", "000001": "sz", "430047": "bj"}[code]
    d = tmp_path / "vipdoc" / prefix / "lday"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{prefix}{code}.day").write_bytes(records)


def _sample_records() -> bytes:
    # 600519: 2026-01-02 open 100 close 101.5, and 2026-01-03 open 101.5 close 102
    return (
        _pack(20260102, 10000, 10250, 9950, 10150, 1_000_000.0, 5000)
        + _pack(20260103, 10150, 10300, 10100, 10200, 1_200_000.0, 5200)
    )


def test_parse_day_file_roundtrip(tmp_path) -> None:
    _write_day(tmp_path, "600519", _sample_records())
    path = tmp_path / "vipdoc" / "sh" / "lday" / "sh600519.day"
    bars = parse_day_file(path)
    assert len(bars) == 2
    assert bars[0]["date"] == "2026-01-02"
    assert bars[0]["open"] == 100.0
    assert bars[0]["close"] == 101.5
    assert bars[0]["volume"] == 5000.0
    assert bars[0]["amount"] == 1_000_000.0


def test_resolve_tdx_root_env(tmp_path) -> None:
    (tmp_path / "vipdoc").mkdir()
    assert resolve_tdx_root(env={ENV_TDX_ROOT: str(tmp_path)}) == tmp_path


def test_resolve_tdx_root_missing() -> None:
    assert resolve_tdx_root(env={}) is None


def test_provider_requires_root() -> None:
    with pytest.raises(FileNotFoundError):
        TdxProvider(root="Z:/definitely/missing/tdx")


def test_get_daily_reads_day_file(tmp_path) -> None:
    _write_day(tmp_path, "600519", _sample_records())
    provider = TdxProvider(root=tmp_path)
    rows = provider.get_daily(["600519"])
    assert len(rows) == 2
    assert rows[0]["symbol"] == "600519"
    assert rows[0]["date"] == "2026-01-02"
    assert rows[0]["close"] == 101.5
    assert rows[0]["source"] == "tdx"


def test_get_daily_date_filter(tmp_path) -> None:
    _write_day(tmp_path, "600519", _sample_records())
    provider = TdxProvider(root=tmp_path)
    rows = provider.get_daily(["600519"], start=date(2026, 1, 3))
    assert [r["date"] for r in rows] == ["2026-01-03"]


def test_get_realtime_not_implemented(tmp_path) -> None:
    _write_day(tmp_path, "600519", _sample_records())
    provider = TdxProvider(root=tmp_path)
    with pytest.raises(NotImplementedError):
        provider.get_realtime(["600519"])
