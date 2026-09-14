"""Offline-safe CN daily / full_minute refresh job.

Providers are injected (capability-matrix resolve at the call site). No HTTP.
Persisted files use ReplayTransport names so a refresh dir can be replayed.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Protocol

from .universe import UniverseEmptyError, load_universe, normalize_universe

REFRESH_DATASETS: tuple[str, ...] = (
    "daily",
    "adj_factor",
    "fund_flow",
    "full_minute",
)

DEFAULT_LOOKBACK_DAYS = 120
ENV_REFRESH_DIR = "STOCK_PLATFORM_REFRESH_DIR"


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


@dataclass
class RefreshItemResult:
    symbol: str
    dataset: str
    ok: bool
    attempts: int
    rows: int = 0
    path: str | None = None
    error: str | None = None


@dataclass
class RefreshReport:
    asof: str
    out_dir: str
    datasets: list[str]
    symbols: list[str]
    ok: bool
    items: list[RefreshItemResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        failed = [i for i in self.items if not i.ok]
        return {
            "asof": self.asof,
            "outDir": self.out_dir,
            "datasets": list(self.datasets),
            "symbols": list(self.symbols),
            "ok": self.ok,
            "okCount": sum(1 for i in self.items if i.ok),
            "failCount": len(failed),
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
) -> RefreshReport:
    """Refresh CN datasets for a universe and persist Replay-compatible JSON.

    Empty universe fail-closed. Per-symbol/dataset errors are recorded; the
    job continues. ``report.ok`` is False if any item failed.
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
    for symbol in univ:
        for dataset in ds:
            attempts = 0
            try:

                def _once(sym: str = symbol, name: str = dataset) -> list[dict[str, Any]]:
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
                rel = f"{dataset}_{symbol}.json"
                path = day_dir / rel
                _json_dump(path, _envelope(dataset, symbol, rows))
                items.append(
                    RefreshItemResult(
                        symbol=symbol,
                        dataset=dataset,
                        ok=True,
                        attempts=attempts,
                        rows=len(rows),
                        path=str(path),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                items.append(
                    RefreshItemResult(
                        symbol=symbol,
                        dataset=dataset,
                        ok=False,
                        attempts=attempts or max_attempts,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )

    report = RefreshReport(
        asof=day.isoformat(),
        out_dir=str(day_dir),
        datasets=ds,
        symbols=univ,
        ok=all(i.ok for i in items) and bool(items),
        items=items,
    )
    payload = report.to_dict()
    _json_dump(day_dir / "manifest.json", payload)
    _json_dump(root / "latest.json", payload)
    return report
