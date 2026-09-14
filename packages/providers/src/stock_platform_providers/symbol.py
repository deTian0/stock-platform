"""A-share / US / HK symbol normalization.

CN path aligns with TradingAgents `_normalize_ticker` and a-stock-data BSE rules.
US / HK are separate markets — never routed through CN digit-only rules.
"""

from __future__ import annotations

import re

from .errors import SymbolError

_PATH_SAFE = re.compile(r"^[A-Za-z0-9._\-\^]+$")
_US_TICKER = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


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


def _normalize_cn(symbol: str) -> str:
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
                    "(e.g. 600519). Pass market='HK' for Hong Kong."
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
            "CN providers only accept 6-digit A-share codes. Pass market='HK'."
        )
    if s and not s.isdigit():
        raise SymbolError(
            f"{original!r} is not an A-share code. "
            "CN providers only accept 6-digit numeric codes (e.g. 600519). "
            "Pass market='US' for US tickers."
        )
    raise SymbolError(
        f"{original!r} is not a valid A-share code (need exactly 6 digits, got {s!r})."
    )


def _normalize_hk(symbol: str) -> str:
    original = symbol.strip()
    if not original:
        raise SymbolError("HK ticker must be a non-empty string")
    if re.search(r"[\u4e00-\u9fff]", original):
        raise SymbolError(f"{original!r}: HK path does not resolve Chinese names")

    s = original.upper().replace(" ", "")
    if s.startswith("HK") and len(s) > 2 and s[2:].replace(".", "").isdigit():
        s = s[2:]
    if s.endswith(".HK"):
        s = s[:-3]
    if s.startswith("0") and s[1:].isdigit() and len(s) > 5:
        # keep as-is until length check
        pass
    if not s.isdigit() or len(s) > 5:
        raise SymbolError(
            f"{original!r} is not a Hong Kong numeric ticker "
            "(expect 1–5 digits or *.HK, e.g. 00700 / 0700.HK)."
        )
    return s.zfill(5)


def _normalize_us(symbol: str) -> str:
    original = symbol.strip()
    if not original:
        raise SymbolError("US ticker must be a non-empty string")
    if re.search(r"[\u4e00-\u9fff]", original):
        raise SymbolError(f"{original!r}: US path does not resolve Chinese names")

    s = original.upper().replace(" ", "")
    for suffix in (".US", ".NYSE", ".NASDAQ"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    # Yahoo-style class shares: BRK-B → BRK.B
    s = s.replace("-", ".")
    if s.isdigit():
        raise SymbolError(
            f"{original!r} looks numeric; US path expects letter tickers (e.g. AAPL). "
            "Use market='HK' for Hong Kong codes."
        )
    if not _US_TICKER.fullmatch(s):
        raise SymbolError(
            f"{original!r} is not a valid US ticker after parse ({s!r})."
        )
    return s


def normalize_symbol(symbol: str, *, market: str = "CN") -> str:
    """Normalize a ticker for the given ``market`` (``CN`` / ``US`` / ``HK``).

    CN returns a 6-digit A-share code and **rejects** HK / US forms.
    HK returns a zero-padded 5-digit code (``00700``).
    US returns an uppercase letter ticker (``AAPL``, ``BRK.B``).
    """
    if not isinstance(symbol, str) or not symbol.strip():
        raise SymbolError(f"ticker must be a non-empty string, got {symbol!r}")

    m = str(market).strip().upper()
    if m == "CN":
        return _normalize_cn(symbol)
    if m == "HK":
        return _normalize_hk(symbol)
    if m == "US":
        return _normalize_us(symbol)
    raise SymbolError(f"market={market!r} is not supported; expected CN, US, or HK.")


_SECTOR_CODE = re.compile(r"^BK\d{4,6}$")


def normalize_sector_code(code: str) -> str:
    """Normalize an East Money board / sector code (e.g. ``BK0477``).

    Accepts ``BK0477``, ``bk0477``, or ``90.BK0477`` (EM secid form).
    """
    if not isinstance(code, str) or not code.strip():
        raise SymbolError(f"sector code must be a non-empty string, got {code!r}")
    original = code.strip()
    s = original.upper().replace(" ", "")
    if s.startswith("90."):
        s = s[3:]
    if not _SECTOR_CODE.fullmatch(s):
        raise SymbolError(
            f"{original!r} is not a valid EM board/sector code "
            "(expect BK####, e.g. BK0477)."
        )
    return s
