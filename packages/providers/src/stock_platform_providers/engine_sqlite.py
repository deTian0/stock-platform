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
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .base import AssetType
from .errors import SymbolError
from .normalize import normalize_daily_row
from .symbol import is_bse_symbol, normalize_symbol

ENV_ENGINE_MARKET_DB = "STOCK_PLATFORM_ENGINE_MARKET_DB"
PROVIDER_NAME = "engine_sqlite"

# X1: default window used when enumerating the whole market (calendar days).
DEFAULT_UNIVERSE_LOOKBACK_DAYS = 120
DEFAULT_UNIVERSE_MIN_BARS = 1

# C2: coverage / freshness guard for `daily_price` (calendar-day window + full-market floor).
# A full A-share cross-section is ~5.2k rows; anything far below is a partial import.
DEFAULT_COVERAGE_LOOKBACK_DAYS = 30
DEFAULT_COVERAGE_MIN_ROWS = 3000

MSG_COVERAGE_TABLE_MISSING = (
    "引擎 market.db 缺少 daily_price 表：平台只读，无法代抓；请先在引擎侧完成日线导入。"
)

# Human-readable verdicts for `EngineSqliteProvider.coverage_snapshot` (Chinese, no i18n layer).
_MSG_COVERAGE: dict[str, str] = {
    "ok": "日线覆盖正常：窗口内全部交易日齐全，且达到全市场行数下限。",
    "thin": "日线覆盖偏薄：存在低于全市场行数下限的交易日（部分导入）。",
    "stale": "日线覆盖滞后：窗口内存在缺失的交易日，引擎侧导入可能已中断。",
    "empty": "日线为空：窗口内没有任何交易日数据。",
    "missing_table": MSG_COVERAGE_TABLE_MISSING,
}

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

    def latest_trade_date(self) -> str | None:
        """Max ``date`` in ``daily_price`` (ISO ``YYYY-MM-DD``), ``None`` if empty."""
        with self._connect() as conn:
            row = conn.execute("SELECT MAX(date) FROM daily_price").fetchone()
        if row is None or row[0] is None:
            return None
        return _norm_ymd(row[0])

    def coverage_snapshot(
        self,
        *,
        asof: date | str | None = None,
        lookback_days: int = DEFAULT_COVERAGE_LOOKBACK_DAYS,
        min_rows: int = DEFAULT_COVERAGE_MIN_ROWS,
    ) -> dict[str, Any]:
        """Read-only ``daily_price`` coverage / freshness snapshot (milestone ``C2``).

        Guards the failure mode where the engine ingest stops **silently**: the table
        keeps a plausible ``MAX(date)`` while every fresh day is either absent or a
        thin partial import (the engine's ``refresh_etf_daily_prices`` writes only
        ~14 ETFs per day, so a stalled *stock* ingest shows up as ``14 rows`` days
        next to a wall of full ~5.2k-row history).

        Never mutates the warehouse (``mode=ro``, ADR 0050) and never raises for
        data-shape reasons — ``status`` carries the verdict so ops can log it without
        wrapping every field in ``try/except``:

        - ``ok``            window complete, every day at/above ``min_rows``
        - ``thin``          days present but below ``min_rows`` (partial import)
        - ``stale``         expected trading day(s) missing / ``latest`` lags behind
        - ``empty``         no rows at all in the window
        - ``missing_table`` ``daily_price`` absent (engine never imported)

        ``lagTradingDays`` counts CN trading days strictly after ``latestTradeDate``
        up to the expected trading day, so a weekend/holiday tail is never reported
        as staleness.
        """
        from .calendar import get_trading_calendar  # local import keeps module load light

        target = (
            date.fromisoformat(_norm_ymd(asof)) if asof not in (None, "") else date.today()
        )
        cal = get_trading_calendar("CN")
        expected = cal.last_trading_day(target)
        span = max(1, int(lookback_days))
        window_start = expected - timedelta(days=span)

        with self._connect() as conn:
            if not self._table_exists(conn, "daily_price"):
                return {
                    "status": "missing_table",
                    "dbPath": str(self.db_path),
                    "expectedTradingDay": expected.isoformat(),
                    "windowStart": window_start.isoformat(),
                    "lookbackDays": span,
                    "minRowsPerDay": int(min_rows),
                    "message": MSG_COVERAGE_TABLE_MISSING,
                }
            rows = conn.execute(
                "SELECT date, COUNT(*) FROM daily_price "
                "WHERE date >= ? AND date <= ? GROUP BY date",
                (window_start.isoformat(), expected.isoformat()),
            ).fetchall()

        counts: dict[str, int] = {
            _norm_ymd(d): int(n or 0) for d, n in rows if d is not None
        }

        # Expected CN trading days inside the window (ascending, inclusive).
        expected_days: list[date] = []
        cursor = expected
        while cursor >= window_start:
            if cal.is_trading_day(cursor):
                expected_days.append(cursor)
            cursor -= timedelta(days=1)
        expected_days.reverse()

        missing = [d.isoformat() for d in expected_days if d.isoformat() not in counts]
        thin = [
            {"date": d, "rows": counts[d]}
            for d in (x.isoformat() for x in expected_days)
            if d in counts and counts[d] < int(min_rows)
        ]

        latest = max(counts) if counts else None
        lag = 0
        if latest is not None:
            probe = date.fromisoformat(latest) + timedelta(days=1)
            while probe <= expected:
                if cal.is_trading_day(probe):
                    lag += 1
                probe += timedelta(days=1)

        if not counts:
            status = "empty"
        elif missing or lag > 0:
            status = "stale"
        elif thin:
            status = "thin"
        else:
            status = "ok"

        return {
            "status": status,
            "dbPath": str(self.db_path),
            "expectedTradingDay": expected.isoformat(),
            "latestTradeDate": latest,
            "latestRows": counts.get(latest, 0) if latest else 0,
            "lagTradingDays": lag,
            "windowStart": window_start.isoformat(),
            "lookbackDays": span,
            "minRowsPerDay": int(min_rows),
            "expectedDays": len(expected_days),
            "missingDays": missing,
            "thinDays": thin,
            "message": _MSG_COVERAGE.get(status, ""),
        }

    def list_symbols(
        self,
        *,
        asof: date | str | None = None,
        lookback_days: int = DEFAULT_UNIVERSE_LOOKBACK_DAYS,
        min_bars: int = DEFAULT_UNIVERSE_MIN_BARS,
        include_bse: bool = False,
        limit: int | None = None,
    ) -> list[str]:
        """Enumerate tradable codes from ``daily_price`` (milestone ``X1``).

        This is the **single source of truth** for turning the engine warehouse
        into a symbol list: :mod:`stock_platform_research.market_universe`
        consumes the result and never re-implements the query, so coverage rules
        (window / min bars / BSE) have exactly one definition.

        Behaviour
        ---------
        - ``asof`` defaults to the latest trade date present in the DB
        - window is ``[asof - lookback_days, asof]`` (calendar days)
        - bar counts are summed **after** collapsing ``600519.SH`` and the legacy
          bare ``600519`` form onto the same 6-digit code (the warehouse mixes both)
        - ``min_bars`` drops delisted / long-suspended / dirty leftovers
        - BSE (``4`` / ``8`` / ``92`` prefixes) excluded via
          :func:`symbol.is_bse_symbol` unless ``include_bse=True``
        - rows whose code is not a 6-digit A-share number (e.g. ``"42"``, ``"8"``)
          are always dropped
        - returns sorted bare 6-digit codes; **empty → ``[]``** (fail-closed is
          the caller's job, see ``market_universe.resolve_market_universe``)
        """
        if asof in (None, ""):
            asof_s = self.latest_trade_date()
            if asof_s is None:
                return []
        else:
            asof_s = _norm_ymd(asof)

        with self._connect() as conn:
            start_d = date.fromisoformat(asof_s) - timedelta(days=int(lookback_days))
            rows = conn.execute(
                "SELECT code, COUNT(*) AS n FROM daily_price "
                "WHERE date >= ? AND date <= ? GROUP BY code",
                (start_d.isoformat(), asof_s),
            ).fetchall()

        counts: dict[str, int] = {}
        for code, n in rows:
            bare = str(code).split(".")[0].strip()
            if not (bare.isdigit() and len(bare) == 6):
                continue
            counts[bare] = counts.get(bare, 0) + int(n or 0)

        min_n = max(1, int(min_bars))
        out: list[str] = []
        for bare in sorted(counts):
            if counts[bare] < min_n:
                continue
            if not include_bse and is_bse_symbol(bare):
                continue
            out.append(bare)
        if limit is not None:
            out = out[: max(0, int(limit))]
        return out

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
