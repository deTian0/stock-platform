"""Benchmark identity — fail-closed when a bare code collides with a stock.

Engine ``market.db`` often stores ``000905`` / ``000905.SZ`` as the **stock**
厦门港务, while product docs treat ``000905`` as 中证500. Alpha must not silently
use a stock series as an index (ADR 0090 / F1).
"""

from __future__ import annotations

import os
import re
from typing import Any, Mapping

from stock_platform_providers import exchange_prefix

# Bare 6-digit code → substrings that must appear in fundamentals.name (any one).
KNOWN_INDEX_NAME_HINTS: dict[str, tuple[str, ...]] = {
    "000905": ("中证500", "中证 500", "CSI 500", "CSI500"),
    "000300": ("沪深300", "沪深 300", "CSI 300", "CSI300"),
    "000852": ("中证1000", "中证 1000", "CSI 1000", "CSI1000"),
    "000016": ("上证50", "上证 50"),
}

# These codes collide with A-share stocks under the digit-prefix rule; external
# quote APIs still expect the **Shanghai index** secid (sh000905 etc.).
KNOWN_SH_INDEX_CODES: frozenset[str] = frozenset(KNOWN_INDEX_NAME_HINTS)

ENV_BENCHMARK_SYMBOL = "STOCK_PLATFORM_BENCHMARK_SYMBOL"
DEFAULT_BENCHMARK_SYMBOL = "000905"


def bare_benchmark_code(raw: str | None) -> str:
    """``'000905.SH'`` / ``'sh000905'`` / ``'000905'`` → ``'000905'``."""
    s = str(raw or "").strip().upper()
    if not s:
        return DEFAULT_BENCHMARK_SYMBOL
    for prefix in ("SH", "SZ", "BJ"):
        if s.startswith(prefix) and len(s) > len(prefix) and s[len(prefix) :].isdigit():
            s = s[len(prefix) :]
            break
    if "." in s:
        s = s.split(".", 1)[0]
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 6:
        return digits[-6:]
    return digits.zfill(6) if digits else DEFAULT_BENCHMARK_SYMBOL


def resolve_benchmark_symbol() -> str:
    """Bare default / env override (unchanged call shape for settle / digest)."""
    raw = str(os.environ.get(ENV_BENCHMARK_SYMBOL) or "").strip()
    return bare_benchmark_code(raw) if raw else DEFAULT_BENCHMARK_SYMBOL


def engine_benchmark_code(symbol: str | None = None) -> str:
    """Code form used to read ``daily_price`` in the engine warehouse.

    Prefers ``XXXXXX.<EX>`` where ``EX`` comes from :func:`exchange_prefix`
    (so Shanghai funds/indexes are ``.SH``, not the historical blind ``.SZ``).
    """
    bare = bare_benchmark_code(symbol or resolve_benchmark_symbol())
    try:
        ex = exchange_prefix(bare).upper()
    except Exception:  # noqa: BLE001
        ex = "SZ"
    return f"{bare}.{ex}"


def quote_benchmark_key(symbol: str | None = None) -> str:
    """External quote key ``sh000905`` / ``sz159915`` for snapshot / westock.

    Known CSI-style indexes force ``sh`` even when :func:`exchange_prefix`
    would return ``sz`` for the colliding stock code.
    """
    bare = bare_benchmark_code(symbol or resolve_benchmark_symbol())
    if bare in KNOWN_SH_INDEX_CODES:
        return f"sh{bare}"
    try:
        return f"{exchange_prefix(bare)}{bare}"
    except Exception:  # noqa: BLE001
        return f"sz{bare}"


def _name_matches_index(bare: str, name: str | None) -> bool:
    if not name:
        return False
    hints = KNOWN_INDEX_NAME_HINTS.get(bare)
    if not hints:
        # Unknown code: do not claim index identity; caller treats as unchecked.
        return False
    text = str(name)
    return any(h in text for h in hints)


def resolve_benchmark_identity(
    symbol: str | None = None,
    *,
    name: str | None = None,
    names: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return identity block for reports / alpha gating.

    ``ok`` is True only when the code is in :data:`KNOWN_INDEX_NAME_HINTS` **and**
    the fundamentals name matches an expected index label. Stock collision →
    ``ok=False`` and a Chinese ``warning`` (alpha must be marked unavailable).
    """
    bare = bare_benchmark_code(symbol or resolve_benchmark_symbol())
    resolved_name = name
    if resolved_name is None and names is not None:
        resolved_name = names.get(bare)
    hints = KNOWN_INDEX_NAME_HINTS.get(bare)
    if bare in KNOWN_SH_INDEX_CODES:
        prefix = "sh"
    else:
        try:
            prefix = exchange_prefix(bare)
        except Exception:  # noqa: BLE001
            prefix = "sz"

    if hints is None:
        return {
            "symbol": bare,
            "engineCode": engine_benchmark_code(bare),
            "quoteKey": quote_benchmark_key(bare),
            "exchangePrefix": prefix,
            "name": resolved_name,
            "expectedHints": None,
            "ok": True,
            "checked": False,
            "warning": None,
            "alphaAvailable": True,
        }

    matched = _name_matches_index(bare, resolved_name)
    if matched:
        return {
            "symbol": bare,
            "engineCode": engine_benchmark_code(bare),
            "quoteKey": quote_benchmark_key(bare),
            "exchangePrefix": prefix,
            "name": resolved_name,
            "expectedHints": list(hints),
            "ok": True,
            "checked": True,
            "warning": None,
            "alphaAvailable": True,
        }

    shown = resolved_name or "（无名称）"
    warning = (
        f"平台基准 `{bare}` 在引擎 fundamentals 中解析为 **{shown}**，"
        f"未匹配指数别名 {list(hints)}；疑似个股/错误序列。"
        "相对基准超额（alpha）标为不可用，不编造指数超额。"
    )
    return {
        "symbol": bare,
        "engineCode": engine_benchmark_code(bare),
        "quoteKey": quote_benchmark_key(bare),
        "exchangePrefix": prefix,
        "name": resolved_name,
        "expectedHints": list(hints),
        "ok": False,
        "checked": True,
        "warning": warning,
        "alphaAvailable": False,
    }


__all__ = [
    "DEFAULT_BENCHMARK_SYMBOL",
    "ENV_BENCHMARK_SYMBOL",
    "KNOWN_INDEX_NAME_HINTS",
    "KNOWN_SH_INDEX_CODES",
    "bare_benchmark_code",
    "engine_benchmark_code",
    "quote_benchmark_key",
    "resolve_benchmark_identity",
    "resolve_benchmark_symbol",
]
