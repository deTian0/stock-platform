"""Read-only CN daily + optional PIT fundamentals from a-stock-engine ``market.db``.

Points at the engine SQLite via ``STOCK_PLATFORM_ENGINE_MARKET_DB`` (path to
``data_cache/market.db``). Does **not** import or mutate the engine repo —
only opens the DB read-only and maps:

- ``daily_price`` → platform ``daily`` rows (capability matrix)
- ``fundamentals_pit`` / ``daily_basic_pit`` → offline PIT helpers (ADR 0050;
  **not** the live ``financial`` capability)

Limitations:
- Daily: OHLC open/high/low are None when absent; coverage ends at last import.
- PIT: requires ``asof``; rows without ``ann_date`` are dropped; missing tables
  or path → explicit Chinese errors (fail-closed).
- Not a production live default — use preset ``cn_engine_sqlite`` or settle
  fallback when the env path is set.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from .base import AssetType
from .errors import SymbolError
from .normalize import normalize_daily_row
from .symbol import normalize_symbol

ENV_ENGINE_MARKET_DB = "STOCK_PLATFORM_ENGINE_MARKET_DB"
PROVIDER_NAME = "engine_sqlite"

# Fail-closed Chinese messages (Workbench / research callers may surface as-is).
MSG_DB_MISSING = (
    "未配置或找不到引擎 market.db：请设置 STOCK_PLATFORM_ENGINE_MARKET_DB "
    "指向 a-stock-engine/data_cache/market.db（只读）；禁止静默空结果冒充 PIT。"
)
MSG_TABLE_MISSING = (
    "引擎 market.db 缺少 PIT 表 {table}：请先在引擎侧导入 fundamentals_pit / "
    "daily_basic_pit；平台只读、不抓取。"
)
MSG_ASOF_REQUIRED = "PIT 查询必须提供 asof（YYYY-MM-DD），禁止无截止日扫全表。"


def resolve_engine_market_db(env: dict[str, str] | None = None) -> Path | None:
    """Return configured market.db path if set and the file exists."""
    source = env if env is not None else os.environ
    raw = str(source.get(ENV_ENGINE_MARKET_DB, "") or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_file() else None


def _engine_codes(symbol: str) -> list[str]:
    """Map platform symbol → candidate keys in engine ``daily_price.code``."""
    try:
        sym = normalize_symbol(str(symbol), market="CN")
    except SymbolError:
        return []
    bare = sym[-6:] if len(sym) >= 6 else sym.zfill(6)
    if not bare.isdigit() or len(bare) != 6:
        return [bare]
    # a-stock-engine stores ts_code-like keys: 600519.SH / 000001.SZ / 430047.BJ
    if bare.startswith(("5", "6", "9")):
        suffix = "SH"
    elif bare.startswith(("4", "8")):
        suffix = "BJ"
    else:
        suffix = "SZ"
    return [f"{bare}.{suffix}", bare]


def _norm_ymd(value: str | date) -> str:
    """Normalize to ``YYYY-MM-DD`` for ISO compares; engine may store YYYYMMDD."""
    if isinstance(value, date):
        return value.isoformat()
    s = str(value).strip().replace("-", "")
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return str(value)[:10]


def _ann_date_ok(ann: Any) -> bool:
    if ann is None:
        return False
    s = str(ann).strip().replace("-", "")
    return len(s) >= 8 and s[:8].isdigit()


class EngineSqliteProvider:
    """Thin adapter: a-stock-engine tables → platform daily / PIT helpers."""

    name = PROVIDER_NAME

    def __init__(self, db_path: str | Path | None = None) -> None:
        path = Path(db_path) if db_path is not None else resolve_engine_market_db()
        if path is None:
            raise FileNotFoundError(MSG_DB_MISSING)
        if not path.is_file():
            raise FileNotFoundError(f"engine market db not found: {path}")
        self.db_path = path.resolve()

    def _connect(self) -> sqlite3.Connection:
        # Read-only URI — never write into the engine warehouse.
        return sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True)

    def _table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
        return row is not None

    def _require_table(self, conn: sqlite3.Connection, table: str) -> None:
        if not self._table_exists(conn, table):
            raise LookupError(MSG_TABLE_MISSING.format(table=table))

    def get_daily(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        if not symbols:
            return []
        code_to_bare: dict[str, str] = {}
        for raw in symbols:
            candidates = _engine_codes(raw)
            if not candidates:
                continue
            bare = candidates[0].split(".")[0]
            for c in candidates:
                code_to_bare[c] = bare
        codes = list(code_to_bare.keys())
        if not codes:
            return []

        placeholders = ",".join("?" for _ in codes)
        sql = (
            f"SELECT code, date, close, pct_chg, vol, amount "
            f"FROM daily_price WHERE code IN ({placeholders})"
        )
        params: list[Any] = list(codes)
        if start is not None:
            sql += " AND date >= ?"
            params.append(start.isoformat())
        if end is not None:
            sql += " AND date <= ?"
            params.append(end.isoformat())
        sql += " ORDER BY code, date"

        out: list[dict[str, Any]] = []
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        for code, trade_date, close, pct_chg, vol, amount in rows:
            bare = code_to_bare.get(str(code)) or str(code).split(".")[0]
            raw = {
                "symbol": bare.zfill(6),
                "date": str(trade_date)[:10],
                "close": close,
                "vol": vol,
                "amount": amount,
                "change_pct": pct_chg,
                "pct_unit": "percent",
            }
            out.append(
                normalize_daily_row(
                    raw,
                    source=PROVIDER_NAME,
                    asset_type=asset_type,
                    market="CN",
                )
            )
        return out

    def get_realtime(
        self,
        symbols: list[str],
        *,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "engine_sqlite is daily-only (offline market.db); use live/replay for realtime"
        )

    def get_fundamentals_pit(
        self,
        symbols: list[str],
        *,
        asof: date | str,
    ) -> list[dict[str, Any]]:
        """Latest ``fundamentals_pit`` row per symbol with ``ann_date <= asof``.

        Offline helper (ADR 0050) — **not** matrix ``financial``. Missing DB /
        table → fail-closed Chinese error. Rows without usable ``ann_date`` skipped.
        """
        if asof in (None, ""):
            raise ValueError(MSG_ASOF_REQUIRED)
        asof_s = _norm_ymd(asof)
        if not symbols:
            return []

        code_to_bare: dict[str, str] = {}
        for raw in symbols:
            for c in _engine_codes(raw):
                code_to_bare[c] = c.split(".")[0]
        codes = list(code_to_bare.keys())
        if not codes:
            return []

        placeholders = ",".join("?" for _ in codes)
        sql = (
            f"SELECT code, end_date, ann_date, roe, roa, gross_margin, debt_ratio, "
            f"revenue_growth, profit_growth, eps, eps_ttm, bps, report_type "
            f"FROM fundamentals_pit WHERE code IN ({placeholders})"
        )

        by_bare: dict[str, dict[str, Any]] = {}
        with self._connect() as conn:
            self._require_table(conn, "fundamentals_pit")
            rows = conn.execute(sql, codes).fetchall()

        for row in rows:
            (
                code,
                end_date,
                ann_date,
                roe,
                roa,
                gross_margin,
                debt_ratio,
                revenue_growth,
                profit_growth,
                eps,
                eps_ttm,
                bps,
                report_type,
            ) = row
            if not _ann_date_ok(ann_date):
                continue
            ann_s = _norm_ymd(str(ann_date))
            if ann_s > asof_s:
                continue
            bare = code_to_bare.get(str(code)) or str(code).split(".")[0]
            end_s = _norm_ymd(str(end_date)) if end_date else ""
            prev = by_bare.get(bare)
            # Prefer latest end_date among visible announcements; tie-break ann_date.
            if prev is None or (end_s, ann_s) > (
                str(prev.get("end_date") or ""),
                str(prev.get("ann_date") or ""),
            ):
                by_bare[bare] = {
                    "symbol": bare.zfill(6),
                    "source": PROVIDER_NAME,
                    "dataNote": "offline_pit",
                    "asof": asof_s,
                    "end_date": end_s,
                    "ann_date": ann_s,
                    "roe": roe,
                    "roa": roa,
                    "gross_margin": gross_margin,
                    "debt_ratio": debt_ratio,
                    "revenue_growth": revenue_growth,
                    "profit_growth": profit_growth,
                    "eps": eps,
                    "eps_ttm": eps_ttm,
                    "bps": bps,
                    "report_type": report_type,
                }
        return [by_bare[k] for k in sorted(by_bare)]

    def get_daily_basic_pit(
        self,
        symbols: list[str],
        *,
        asof: date | str,
    ) -> list[dict[str, Any]]:
        """``daily_basic_pit`` rows with ``trade_date = asof`` (exact day).

        Offline helper (ADR 0050). No asof / missing table → fail-closed.
        """
        if asof in (None, ""):
            raise ValueError(MSG_ASOF_REQUIRED)
        asof_s = _norm_ymd(asof)
        asof_compact = asof_s.replace("-", "")
        if not symbols:
            return []

        code_to_bare: dict[str, str] = {}
        for raw in symbols:
            for c in _engine_codes(raw):
                code_to_bare[c] = c.split(".")[0]
        codes = list(code_to_bare.keys())
        if not codes:
            return []

        placeholders = ",".join("?" for _ in codes)
        # Engine may store trade_date as YYYY-MM-DD or YYYYMMDD.
        sql = (
            f"SELECT code, trade_date, pe, pe_ttm, pb, ps, ps_ttm, dv_ratio, "
            f"total_mv, circ_mv FROM daily_basic_pit "
            f"WHERE code IN ({placeholders}) AND (trade_date = ? OR trade_date = ?)"
        )
        params: list[Any] = list(codes) + [asof_s, asof_compact]

        out: list[dict[str, Any]] = []
        with self._connect() as conn:
            self._require_table(conn, "daily_basic_pit")
            rows = conn.execute(sql, params).fetchall()

        for (
            code,
            trade_date,
            pe,
            pe_ttm,
            pb,
            ps,
            ps_ttm,
            dv_ratio,
            total_mv,
            circ_mv,
        ) in rows:
            bare = code_to_bare.get(str(code)) or str(code).split(".")[0]
            out.append(
                {
                    "symbol": bare.zfill(6),
                    "source": PROVIDER_NAME,
                    "dataNote": "offline_pit",
                    "asof": asof_s,
                    "trade_date": _norm_ymd(str(trade_date)),
                    "pe": pe,
                    "pe_ttm": pe_ttm,
                    "pb": pb,
                    "ps": ps,
                    "ps_ttm": ps_ttm,
                    "dv_ratio": dv_ratio,
                    "total_mv": total_mv,
                    "circ_mv": circ_mv,
                }
            )
        out.sort(key=lambda r: r["symbol"])
        return out
