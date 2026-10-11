"""Offline-safe CN daily / full_minute refresh job.

Providers are injected (capability-matrix resolve at the call site).

Two execution paths
-------------------
1. **Bulk** (default when the provider exposes ``bulk_daily``, e.g. the offline
   :class:`~stock_platform_providers.market_db_bulk.MarketDbBulkProvider`): one
   SQL pass serves the whole universe for ``daily``. A measured whole-market
   120-day read is ~3s, so the 08:30 pre-market job finishes in seconds.
2. **Per-symbol with a thread pool** (live HTTP providers): ``workers`` parallel
   ``(symbol, dataset)`` tasks behind a shared rate-limit gate. The gate honours
   ``EM_MIN_INTERVAL`` so raising concurrency cannot outrun the upstream throttle.

Both paths write the same Replay-compatible JSON (ReplayTransport names), so a
refresh directory can always be replayed offline.
"""

from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from .universe import UniverseEmptyError, load_universe, normalize_universe

REFRESH_DATASETS: tuple[str, ...] = (
    "daily",
    "adj_factor",
    "fund_flow",
    "full_minute",
)

DEFAULT_LOOKBACK_DAYS = 120
DEFAULT_WORKERS = 1  # live HTTP: 1 = strictly serial (pre-P0-1 behaviour)
ENV_REFRESH_DIR = "STOCK_PLATFORM_REFRESH_DIR"
ENV_REFRESH_WORKERS = "STOCK_PLATFORM_REFRESH_WORKERS"
ENV_REFRESH_MIN_INTERVAL = "STOCK_PLATFORM_REFRESH_MIN_INTERVAL"


class RefreshProvider(Protocol):
    """Duck-typed market provider used by the refresh job."""

    def get_daily(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        asset_type: str = "stock",
    ) -> list[dict[str, Any]]: ...


Sleeper = Callable[[float], None]


class RefreshError(RuntimeError):
    """Raised when the job cannot start (empty universe / bad config)."""


# Marker for a per-symbol data gap (no bars for the requested window).
# This is a *data quality* signal, not a job failure: the cross-section panel
# already drops symbols with no bar on ``asof`` (strict PIT), so one thin
# symbol must not fail the whole daily run.
EMPTY_BARS_MARKER = "empty daily bars"

# Datasets whose per-symbol gap is tolerable for a daily *brief* run.
# The brief only consumes ``daily``; a symbol with no daily bar is silently
# skipped downstream (panel.py strict PIT), so a gap here is a warning, not a
# failure. Other datasets keep fail-closed semantics (they signal real errors).
TOLERABLE_GAP_DATASETS: frozenset[str] = frozenset({"daily"})


@dataclass
class RefreshItemResult:
    symbol: str
    dataset: str
    ok: bool
    attempts: int
    rows: int = 0
    path: str | None = None
    error: str | None = None

    @property
    def is_gap(self) -> bool:
        """True when this item has no bars but is otherwise a valid symbol.

        Distinguishes "the provider answered, there is simply no data" from a
        transport/schema error. ``ok`` stays ``False`` (it did not produce
        rows), but a gap does not by itself fail the run.
        """
        return (
            not self.ok
            and self.error is not None
            and EMPTY_BARS_MARKER in self.error
            and self.dataset in TOLERABLE_GAP_DATASETS
        )


@dataclass
class RefreshReport:
    asof: str
    out_dir: str
    datasets: list[str]
    symbols: list[str]
    ok: bool
    items: list[RefreshItemResult] = field(default_factory=list)
    # When True (default), a per-symbol empty-bar gap in a tolerable dataset
    # does not fail the run. Set False to restore strict all-or-nothing gating.
    tolerate_gaps: bool = True

    @property
    def gaps(self) -> list[RefreshItemResult]:
        return [i for i in self.items if i.is_gap]

    @property
    def hard_failures(self) -> list[RefreshItemResult]:
        """Items that fail the run: real errors, plus gaps when not tolerated."""
        return [
            i
            for i in self.items
            if not i.ok and not (self.tolerate_gaps and i.is_gap)
        ]

    def to_dict(self) -> dict[str, Any]:
        failed = self.hard_failures
        gaps = self.gaps
        return {
            "asof": self.asof,
            "outDir": self.out_dir,
            "datasets": list(self.datasets),
            "symbols": list(self.symbols),
            "ok": self.ok,
            "tolerateGaps": self.tolerate_gaps,
            "okCount": sum(1 for i in self.items if i.ok),
            "gapCount": len(gaps),
            "failCount": len(failed),
            "gaps": [
                {
                    "symbol": i.symbol,
                    "dataset": i.dataset,
                    "error": i.error,
                }
                for i in gaps
            ],
            "failures": [
                {
                    "symbol": i.symbol,
                    "dataset": i.dataset,
                    "attempts": i.attempts,
                    "error": i.error,
                }
                for i in failed
            ],
            "items": [
                {
                    "symbol": i.symbol,
                    "dataset": i.dataset,
                    "ok": i.ok,
                    "attempts": i.attempts,
                    "rows": i.rows,
                    "path": i.path,
                    "error": i.error,
                }
                for i in self.items
            ],
        }


def default_refresh_dir() -> Path:
    raw = os.environ.get(ENV_REFRESH_DIR, "").strip()
    if raw:
        return Path(raw)
    return Path.home() / ".stock-platform" / "refresh"


def default_workers() -> int:
    """Concurrency default for the per-symbol path.

    ``1`` unless ``STOCK_PLATFORM_REFRESH_WORKERS`` says otherwise. Serial by
    default so the live HTTP behaviour is unchanged until an operator opts in
    (they are the ones who know the upstream rate budget).
    """
    raw = (os.environ.get(ENV_REFRESH_WORKERS) or "").strip()
    if not raw:
        return DEFAULT_WORKERS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_WORKERS


def default_min_interval() -> float:
    """Minimum seconds between upstream calls across all workers.

    Reuses the East Money knob (``EM_MIN_INTERVAL``) so one setting governs both
    the EM client and this gate; ``STOCK_PLATFORM_REFRESH_MIN_INTERVAL`` overrides
    for non-EM sources. ``0`` disables pacing (offline / replay).
    """
    raw = (os.environ.get(ENV_REFRESH_MIN_INTERVAL) or "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    raw = (os.environ.get("EM_MIN_INTERVAL") or "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return 0.0


class RateLimiter:
    """Thread-safe minimum-interval gate shared by all refresh workers.

    Guarantees that no two upstream calls start closer than ``min_interval``
    seconds apart **in aggregate** — so ``workers=16`` still produces at most
    ``1 / min_interval`` requests per second and cannot outrun a provider
    throttle. ``min_interval=0`` makes :meth:`acquire` a no-op.
    """

    def __init__(
        self,
        min_interval: float,
        *,
        sleeper: Sleeper | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_interval = max(0.0, float(min_interval))
        self._sleeper = sleeper or time.sleep
        self._clock = clock
        self._lock = threading.Lock()
        self._last = 0.0

    def acquire(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            now = self._clock()
            wait = self.min_interval - (now - self._last)
            if wait > 0:
                self._sleeper(wait)
            self._last = self._clock()


def _to_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()[:10]
    return date.fromisoformat(text)


def _json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _filter_symbol(rows: list[dict[str, Any]], symbol: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw = str(row.get("symbol") or "").strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        if digits == symbol or raw == symbol:
            out.append(row)
        elif not raw:
            # Provider returned a single-symbol payload without symbol field.
            out.append(row)
    return out if out else list(rows)


def _fetch_dataset(
    provider: Any,
    dataset: str,
    symbol: str,
    *,
    asof: date,
    lookback_days: int,
) -> list[dict[str, Any]]:
    start = asof - timedelta(days=lookback_days)
    if dataset == "daily":
        if not hasattr(provider, "get_daily"):
            raise RefreshError("provider missing get_daily")
        rows = provider.get_daily([symbol], start=start, end=asof)
        return list(rows or [])
    if dataset == "adj_factor":
        if not hasattr(provider, "get_adj_factor"):
            raise RefreshError("provider missing get_adj_factor")
        rows = provider.get_adj_factor([symbol], start=start, end=asof, kind="qfq")
        return list(rows or [])
    if dataset == "fund_flow":
        if not hasattr(provider, "get_fund_flow"):
            raise RefreshError("provider missing get_fund_flow")
        rows = provider.get_fund_flow([symbol], start=start, end=asof)
        return list(rows or [])
    if dataset == "full_minute":
        if not hasattr(provider, "get_full_minute"):
            raise RefreshError("provider missing get_full_minute")
        rows = provider.get_full_minute([symbol], trade_date=asof)
        return list(rows or [])
    raise RefreshError(f"unknown dataset: {dataset}")


def _envelope(dataset: str, symbol: str, rows: list[dict[str, Any]]) -> Any:
    if dataset in {"daily", "adj_factor", "fund_flow", "full_minute"}:
        return {"symbol": symbol, "bars": rows}
    return {"symbol": symbol, "data": rows}


def _resolve_workers(workers: int | None) -> int:
    return max(1, int(workers)) if workers is not None else default_workers()


def _bulk_daily_allowed(
    provider: Any,
    datasets: list[str],
    bulk: bool | None,
) -> bool:
    """Whether the fast bulk path applies to this run.

    Requires an explicit opt-in (``bulk=True``) or a provider that advertises
    ``bulk_daily``; and every requested dataset must be bulk-capable, otherwise
    the run falls back to per-symbol so no dataset is silently skipped.
    """
    if bulk is False:
        return False
    if not hasattr(provider, "bulk_daily"):
        return False
    caps = getattr(provider, "capabilities", None)
    if caps is not None and any(d not in caps for d in datasets):
        return False
    return True


def _run_bulk(
    *,
    provider: Any,
    univ: list[str],
    datasets: list[str],
    day: date,
    lookback_days: int,
    day_dir: Path,
    persist: bool = True,
) -> list[RefreshItemResult]:
    """One-pass refresh for bulk-capable datasets (no per-symbol HTTP)."""
    items: list[RefreshItemResult] = []
    start = day - timedelta(days=lookback_days)
    for dataset in datasets:
        if dataset != "daily":
            # Bulk provider advertises only ``daily``; anything else is reported
            # as failed rather than quietly dropped.
            for sym in univ:
                items.append(
                    RefreshItemResult(
                        symbol=sym,
                        dataset=dataset,
                        ok=False,
                        attempts=1,
                        error=RefreshError(f"bulk provider does not serve {dataset!r}"),
                    )
                )
            continue
        try:
            by_symbol = provider.bulk_daily(univ, start=start, end=day)
        except Exception as exc:  # noqa: BLE001 — job must report any provider failure
            msg = f"{type(exc).__name__}: {exc}"
            for sym in univ:
                items.append(
                    RefreshItemResult(
                        symbol=sym, dataset=dataset, ok=False, attempts=1, error=msg
                    )
                )
            continue
        for sym in univ:
            rows = list(by_symbol.get(sym) or [])
            if not rows:
                items.append(
                    RefreshItemResult(
                        symbol=sym,
                        dataset=dataset,
                        ok=False,
                        attempts=1,
                        error="empty daily bars (fail-closed)",
                    )
                )
                continue
            path: str | None = None
            if persist:
                out_path = day_dir / f"{dataset}_{sym}.json"
                _json_dump(out_path, _envelope(dataset, sym, rows))
                path = str(out_path)
            items.append(
                RefreshItemResult(
                    symbol=sym,
                    dataset=dataset,
                    ok=True,
                    attempts=1,
                    rows=len(rows),
                    path=path,
                )
            )
    return items


def _refresh_one(
    *,
    provider: Any,
    symbol: str,
    dataset: str,
    day: date,
    lookback_days: int,
    max_attempts: int,
    sleeper: Sleeper | None,
    limiter: RateLimiter | None,
    day_dir: Path,
    persist: bool = True,
) -> RefreshItemResult:
    """Fetch + persist a single ``(symbol, dataset)`` pair (thread-safe)."""
    attempts = 0
    try:

        def _once(sym: str = symbol, name: str = dataset) -> list[dict[str, Any]]:
            if limiter is not None:
                limiter.acquire()
            raw = _fetch_dataset(
                provider,
                name,
                sym,
                asof=day,
                lookback_days=lookback_days,
            )
            rows = _filter_symbol(raw, sym)
            if name == "daily" and not rows:
                raise RefreshError("empty daily bars (fail-closed)")
            return rows

        rows, attempts = _call_with_retry(
            _once,
            max_attempts=max_attempts,
            sleeper=sleeper,
        )
        path: str | None = None
        if persist:
            out_path = day_dir / f"{dataset}_{symbol}.json"
            _json_dump(out_path, _envelope(dataset, symbol, rows))
            path = str(out_path)
        return RefreshItemResult(
            symbol=symbol,
            dataset=dataset,
            ok=True,
            attempts=attempts,
            rows=len(rows),
            path=path,
        )
    except Exception as exc:  # noqa: BLE001
        return RefreshItemResult(
            symbol=symbol,
            dataset=dataset,
            ok=False,
            attempts=attempts or max_attempts,
            error=f"{type(exc).__name__}: {exc}",
        )


def run_refresh(
    *,
    asof: date | str,
    provider: Any,
    out_dir: str | Path | None = None,
    universe_path: str | Path | None = None,
    symbols: list[str] | None = None,
    datasets: list[str] | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    max_attempts: int = 3,
    sleeper: Sleeper | None = None,
    workers: int | None = None,
    min_interval: float | None = None,
    bulk: bool | None = None,
    persist: bool = True,
    tolerate_gaps: bool = True,
) -> RefreshReport:
    """Refresh CN datasets for a universe and persist Replay-compatible JSON.

    Empty universe fail-closed. Per-symbol/dataset errors are recorded; the
    job continues.

    Gap vs failure
    --------------
    ``report.ok`` is False when any item failed **hard**. An item that answered
    with no bars (``"empty daily bars"``) on a tolerable dataset (``daily``) is
    classified as a *gap*: it is reported under ``gaps`` and counted in
    ``gapCount``, but does not fail the run. That matches the downstream
    consumer — the cross-section panel drops symbols lacking a bar on ``asof``
    (strict PIT) rather than erroring. Pass ``tolerate_gaps=False`` for strict
    all-or-nothing gating.

    Performance
    -----------
    ``workers > 1`` runs the per-symbol path on a thread pool and ``min_interval``
    (default: ``EM_MIN_INTERVAL``) paces **all** workers through one shared gate,
    so aggregate request rate never exceeds the provider's budget. When the
    provider exposes ``bulk_daily`` (offline market.db) the whole universe is
    served in a single pass instead — the 08:30 pre-market path.

    ``persist=False`` skips the per-symbol JSON dump. Measured on the real
    warehouse: the SQL read is ~3s while writing 5.2k JSON files costs ~110s, so
    the daily pipeline (which reads bars straight back through the provider and
    never replays the refresh dir) turns persistence off to stay well inside the
    pre-market budget. ``persist=True`` remains the default for the standalone
    ``stock-platform-refresh`` job, whose whole purpose is that replayable dir.

    Results are returned in ``(symbol, dataset)`` order regardless of execution
    mode, so callers and tests see a stable shape.
    """
    day = _to_date(asof)
    ds = list(datasets or REFRESH_DATASETS)
    unknown = [d for d in ds if d not in REFRESH_DATASETS]
    if unknown:
        raise RefreshError(f"unsupported datasets: {unknown}")

    if symbols is not None:
        univ = load_universe(symbols=symbols)
    elif universe_path is not None:
        univ = load_universe(universe_path)
    else:
        raise UniverseEmptyError("universe path or symbols is required")
    univ = normalize_universe(univ)

    root = Path(out_dir) if out_dir is not None else default_refresh_dir()
    day_dir = root / day.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)

    items: list[RefreshItemResult] = []
    if univ and _bulk_daily_allowed(provider, ds, bulk):
        items = _run_bulk(
            provider=provider,
            univ=univ,
            datasets=ds,
            day=day,
            lookback_days=lookback_days,
            day_dir=day_dir,
            persist=persist,
        )
    else:
        n_workers = _resolve_workers(workers)
        interval = default_min_interval() if min_interval is None else max(0.0, float(min_interval))
        limiter = RateLimiter(interval, sleeper=sleeper) if n_workers > 1 else None
        tasks = [(sym, d) for sym in univ for d in ds]

        def _task(task: tuple[str, str]) -> RefreshItemResult:
            sym, dataset = task
            return _refresh_one(
                provider=provider,
                symbol=sym,
                dataset=dataset,
                day=day,
                lookback_days=lookback_days,
                max_attempts=max_attempts,
                sleeper=sleeper,
                limiter=limiter,
                day_dir=day_dir,
                persist=persist,
            )

        if n_workers == 1 or len(tasks) <= 1:
            items = [_task(t) for t in tasks]
        else:
            with ThreadPoolExecutor(max_workers=n_workers) as pool:
                items = list(pool.map(_task, tasks))

    report = RefreshReport(
        asof=day.isoformat(),
        out_dir=str(day_dir),
        datasets=ds,
        symbols=univ,
        ok=bool(items) and not _hard_failure_items(items, tolerate_gaps),
        items=items,
        tolerate_gaps=tolerate_gaps,
    )
    payload = report.to_dict()
    _json_dump(day_dir / "manifest.json", payload)
    _json_dump(root / "latest.json", payload)
    return report


def _hard_failure_items(
    items: list[RefreshItemResult], tolerate_gaps: bool
) -> list[RefreshItemResult]:
    """Items that should fail the run (see :attr:`RefreshReport.hard_failures`)."""
    return [
        i for i in items if not i.ok and not (tolerate_gaps and i.is_gap)
    ]


def _call_with_retry(
    fn: Callable[[], list[dict[str, Any]]],
    *,
    max_attempts: int,
    sleeper: Sleeper | None,
) -> tuple[list[dict[str, Any]], int]:
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            rows = fn()
            return rows, attempt
        except Exception as exc:  # noqa: BLE001 — job must report any provider failure
            last_exc = exc
            if attempt < max_attempts and sleeper is not None:
                sleeper(0.0)
    assert last_exc is not None
    raise last_exc

