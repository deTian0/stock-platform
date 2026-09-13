"""A-share symbol normalization.

Aligns with TradingAgents `_normalize_ticker` / `_get_prefix` and
a-stock-data BSE segment rules. Chinese-name resolution is intentionally
out of scope for M1.1 (no mootdx dependency yet).
"""

from __future__ import annotations

import re

from .errors import SymbolError

_PATH_SAFE = re.compile(r"^[A-Za-z0-9._\-\^]+$")


def is_bse_symbol(code: str) -> bool:
    """True when a 6-digit code belongs to the Beijing Stock Exchange segment."""
    return code.startswith(("4", "8", "92"))


def exchange_prefix(code: str) -> str:
    """Map a normalized 6-digit A-share code to ``sh`` / ``sz`` / ``bj``.

    ``92`` must be checked before the leading-``9`` Shanghai B-share rule,
    otherwise BSE ``920xxx`` is misrouted to Shanghai.
    """
    if not (isinstance(code, str) and code.isdigit() and len(code) == 6):
        raise SymbolError(f"exchange_prefix expects a 6-digit code, got {code!r}")
    if code.startswith("92") or code.startswith(("4", "8")):
        return "bj"
    if code.startswith(("6", "9")):
        return "sh"
    return "sz"


def normalize_symbol(symbol: str, *, market: str = "CN") -> str:
    """Return a pure 6-digit A-share code.

    Accepts forms such as ``600519``, ``SH600519``, ``600519.SH``, ``sz000001``.
    Rejects HK (4–5 digit / ``.HK``) and US-style tickers on the CN path.

    Parameters
    ----------
    symbol:
        Raw ticker from user / LLM / vendor.
    market:
        Only ``CN`` is implemented. Other markets raise ``SymbolError`` until M5.
    """
    if market != "CN":
        raise SymbolError(
            f"market={market!r} is not supported yet; only CN is available until M5."
        )
    if not isinstance(symbol, str) or not symbol.strip():
        raise SymbolError(f"ticker must be a non-empty string, got {symbol!r}")

    original = symbol.strip()
    if re.search(r"[\u4e00-\u9fff]", original):
        raise SymbolError(
            f"{original!r} looks like a Chinese name. "
            "Name→code resolution is not in M1.1; pass a 6-digit A-share code."
        )

    s = original.upper()
    for suffix in (".SH", ".SZ", ".BJ", ".SS", ".HK"):
        if s.endswith(suffix):
            if suffix == ".HK":
                raise SymbolError(
                    f"{original!r} is a Hong Kong ticker. "
                    "CN providers only accept 6-digit A-share codes "
                    "(e.g. 600519). Use global providers at M5."
                )
            s = s[: -len(suffix)]
            break
    for prefix in ("SH", "SZ", "BJ"):
        if s.startswith(prefix) and len(s) > len(prefix):
            s = s[len(prefix) :]
            break

    if len(s) > 32 or not _PATH_SAFE.fullmatch(s) or set(s) == {"."}:
        raise SymbolError(
            f"{original!r} is not a safe/valid ticker component after parse ({s!r})."
        )

    if s.isdigit() and len(s) == 6:
        return s

    if s.isdigit() and len(s) in (4, 5):
        raise SymbolError(
            f"{original!r} looks like a Hong Kong numeric code. "
            "CN providers only accept 6-digit A-share codes."
        )
    if s and not s.isdigit():
        raise SymbolError(
            f"{original!r} is not an A-share code. "
            "CN providers only accept 6-digit numeric codes (e.g. 600519)."
        )
    raise SymbolError(
        f"{original!r} is not a valid A-share code (need exactly 6 digits, got {s!r})."
    )
