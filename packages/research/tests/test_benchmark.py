"""F1 — benchmark identity fail-closed + quote keys."""

from __future__ import annotations

from stock_platform_research.benchmark import (
    DEFAULT_BENCHMARK_SYMBOL,
    engine_benchmark_code,
    quote_benchmark_key,
    resolve_benchmark_identity,
    resolve_benchmark_symbol,
)


def test_default_benchmark_is_csi500_bare() -> None:
    assert resolve_benchmark_symbol() == "000905"
    assert DEFAULT_BENCHMARK_SYMBOL == "000905"


def test_quote_key_forces_sh_for_known_indexes() -> None:
    assert quote_benchmark_key("000905") == "sh000905"
    assert quote_benchmark_key("000300") == "sh000300"


def test_engine_code_uses_exchange_suffix() -> None:
    # Digit-prefix still maps 000905 → sz; engine warehouses historically used .SZ.
    assert engine_benchmark_code("000905") == "000905.SZ"
    assert engine_benchmark_code("510300") == "510300.SH"


def test_identity_ok_when_name_matches_index() -> None:
    ident = resolve_benchmark_identity("000905", name="中证500")
    assert ident["ok"] is True
    assert ident["alphaAvailable"] is True
    assert ident["warning"] is None
    assert ident["quoteKey"] == "sh000905"


def test_identity_fail_closed_on_stock_collision() -> None:
    ident = resolve_benchmark_identity("000905", name="厦门港务")
    assert ident["ok"] is False
    assert ident["alphaAvailable"] is False
    assert ident["warning"]
    assert "厦门港务" in ident["warning"]


def test_identity_from_names_map() -> None:
    ident = resolve_benchmark_identity("000905", names={"000905": "厦门港务"})
    assert ident["alphaAvailable"] is False
