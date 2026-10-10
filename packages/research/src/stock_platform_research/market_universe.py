"""Market-wide universe resolution — **single definition** (milestone ``X1``).

Before ``X1`` the daily universe came from a small JSON fixture (``core`` /
``watch`` / ``full`` tiers, a few hundred symbols). ``X1`` widens it to the whole
market carried by the engine ``market.db`` (~5.3k tradable codes, BSE excluded).

Split of responsibilities (so no rule is defined twice)
-------------------------------------------------------
- **how the warehouse becomes a symbol list** — window, min-bars, BSE exclusion,
  6-digit normalisation → :meth:`stock_platform_providers.engine_sqlite.
  EngineSqliteProvider.list_symbols`
- **what the research side does on top** — asset-class filtering (reusing
  :func:`portfolio.asset_class`, milestone ``B4``), ordering, ``limit``, and
  fail-closed emptiness → :func:`resolve_market_universe` here

Callers never talk to SQLite directly and never re-implement a prefix table:
:func:`resolve_universe` is the one entry point for both ``config`` and
``market_db`` sources.

Fail-closed
-----------
An empty resolution **raises** :class:`universe.UniverseEmptyError` — an empty
market silently degrading into "no picks" is exactly the failure mode ``X1``
must not have (see ``docs/contracts/market-universe.md``).
"""

from __future__ import annotations

import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping, Protocol, Sequence

from .portfolio import asset_class
from .universe import (
    UNIVERSE_SOURCES,
    UniverseEmptyError,
    load_universe,
    normalize_universe,
)

ASSET_TYPE_CHOICES = ("stock", "etf", "fund", "all")

# Keep in sync with providers.engine_sqlite.DEFAULT_UNIVERSE_LOOKBACK_DAYS.
DEFAULT_MARKET_LOOKBACK_DAYS = 120
DEFAULT_MARKET_MIN_BARS = 1

MSG_SOURCE_MISSING = (
    "market_db 宇宙需要注入行情源：请传入实现 list_symbols(...) 的对象"
    "（如 EngineSqliteProvider），禁止静默回退到样例宇宙冒充全市场。"
)
MSG_EMPTY = (
    "全市场宇宙解析结果为空（source={source}, asset_type={asset_type}, "
    "min_bars={min_bars}, lookback_days={lookback_days}, counts={counts}）："
    "请检查 market.db 覆盖窗口或放宽 min_bars；禁止空宇宙静默继续。"
)


class MarketSymbolSource(Protocol):
    """Anything that can enumerate market symbols (provider side)."""

    def list_symbols(
        self,
        *,
        asof: date | str | None = None,
        lookback_days: int = DEFAULT_MARKET_LOOKBACK_DAYS,
        min_bars: int = DEFAULT_MARKET_MIN_BARS,
        include_bse: bool = False,
        limit: int | None = None,
    ) -> Sequence[str]: ...


@dataclass(frozen=True)
class MarketUniverse:
    """Resolution result + provenance + cost (all numbers measured, not guessed)."""

    symbols: tuple[str, ...] = ()
    source: str = "market_db"
    asof: str | None = None
    lookback_days: int = DEFAULT_MARKET_LOOKBACK_DAYS
    min_bars: int = DEFAULT_MARKET_MIN_BARS
    include_bse: bool = False
    asset_type: str = "stock"
    limit: int | None = None
    counts: Mapping[str, int] = field(default_factory=dict)
    elapsed_s: float = 0.0
    peak_memory_mb: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "asof": self.asof,
            "lookback_days": self.lookback_days,
            "min_bars": self.min_bars,
            "include_bse": self.include_bse,
            "asset_type": self.asset_type,
            "limit": self.limit,
            "symbol_count": len(self.symbols),
            "symbols": list(self.symbols),
            "counts": dict(self.counts),
            "elapsed_s": round(self.elapsed_s, 4),
            "peak_memory_mb": self.peak_memory_mb,
        }


def _asof_str(asof: date | str | None) -> str | None:
    if asof is None or asof == "":
        return None
    if isinstance(asof, date):
        return asof.isoformat()
    return str(asof)[:10]


def resolve_market_universe(
    source: MarketSymbolSource | Any,
    *,
    asof: date | str | None = None,
    lookback_days: int = DEFAULT_MARKET_LOOKBACK_DAYS,
    min_bars: int = DEFAULT_MARKET_MIN_BARS,
    include_bse: bool = False,
    asset_type: str = "stock",
    limit: int | None = None,
    measure_memory: bool = False,
) -> MarketUniverse:
    """Resolve the market-wide universe from an injected symbol source.

    ``source`` must expose ``list_symbols(...)`` (protocol
    :class:`MarketSymbolSource`); the DB query itself stays in the providers
    package. Asset filtering reuses :func:`portfolio.asset_class` so ``X1``
    cannot drift away from the ``B4`` stamp-duty / classification tables.

    ``measure_memory=True`` wraps the call in :mod:`tracemalloc` and reports
    ``peak_memory_mb`` (used by the benchmark CLI; off by default because it
    slows the query down).

    Empty → :class:`UniverseEmptyError` with the filter counts attached.
    """
    if source is None or not hasattr(source, "list_symbols"):
        raise UniverseEmptyError(MSG_SOURCE_MISSING)

    key = str(asset_type or "stock").strip().lower()
    if key not in ASSET_TYPE_CHOICES:
        raise UniverseEmptyError(
            f"unknown asset_type {asset_type!r}; expected one of {ASSET_TYPE_CHOICES}"
        )

    if measure_memory:
        tracemalloc.start()
    started = time.perf_counter()
    try:
        raw = list(
            source.list_symbols(
                asof=asof,
                lookback_days=int(lookback_days),
                min_bars=int(min_bars),
                include_bse=bool(include_bse),
            )
        )
    finally:
        elapsed = time.perf_counter() - started
    peak_mb: float | None = None
    if measure_memory:
        peak_bytes = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        peak_mb = round(peak_bytes / (1024 * 1024), 3)

    normalized = normalize_universe(raw)
    if key == "all":
        kept = list(normalized)
    else:
        kept = [c for c in normalized if asset_class(c) == key]
    counts = {
        "source": len(raw),
        "normalized": len(normalized),
        "asset_matched": len(kept),
    }
    if limit is not None:
        kept = kept[: max(0, int(limit))]
    counts["final"] = len(kept)

    if not kept:
        raise UniverseEmptyError(
            MSG_EMPTY.format(
                source="market_db",
                asset_type=key,
                min_bars=min_bars,
                lookback_days=lookback_days,
                counts=counts,
            )
        )

    return MarketUniverse(
        symbols=tuple(kept),
        source="market_db",
        asof=_asof_str(asof),
        lookback_days=int(lookback_days),
        min_bars=int(min_bars),
        include_bse=bool(include_bse),
        asset_type=key,
        limit=None if limit is None else int(limit),
        counts=counts,
        elapsed_s=elapsed,
        peak_memory_mb=peak_mb,
    )


def resolve_universe(
    *,
    source: str = "config",
    symbols: Sequence[Any] | None = None,
    path: Any = None,
    tier: str | None = None,
    market_symbol_source: MarketSymbolSource | Any = None,
    **market_kwargs: Any,
) -> list[str]:
    """One entry point for both universe sources (``X1``).

    Precedence: explicit ``symbols`` > ``market_db`` > config file.

    ``source`` must be one of :data:`universe.UNIVERSE_SOURCES`. Unknown source
    and empty results both fail closed — no silent fallback to the tiny sample
    fixture, which would look like a healthy run over a handful of symbols.
    """
    key = str(source or "config").strip().lower()
    if key not in UNIVERSE_SOURCES:
        raise UniverseEmptyError(
            f"unknown universe source {source!r}; expected one of {UNIVERSE_SOURCES}"
        )

    if symbols is not None:
        out = normalize_universe(symbols)
        if not out:
            raise UniverseEmptyError("symbols list is empty after normalize")
        return out

    if key == "market_db":
        universe = resolve_market_universe(market_symbol_source, **market_kwargs)
        return list(universe.symbols)

    return load_universe(path, tier=tier)
