"""stock-platform providers — unified Vendor surface (A-share first)."""

from .errors import SymbolError
from .symbol import (
    exchange_prefix,
    is_bse_symbol,
    normalize_symbol,
)

__all__ = [
    "SymbolError",
    "exchange_prefix",
    "is_bse_symbol",
    "normalize_symbol",
]

__version__ = "0.1.1"
