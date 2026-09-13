"""stock-platform providers — unified Vendor surface (A-share first)."""

from .errors import SymbolError
from .replay import ReplayProvider, ReplayTransport
from .symbol import (
    exchange_prefix,
    is_bse_symbol,
    normalize_symbol,
)

__all__ = [
    "ReplayProvider",
    "ReplayTransport",
    "SymbolError",
    "exchange_prefix",
    "is_bse_symbol",
    "normalize_symbol",
]

__version__ = "0.1.2"
