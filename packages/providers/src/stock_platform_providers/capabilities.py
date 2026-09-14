"""Capability registry and routing matrix — single authority for dataset routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

# Order: TSP original seven first, then platform extensions (M15+).
CAPABILITY_REGISTRY: list[dict[str, str]] = [
    {"id": "daily", "label": "日K", "desc": "历史K线与实时覆写"},
    {"id": "adj_factor", "label": "除权因子", "desc": "前复权计算基准"},
    {"id": "realtime", "label": "实时行情", "desc": "全市场实时快照"},
    {"id": "minute", "label": "分钟K", "desc": "分时图与分钟回测"},
    {"id": "depth5", "label": "五档盘口", "desc": "连板梯队封单与盘口深度"},
    {"id": "financial", "label": "财务数据", "desc": "财务指标与三大报表"},
    {"id": "full_minute", "label": "全量分钟", "desc": "盘中全市场当日分钟落盘"},
    {"id": "fund_flow", "label": "日级资金流", "desc": "个股主力/大小单日级净流入（元）"},
]

CAPABILITY_IDS: tuple[str, ...] = tuple(item["id"] for item in CAPABILITY_REGISTRY)


@dataclass(frozen=True)
class ProviderDeclaration:
    name: str
    display: str
    kind: str  # builtin | plugin | custom
    datasets: frozenset[str]
    available: bool = True
    status: str = "ok"
    note: str | None = None
    pending_reason: str | None = None


@dataclass
class ProviderRegistry:
    """In-process provider declarations for capability matrix builds."""

    _items: dict[str, ProviderDeclaration] = field(default_factory=dict)

    def register(self, declaration: ProviderDeclaration) -> None:
        unknown = set(declaration.datasets) - set(CAPABILITY_IDS)
        if unknown:
            raise ValueError(f"unknown datasets in {declaration.name}: {sorted(unknown)}")
        self._items[declaration.name] = declaration

    def unregister(self, name: str) -> None:
        self._items.pop(name, None)

    def clear(self) -> None:
        self._items.clear()

    def list(self) -> list[ProviderDeclaration]:
        return list(self._items.values())


_registry = ProviderRegistry()


def get_provider_registry() -> ProviderRegistry:
    return _registry


def reset_provider_registry() -> ProviderRegistry:
    _registry.clear()
    return _registry


def register_builtin_providers(registry: ProviderRegistry | None = None) -> None:
    """Register package-built-in declarations (replay today; http later)."""
    reg = registry or _registry
    reg.register(
        ProviderDeclaration(
            name="replay",
            display="Replay fixtures",
            kind="builtin",
            datasets=frozenset({"daily", "realtime", "fund_flow"}),
            available=True,
            status="ok",
            note="Offline recorded fixtures only",
        )
    )
    reg.register(
        ProviderDeclaration(
            name="astock_http",
            display="A-stock HTTP (EM throttled)",
            kind="builtin",
            datasets=frozenset({"daily", "realtime", "fund_flow"}),
            available=True,
            status="ok",
            note="Live East Money via em_get; prefer replay for offline CI",
        )
    )
    reg.register(
        ProviderDeclaration(
            name="global_replay",
            display="Global US/HK replay fixtures",
            kind="builtin",
            datasets=frozenset({"daily", "realtime"}),
            available=True,
            status="ok",
            note="Offline US/HK fixtures; no CN T+1/limit assumptions",
        )
    )
    reg.register(
        ProviderDeclaration(
            name="global_http",
            display="Global HTTP (Yahoo + Sina)",
            kind="builtin",
            datasets=frozenset({"daily", "realtime"}),
            available=True,
            status="ok",
            note="Live US/HK via Yahoo chart + Sina quotes; prefer global_replay for offline CI",
        )
    )


def build_capability_matrix(
    preferences: dict[str, str] | None = None,
    providers: Iterable[ProviderDeclaration] | None = None,
) -> list[dict[str, Any]]:
    """Build CapabilityStatus rows per docs/contracts/capability-matrix.md.

    ``preferences`` maps capability id → preferred provider ``name``.
    Missing preference falls back to first usable candidate, else null.
    """
    prefs = preferences or {}
    decls = list(providers) if providers is not None else _registry.list()
    rows: list[dict[str, Any]] = []

    for meta in CAPABILITY_REGISTRY:
        cap_id = meta["id"]
        preferred = prefs.get(cap_id, "")
        candidates: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []

        for decl in decls:
            if cap_id not in decl.datasets:
                continue
            if decl.available:
                candidates.append(
                    {
                        "name": decl.name,
                        "display": decl.display,
                        "kind": decl.kind,
                        "available": True,
                        "status": decl.status,
                        "note": decl.note,
                    }
                )
            else:
                pending.append(
                    {
                        "name": decl.name,
                        "display": decl.display,
                        "reason": decl.pending_reason or decl.status,
                    }
                )

        effective: str | None = None
        if preferred and any(c["name"] == preferred for c in candidates):
            effective = preferred
        elif candidates:
            effective = candidates[0]["name"]

        usable = effective is not None and any(
            c["name"] == effective and c["available"] for c in candidates
        )

        rows.append(
            {
                "id": cap_id,
                "label": meta["label"],
                "desc": meta["desc"],
                "preferred": preferred or (effective or ""),
                "effective": effective,
                "usable": usable,
                "candidates": candidates,
                "pending": pending,
            }
        )
    return rows
