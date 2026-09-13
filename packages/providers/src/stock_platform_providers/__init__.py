"""stock-platform providers — unified Vendor surface (A-share first)."""

from .capabilities import (
    CAPABILITY_IDS,
    CAPABILITY_REGISTRY,
    ProviderDeclaration,
    build_capability_matrix,
    get_provider_registry,
    register_builtin_providers,
    reset_provider_registry,
)
from .eastmoney import EastmoneyClient, em_get, is_eastmoney_url, reset_default_client
from .errors import SymbolError
from .replay import ReplayProvider, ReplayTransport
from .symbol import (
    exchange_prefix,
    is_bse_symbol,
    normalize_symbol,
)

__all__ = [
    "CAPABILITY_IDS",
    "CAPABILITY_REGISTRY",
    "EastmoneyClient",
    "ProviderDeclaration",
    "ReplayProvider",
    "ReplayTransport",
    "SymbolError",
    "build_capability_matrix",
    "em_get",
    "exchange_prefix",
    "get_provider_registry",
    "is_bse_symbol",
    "is_eastmoney_url",
    "normalize_symbol",
    "register_builtin_providers",
    "reset_default_client",
    "reset_provider_registry",
]

__version__ = "0.2.2"
