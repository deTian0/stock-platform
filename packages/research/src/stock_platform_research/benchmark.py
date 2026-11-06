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

# Extra aliases used **only** by the aux-market store (ADR 0095) for indexes that
# do not collide with stock codes. Not part of the F1 identity table above.
AUX_EXTRA_INDEX_NAME_HINTS: dict[str, tuple[str, ...]] = {
    "399006": ("创业板指", "创业板指数", "ChiNext"),
}


def aux_index_name_hints() -> dict[str, tuple[str, ...]]:
    """Alias table the aux store verifies East Money index names against."""
    return {**KNOWN_INDEX_NAME_HINTS, **AUX_EXTRA_INDEX_NAME_HINTS}


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


def _market_db_closes(db: str, start: str, end: str, code: str) -> dict[str, float]:
    """Read-only closes from engine ``daily_price``; empty when absent."""
    import sqlite3

    uri = "file:%s?mode=ro" % str(db).replace("\\", "/")
    con = sqlite3.connect(uri, uri=True)
    try:
        rows = con.execute(
            "SELECT date, close FROM daily_price WHERE code=? AND date>=? AND date<=?",
            (code, start, end),
        ).fetchall()
    finally:
        con.close()
    return {str(d)[:10]: float(c) for d, c in rows if c is not None}


def _aux_index_closes(bare: str, start: str, end: str) -> tuple[dict[str, float] | None, str | None]:
    """Verified index closes from the aux store (ADR 0095); ``(None, None)`` if absent."""
    try:
        from stock_platform_providers.aux_market import read_index_closes, read_index_meta
    except Exception:  # noqa: BLE001
        return None, None
    meta = read_index_meta(bare)
    if not meta:
        return None, None
    hints = aux_index_name_hints().get(bare) or ()
    name = str(meta.get("name") or "")
    if not name or not any(h in name for h in hints):
        return None, None
    closes = read_index_closes(bare, start, end)
    if not closes:
        return None, None
    return closes, name


def load_benchmark_closes(
    db: str,
    start: str,
    end: str,
    *,
    names: Mapping[str, str] | None = None,
    symbol: str | None = None,
) -> tuple[dict[str, float] | None, dict[str, Any]]:
    """Benchmark ``date → close`` for offline backtests (F1 + ADR 0095).

    1. Identity check (fail-closed) → read-only ``market.db`` engine-code rows.
    2. Only when that yields nothing (stock collision or no rows), fall back to
       the platform aux store's **verified** index rows.
    3. No aux store / no aux rows → bit-identical to the pre-aux behaviour.
    """
    bench = bare_benchmark_code(symbol) if symbol else resolve_benchmark_symbol()
    ident = resolve_benchmark_identity(bench, names=names or {})
    block: dict[str, Any] = {
        "symbol": ident.get("symbol"),
        "engineCode": ident.get("engineCode"),
        "name": ident.get("name"),
        "identityChecked": bool(ident.get("checked")),
        "identityOk": bool(ident.get("ok")),
    }
    if not ident.get("alphaAvailable", True):
        reason = str(ident.get("warning") or "基准身份校验未通过")
    else:
        closes = _market_db_closes(db, start, end, str(ident.get("engineCode")))
        if closes:
            return closes, block
        reason = f"market.db daily_price 无 `{ident.get('engineCode')}` 行（{start}~{end}）"

    aux, aux_name = _aux_index_closes(str(ident.get("symbol")), start, end)
    if aux:
        block.update(
            source="aux_market",
            identityOk=True,
            auxName=aux_name,
            marketDbReason=reason,
        )
        return aux, block
    block["reason"] = reason
    return None, block


__all__ = [
    "AUX_EXTRA_INDEX_NAME_HINTS",
    "aux_index_name_hints",
    "load_benchmark_closes",
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
