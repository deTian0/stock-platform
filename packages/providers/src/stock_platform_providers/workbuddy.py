"""WorkBuddy MCP data source — JSON cache adapter.

The WorkBuddy platform exposes market data through its own MCP connectors
(``westock-data`` CLI and the ``neodata-financial-search`` HTTP service), both
of which are **agent-facing** (natural language / Markdown output) rather than a
deterministic, machine-callable OHLC API. For the platform's provider layer the
canonical hand-off is therefore a **JSON cache directory** populated by that MCP
bridge: the agent (or a thin export step) writes ``daily_{symbol}.json`` /
``realtime_{symbol}.json`` — the *same* layout the ``replay`` provider reads —
and this provider consumes them verbatim.

This keeps the provider deterministic and fully unit-testable (zero network),
while "workbuddy mode" remains live: point ``STOCK_PLATFORM_WORKBUDDY_CACHE_DIR``
at a directory the MCP bridge refreshes, and routing switches over with no code
change. The canonical writers (:func:`write_daily_cache` / :func:`write_realtime_cache`)
are the only place the JSON schema is produced.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .base import AssetType
from .errors import SymbolError
from .normalize import normalize_daily_row, normalize_realtime_row
from .symbol import normalize_symbol

ENV_WORKBUDDY_CACHE_DIR = "STOCK_PLATFORM_WORKBUDDY_CACHE_DIR"
PROVIDER_NAME = "workbuddy"

MSG_CACHE_MISSING = (
    "未配置 WorkBuddy 数据缓存目录：请设置 STOCK_PLATFORM_WORKBUDDY_CACHE_DIR "
    "指向由 WorkBuddy MCP（westock/neodata）落盘的 JSON 缓存目录；平台只读消费、不抓取。"
)


def resolve_workbuddy_cache_dir(env: dict[str, str] | None = None) -> Path | None:
    """Return the configured cache dir if set and it exists."""
    source = env if env is not None else os.environ
    raw = str(source.get(ENV_WORKBUDDY_CACHE_DIR, "") or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


def _load_bars(path: Path, symbol: str) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        bars = data.get("bars") or data.get("data") or []
        if not isinstance(bars, list):
            raise ValueError(f"workbuddy daily cache {path.name} has no bars list")
        return list(bars)
    if isinstance(data, list):
        return data
    raise ValueError(f"unexpected workbuddy daily cache shape in {path.name}")


def write_daily_cache(
    symbol: str,
    bars: Iterable[dict[str, Any]],
    cache_dir: str | Path,
    *,
    symbol_key: str = "symbol",
) -> Path:
    """Canonical writer for the MCP bridge: ``daily_{symbol}.json``.

    Each ``bar`` is a raw vendor dict shaped for :func:`normalize_daily_row`
    (``date``/``open``/``high``/``low``/``close``/``volume``/``amount``/
    ``change_pct``/``pct_unit`` …). ``symbol_key`` selects which field holds the
    symbol when the bar dicts already carry it (default ``"symbol"``).
    """
    code = normalize_symbol(str(symbol), market="CN")
    d = Path(cache_dir).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    items = []
    for bar in bars:
        row = dict(bar)
        row.setdefault(symbol_key, code)
        items.append(row)
    payload: dict[str, Any] = {"symbol": code, "bars": items}
    path = d / f"daily_{code}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_realtime_cache(
    symbol: str,
    quote: dict[str, Any],
    cache_dir: str | Path,
) -> Path:
    """Canonical writer for the MCP bridge: ``realtime_{symbol}.json``."""
    code = normalize_symbol(str(symbol), market="CN")
    d = Path(cache_dir).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    payload = dict(quote)
    payload.setdefault("symbol", code)
    path = d / f"realtime_{code}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


class WorkbuddyProvider:
    """Read WorkBuddy-MCP-landed JSON from a cache directory (offline-consistent).

    Layout mirrors the ``replay`` transport so a cache dir can double as fixtures
    and vice versa. ``daily`` and ``realtime`` are mapped; every other capability
    is intentionally **not** declared on the matrix (fail-closed until the MCP
    bridge exposes a stable machine schema for it).
    """

    name = PROVIDER_NAME

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        path = Path(cache_dir) if cache_dir is not None else resolve_workbuddy_cache_dir()
        if path is None:
            raise FileNotFoundError(MSG_CACHE_MISSING)
        if not path.is_dir():
            raise FileNotFoundError(f"workbuddy cache dir not found: {path}")
        self.cache_dir = path.resolve()

    def get_daily(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw_sym in symbols:
            symbol = normalize_symbol(raw_sym, market="CN")
            path = self.cache_dir / f"daily_{symbol}.json"
            if not path.is_file():
                continue
            for bar in _load_bars(path, symbol):
                row = normalize_daily_row(
                    bar,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=symbol,
                    market="CN",
                )
                d = date.fromisoformat(row["date"])
                if start and d < start:
                    continue
                if end and d > end:
                    continue
                rows.append(row)
        rows.sort(key=lambda r: (r["symbol"], r["date"]))
        return rows

    def get_realtime(
        self,
        symbols: list[str],
        *,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw_sym in symbols:
            symbol = normalize_symbol(raw_sym, market="CN")
            path = self.cache_dir / f"realtime_{symbol}.json"
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and (
                "price" in data or "last" in data or "close" in data
            ):
                quote = data
            elif isinstance(data, dict):
                quote = data.get("quote") or data.get("data")
                if not isinstance(quote, dict):
                    raise ValueError(
                        f"unexpected workbuddy realtime cache shape in {path.name}"
                    )
            else:
                raise ValueError(
                    f"unexpected workbuddy realtime cache shape in {path.name}"
                )
            try:
                rows.append(
                    normalize_realtime_row(
                        quote,
                        source=self.name,
                        asset_type=asset_type,
                        default_symbol=symbol,
                        market="CN",
                    )
                )
            except (ValueError, SymbolError):
                # A stale/partial snapshot should not take down the whole batch.
                continue
        return rows
