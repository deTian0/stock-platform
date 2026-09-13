"""Tests for A-share symbol normalization."""

from __future__ import annotations

import pytest

from stock_platform_providers import (
    SymbolError,
    exchange_prefix,
    is_bse_symbol,
    normalize_symbol,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("600519", "600519"),
        ("000001", "000001"),
        ("SH600519", "600519"),
        ("sz000001", "000001"),
        ("600519.SH", "600519"),
        ("000001.SZ", "000001"),
        ("920001.BJ", "920001"),
        (" bj920001 ", "920001"),
        ("688017", "688017"),
    ],
)
def test_normalize_accepts_a_share_forms(raw: str, expected: str) -> None:
    assert normalize_symbol(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "00700",
        "0700.HK",
        "00700.HK",
        "AAPL",
        "BRK.B",
        "茅台",
        "",
        "   ",
        "12345",
        "1234567",
        "../etc",
    ],
)
def test_normalize_rejects_non_cn(raw: str) -> None:
    with pytest.raises(SymbolError):
        normalize_symbol(raw)


def test_normalize_rejects_non_cn_market() -> None:
    with pytest.raises(SymbolError, match="M5"):
        normalize_symbol("AAPL", market="US")


@pytest.mark.parametrize(
    "code,prefix",
    [
        ("600519", "sh"),
        ("900001", "sh"),
        ("000001", "sz"),
        ("300750", "sz"),
        ("688017", "sh"),
        ("830001", "bj"),
        ("430001", "bj"),
        ("920001", "bj"),
    ],
)
def test_exchange_prefix(code: str, prefix: str) -> None:
    assert exchange_prefix(code) == prefix


def test_bse_920_not_shanghai() -> None:
    """Regression: 920xxx must not follow leading-9 → sh."""
    assert exchange_prefix("920982") == "bj"
    assert is_bse_symbol("920982")
    assert is_bse_symbol("830001")
    assert not is_bse_symbol("600519")
