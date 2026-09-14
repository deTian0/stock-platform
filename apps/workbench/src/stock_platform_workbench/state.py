"""Application state and capability-aware provider resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from stock_platform_providers import (
    AStockHttpProvider,
    GlobalHttpRouter,
    ProviderDeclaration,
    ReplayProvider,
    ReplayTransport,
    build_capability_matrix,
    register_builtin_providers,
    reset_provider_registry,
)
from stock_platform_providers.base import MarketDataProvider
from stock_platform_execution import PaperLedger, StrategyLifecycle


class CapabilityUnavailable(Exception):
    """Raised when the capability matrix says the requested dataset is not usable."""

    def __init__(self, capability: str, detail: dict[str, Any]) -> None:
        self.capability = capability
        self.detail = detail
        super().__init__(f"capability {capability!r} is not usable")


@dataclass
class PaperRuntime:
    ledger: PaperLedger = field(default_factory=PaperLedger)
    lifecycle: StrategyLifecycle = field(default_factory=StrategyLifecycle)


@dataclass
class WorkbenchState:
    """Runtime wiring: preferences + concrete provider instances (by name)."""

    fixtures_dir: Path
    preferences: dict[str, str] = field(default_factory=dict)
    providers: dict[str, MarketDataProvider] = field(default_factory=dict)
    declarations: list[ProviderDeclaration] = field(default_factory=list)
    paper: PaperRuntime = field(default_factory=PaperRuntime)

    def matrix(self) -> list[dict[str, Any]]:
        return build_capability_matrix(self.preferences, self.declarations)

    def resolve(self, capability: str) -> MarketDataProvider:
        rows = {row["id"]: row for row in self.matrix()}
        if capability not in rows:
            raise CapabilityUnavailable(
                capability,
                {"capability": capability, "usable": False, "reason": "unknown_capability"},
            )
        row = rows[capability]
        if not row["usable"] or not row["effective"]:
            raise CapabilityUnavailable(
                capability,
                {
                    "capability": capability,
                    "usable": False,
                    "preferred": row.get("preferred"),
                    "effective": row.get("effective"),
                    "candidates": row.get("candidates"),
                    "pending": row.get("pending"),
                    "reason": "capability_not_usable",
                },
            )
        name = row["effective"]
        provider = self.providers.get(name)
        if provider is None:
            raise CapabilityUnavailable(
                capability,
                {
                    "capability": capability,
                    "usable": False,
                    "effective": name,
                    "reason": "provider_instance_missing",
                },
            )
        return provider


def build_default_state(fixtures_dir: Path, preferences: dict[str, str] | None = None) -> WorkbenchState:
    """Wire replay provider + builtin declarations (no brand hardcoding in routes)."""
    reg = reset_provider_registry()
    register_builtin_providers(reg)
    prefs = {
        "daily": "replay",
        "realtime": "replay",
        "minute": "replay",
        "depth5": "replay",
        "financial": "replay",
        "fund_flow": "replay",
        "lhb": "replay",
        "unlock": "replay",
        **(preferences or {}),
    }
    transport = ReplayTransport(fixtures_dir)
    replay = ReplayProvider(transport)
    providers: dict[str, MarketDataProvider] = {"replay": replay}
    # Live adapters are always constructible; network only happens on call.
    providers["astock_http"] = AStockHttpProvider()
    providers["global_http"] = GlobalHttpRouter()
    return WorkbenchState(
        fixtures_dir=fixtures_dir,
        preferences=prefs,
        providers=providers,
        declarations=reg.list(),
    )
