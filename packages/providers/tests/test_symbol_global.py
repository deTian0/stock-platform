"""US / HK symbol normalization + CN isolation."""

from __future__ import annotations

import pytest

from stock_platform_providers import SymbolError, normalize_symbol


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("AAPL", "AAPL"),
        ("aapl", "AAPL"),
        ("BRK.B", "BRK.B"),
        ("BRK-B", "BRK.B"),
        ("AAPL.US", "AAPL"),
    ],
)
def test_normalize_us(raw: str, expected: str) -> None:
    assert normalize_symbol(raw, market="US") == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("00700", "00700"),
        ("700", "00700"),
        ("0700.HK", "00700"),
        ("00700.HK", "00700"),
        ("hk00700", "00700"),
    ],
)
def test_normalize_hk(raw: str, expected: str) -> None:
    assert normalize_symbol(raw, market="HK") == expected


@pytest.mark.parametrize("raw", ["600519", "00700", "0700.HK", "", "茅台"])
def test_us_rejects_non_us(raw: str) -> None:
    with pytest.raises(SymbolError):
        normalize_symbol(raw, market="US")


@pytest.mark.parametrize("raw", ["AAPL", "600519", "123456", "茅台"])
def test_hk_rejects_non_hk(raw: str) -> None:
    with pytest.raises(SymbolError):
        normalize_symbol(raw, market="HK")


def test_cn_still_rejects_us_hk_forms() -> None:
    for raw in ("AAPL", "00700", "0700.HK"):
        with pytest.raises(SymbolError):
            normalize_symbol(raw, market="CN")


def test_unknown_market() -> None:
    with pytest.raises(SymbolError, match="not supported"):
        normalize_symbol("AAPL", market="JP")
