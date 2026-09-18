"""Application state and capability-aware provider resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from stock_platform_providers import (
    AStockHttpProvider,
    EngineSqliteProvider,
    GlobalHttpRouter,
    ProviderDeclaration,
    ReplayProvider,
    ReplayTransport,
    TushareHttpProvider,
    build_capability_matrix,
    register_builtin_providers,
    reset_provider_registry,
    resolve_engine_market_db,
    startup_preferences,
)
from stock_platform_providers.base import MarketDataProvider
from stock_platform_execution import (
    BrokerPort,
    GatedBroker,
    PaperLedger,
    StrategyLifecycle,
    resolve_broker,
)


class CapabilityUnavailable(Exception):
    """Raised when the capability matrix says the requested dataset is not usable."""

    def __init__(self, capability: str, detail: dict[str, Any]) -> None:
        self.capability = capability
        self.detail = detail
        super().__init__(f"capability {capability!r} is not usable")


@dataclass
class PaperRuntime:
    broker: BrokerPort = field(default_factory=lambda: resolve_broker())
    lifecycle: StrategyLifecycle = field(default_factory=StrategyLifecycle)

    def __post_init__(self) -> None:
        # External sim always goes through admission wrapper (still SIMULATE).
        if getattr(self.broker, "name", "") == "ths_sim" and not isinstance(
            self.broker, GatedBroker
        ):
            self.broker = GatedBroker(self.broker, require_active_hash=False)

    @property
    def ledger(self) -> PaperLedger:
        inner = self.broker.inner if isinstance(self.broker, GatedBroker) else self.broker
        ledger = getattr(inner, "ledger", None)
        if isinstance(ledger, PaperLedger):
            return ledger
        raise TypeError("active broker does not expose a PaperLedger")



@dataclass
class WorkbenchState:
    """Runtime wiring: preferences + concrete provider instances (by name)."""

    fixtures_dir: Path
    preferences: dict[str, str] = field(default_factory=dict)
    providers: dict[str, MarketDataProvider] = field(default_factory=dict)
    declarations: list[ProviderDeclaration] = field(default_factory=list)
    paper: PaperRuntime = field(default_factory=PaperRuntime)
    # Optional U2 brief archive override (tests inject temp SqliteBriefRepository).
    brief_repo: Any | None = None

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
    """Wire providers + capability preferences (production default: CN live).

    Pass ``preferences`` explicitly (or set ``STOCK_PLATFORM_PROVIDER_PRESET=replay``)
    for offline CI. Trading remains SIMULATE regardless of market-data prefs.
    """
    reg = reset_provider_registry()
    register_builtin_providers(reg)
    prefs = startup_preferences(preferences)
    transport = ReplayTransport(fixtures_dir)
    replay = ReplayProvider(transport)
    providers: dict[str, MarketDataProvider] = {"replay": replay}
    # Live adapters are always constructible; network only happens on call.
    providers["astock_http"] = AStockHttpProvider()
    providers["global_http"] = GlobalHttpRouter()
    providers["tushare_http"] = TushareHttpProvider()
    engine_db = resolve_engine_market_db()
    if engine_db is not None:
        providers["engine_sqlite"] = EngineSqliteProvider(engine_db)
    return WorkbenchState(
        fixtures_dir=fixtures_dir,
        preferences=prefs,
        providers=providers,
        declarations=reg.list(),
    )
