"""Bulk ``market.db``-backed provider for the daily refresh job.

Context (why this exists)
-------------------------
``research.refresh.run_refresh`` fetches each dataset **per symbol** through the
injected provider. With a *live* provider (tushare/EM) that is one HTTP call per
``(symbol, dataset)`` pair: a measured run took **11m48s for 614 files** and
extrapolated to **≈3 hours** for the whole ~5.2k-code market — impossible for an
08:30 pre-market job. Meanwhile the local ``a-stock-engine`` warehouse already
carries the same history: a whole-market 120-day read is **3.2s** (422k rows).

This provider is the offline bulk source. One SQL round-trip serves *all*
symbols for a dataset, and :class:`stock_platform_research.refresh.run_refresh`
consumes it in a single pass. That is the difference between 3 hours and a few
seconds on the hot path, and it never touches the public net.

Scope and honest limits
-----------------------
- ``daily`` — served from ``daily_price`` (close/vol/amount/pct_chg). This is the
  only series the warehouse actually stores.
- ``adj_factor`` / ``fund_flow`` — **not stored** in the warehouse. The provider
  returns ``[]`` rather than inventing values; callers that need a truly
  adjusted panel must keep using the live provider for those two datasets.
- ``full_minute`` — **not stored**; returns ``[]`` for the same reason.

The empty-list behaviour is deliberate and mirrors ADR 0050 (read-only, no
fabrication): a silently-invented adjustment factor is worse than a missing one.
Callers check the ``capabilities`` set and decide whether that is acceptable.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence

from .engine_sqlite import EngineSqliteProvider
from .normalize import normalize_daily_row
from .symbol import normalize_symbol

PROVIDER_NAME = "market_db_bulk"

# Datasets this provider can actually serve from the warehouse.
SUPPORTED_DATASETS: tuple[str, ...] = ("daily",)

# Datasets the refresh job knows about but the warehouse does not carry.
UNSUPPORTED_DATASETS: tuple[str, ...] = ("adj_factor", "fund_flow", "full_minute")

_CHUNK = 900  # stay well under SQLite's default 999 bound-parameter limit


class MarketDbBulkProvider:
    """Read-only bulk daily source over the engine ``market.db``.

    Exposes the same ``get_daily`` signature as :class:`EngineSqliteProvider`
    (so it is a drop-in for ``build_cross_section_panel``) plus
    :meth:`bulk_daily` which returns ``{symbol: [rows]}`` in one query — the
    shape the refresh job wants.
    """

    name = PROVIDER_NAME
    capabilities = frozenset(SUPPORTED_DATASETS)

    def __init__(self, db_path: str | Path | None = None) -> None:
        # Reuse the engine adapter for path resolution + read-only connect.
        self._engine = EngineSqliteProvider(db_path)
        self.db_path = self._engine.db_path

    # -- introspection ---------------------------------------------------
    def latest_trade_date(self) -> str | None:
        return self._engine.latest_trade_date()

    def supports(self, dataset: str) -> bool:
        return dataset in self.capabilities

    def coverage_snapshot(self, **kwargs: Any) -> dict[str, Any]:
        return self._engine.coverage_snapshot(**kwargs)

    def list_symbols(self, **kwargs: Any) -> list[str]:
        return self._engine.list_symbols(**kwargs)

    # -- daily series ----------------------------------------------------
    def get_daily(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        asset_type: str = "stock",
    ) -> list[dict[str, Any]]:
        """Flat rows for the requested symbols (platform-normalised)."""
        return self._engine.get_daily(symbols, start=start, end=end, asset_type=asset_type)

    def bulk_daily(
        self,
        symbols: Sequence[str],
        *,
        start: date | None = None,
        end: date | None = None,
        asset_type: str = "stock",
    ) -> dict[str, list[dict[str, Any]]]:
        """``{bare_code: [row, ...]}`` for all symbols in **one** SQL pass.

        ``symbols`` that are absent from the warehouse map to an empty list so
        the caller can tell "no bars" from "not requested" without a second call.
        """
        wanted = _bare_codes(symbols)
        if not wanted:
            return {}

        out: dict[str, list[dict[str, Any]]] = {code: [] for code in wanted}
        engine_codes = _engine_code_map(wanted)

        with self._engine._connect() as conn:  # noqa: SLF001 — same package, one adapter
            for chunk in _chunks(list(engine_codes), _CHUNK):
                placeholders = ",".join("?" for _ in chunk)
                sql = (
                    "SELECT code, date, close, pct_chg, vol, amount "
                    f"FROM daily_price WHERE code IN ({placeholders})"
                )
                params: list[Any] = list(chunk)
                if start is not None:
                    sql += " AND date >= ?"
                    params.append(start.isoformat())
                if end is not None:
                    sql += " AND date <= ?"
                    params.append(end.isoformat())
                sql += " ORDER BY code, date"
                for code, trade_date, close, pct_chg, vol, amount in conn.execute(
                    sql, params
                ).fetchall():
                    bare = engine_codes.get(str(code))
                    if bare is None:
                        continue
                    out[bare].append(
                        normalize_daily_row(
                            {
                                "symbol": bare.zfill(6),
                                "date": str(trade_date)[:10],
                                "close": close,
                                "vol": vol,
                                "amount": amount,
                                "change_pct": pct_chg,
                                "pct_unit": "percent",
                            },
                            source=PROVIDER_NAME,
                            asset_type=asset_type,
                            market="CN",
                        )
                    )
        return out


def _bare_codes(symbols: Iterable[str]) -> list[str]:
    """Normalise to unique bare 6-digit codes, preserving order."""
    seen: dict[str, None] = {}
    for raw in symbols:
        code = normalize_symbol(raw, market="CN")
        if code:
            seen.setdefault(code, None)
    return list(seen)


def _engine_code_map(bare_codes: Sequence[str]) -> dict[str, str]:
    """Map every stored code spelling back to the bare 6-digit code.

    The warehouse mixes ``600519.SH`` and legacy bare ``600519``; both must fold
    onto one key or a symbol would split into two partial series.
    """
    out: dict[str, str] = {}
    for code in bare_codes:
        out[code] = code
        for suffix in ("SH", "SZ", "BJ"):
            out[f"{code}.{suffix}"] = code
        for prefix in ("sh", "sz", "bj"):
            out[f"{prefix}{code}"] = code
    return out


def _chunks(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


__all__ = [
    "PROVIDER_NAME",
    "SUPPORTED_DATASETS",
    "UNSUPPORTED_DATASETS",
    "MarketDbBulkProvider",
]
