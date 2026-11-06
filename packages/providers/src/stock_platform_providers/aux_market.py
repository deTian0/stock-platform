"""Platform-owned read-only supplement market store (ADR 0095).

``local/aux_market/aux_market.db`` (override ``STOCK_PLATFORM_AUX_MARKET_DB``) —
**not** the engine ``market.db`` (never written here). Holds:

- ``index_daily``  — true index daily bars (000300/000905/000852/000016/399006),
  written only after East Money's returned ``data.code`` / ``data.name`` match
  the caller-supplied index name hints (fail-closed: mismatch → rejected).
- ``stock_ohlc``   — OHLC for an explicit code list (never whole-market by default).

Hard rules:

- East Money HTTP goes **only** through ``em_get`` (``get_json`` is injectable
  for replay / fake transport in tests).
- Budget: logical requests per Asia/Shanghai calendar day are capped by
  ``STOCK_PLATFORM_AUX_MARKET_EM_BUDGET`` (default 60), ledger in ``em_budget``.
- Idempotent: primary key ``(code, date)`` with ``ON CONFLICT DO UPDATE``.
- Fail-soft: :func:`sync_aux_market` never raises; failures land in the result
  and ``fetch_log``.
- Units: ``pct_chg`` decimal (EM f59 percent ÷ 100); ``amount`` 元; ``vol`` 手
  (EM raw); unadjusted prices (``fqt=0``).
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .astock_http import KLINE_URL, _parse_kline_csv, em_secid
from .symbol import exchange_prefix

ENV_AUX_MARKET_DB = "STOCK_PLATFORM_AUX_MARKET_DB"
ENV_AUX_MARKET_EM_BUDGET = "STOCK_PLATFORM_AUX_MARKET_EM_BUDGET"
DEFAULT_AUX_MARKET_REL = Path("local") / "aux_market" / "aux_market.db"
DEFAULT_DAILY_BUDGET = 60
SOURCE = "eastmoney_kline"

# Bare index code → East Money secid (index table, NOT the stock ``em_secid`` rule:
# 000905 as a stock is 0.000905 厦门港务; the CSI index lives on 1.000905).
INDEX_SECIDS: dict[str, str] = {
    "000300": "1.000300",
    "000905": "1.000905",
    "000852": "1.000852",
    "000016": "1.000016",
    "399006": "0.399006",
}
DEFAULT_INDICES: tuple[str, ...] = tuple(INDEX_SECIDS)

_CN_TZ = ZoneInfo("Asia/Shanghai")

GetJson = Callable[..., Any]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS index_daily (
    code TEXT NOT NULL, date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL,
    vol REAL, amount REAL, pct_chg REAL,
    source TEXT, fetched_at TEXT,
    PRIMARY KEY (code, date)
);
CREATE TABLE IF NOT EXISTS stock_ohlc (
    code TEXT NOT NULL, date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL,
    vol REAL, amount REAL, pct_chg REAL,
    source TEXT, fetched_at TEXT,
    PRIMARY KEY (code, date)
);
CREATE TABLE IF NOT EXISTS index_meta (
    code TEXT PRIMARY KEY, secid TEXT, name TEXT,
    verified_hint TEXT, verified_at TEXT
);
CREATE TABLE IF NOT EXISTS fetch_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT, kind TEXT, code TEXT, status TEXT, rows INTEGER, reason TEXT
);
CREATE TABLE IF NOT EXISTS em_budget (
    day TEXT PRIMARY KEY, used INTEGER NOT NULL DEFAULT 0
);
"""


class AuxBudgetExceeded(RuntimeError):
    """Raised inside the budgeted fetcher; always caught in this module."""


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
def resolve_aux_market_db(path: str | Path | None = None) -> Path:
    """Explicit path → ``STOCK_PLATFORM_AUX_MARKET_DB`` → ``./local/aux_market/aux_market.db``."""
    if path is not None and str(path).strip():
        return Path(path)
    raw = (os.environ.get(ENV_AUX_MARKET_DB) or "").strip()
    if raw:
        return Path(raw)
    return Path.cwd() / DEFAULT_AUX_MARKET_REL


def _assert_not_engine_db(path: Path) -> None:
    """Refuse to ever treat the engine warehouse as the write target."""
    if path.name.lower() == "market.db":
        raise ValueError(f"补充库不得命名为 market.db（引擎库只读）：{path}")
    engine = (os.environ.get("STOCK_PLATFORM_ENGINE_MARKET_DB") or "").strip()
    if engine:
        try:
            if Path(engine).resolve() == path.resolve():
                raise ValueError(f"补充库路径与 STOCK_PLATFORM_ENGINE_MARKET_DB 相同，拒写：{path}")
        except OSError:
            pass


def daily_budget_limit(env: Mapping[str, str] | None = None) -> int:
    src = env if env is not None else os.environ
    raw = str(src.get(ENV_AUX_MARKET_EM_BUDGET) or "").strip()
    if not raw:
        return DEFAULT_DAILY_BUDGET
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_DAILY_BUDGET


# --------------------------------------------------------------------------- #
# Transport
# --------------------------------------------------------------------------- #
def _em_get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Default transport: process-wide ``em_get`` (throttle + circuit + retries)."""
    from .eastmoney import em_get

    resp = em_get(url, params=params)
    if isinstance(resp, dict):
        return resp
    return resp.json()


class _BudgetedGetJson:
    def __init__(self, inner: GetJson, remaining: int) -> None:
        self._inner = inner
        self.remaining = max(0, int(remaining))
        self.used = 0

    def __call__(self, url: str, params: dict[str, Any] | None = None) -> Any:
        if self.used >= self.remaining:
            raise AuxBudgetExceeded(f"补充库东财请求预算已用尽（本次剩余 {self.remaining}）")
        self.used += 1
        return self._inner(url, params=params)


def _kline_params(secid: str, start: date, end: date) -> dict[str, Any]:
    return {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "0",
        "beg": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "lmt": "1000000",
    }


def _f(x: Any) -> float | None:
    if x is None or x in {"", "-"}:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse_klines(payload: Mapping[str, Any], start: date, end: date) -> list[dict[str, Any]]:
    """EM kline payload → rows (``pct_chg`` decimal). Rows outside [start, end] dropped."""
    data = payload.get("data") or {}
    out: list[dict[str, Any]] = []
    for line in data.get("klines") or []:
        raw = _parse_kline_csv(str(line))
        d = str(raw["date"])[:10]
        try:
            dd = date.fromisoformat(d)
        except ValueError:
            continue
        if dd < start or dd > end:
            continue
        pct = _f(raw.get("change_pct"))
        out.append(
            {
                "date": d,
                "open": _f(raw.get("open")),
                "high": _f(raw.get("high")),
                "low": _f(raw.get("low")),
                "close": _f(raw.get("close")),
                "vol": _f(raw.get("volume")),
                "amount": _f(raw.get("amount")),
                "pct_chg": pct / 100.0 if pct is not None else None,
            }
        )
    return out


def match_index_name(code: str, name: str | None, hints: Mapping[str, Sequence[str]]) -> str | None:
    """Return the matched alias, or ``None`` when the name is missing / unexpected."""
    if not name:
        return None
    for h in hints.get(code) or ():
        if h and h in str(name):
            return h
    return None


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #
def _connect_rw(path: Path) -> sqlite3.Connection:
    _assert_not_engine_db(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.executescript(_SCHEMA)
    return con


def _upsert(con: sqlite3.Connection, table: str, code: str, rows: Iterable[Mapping[str, Any]], now: str) -> int:
    assert table in {"index_daily", "stock_ohlc"}
    payload = [
        (
            code, r["date"], r.get("open"), r.get("high"), r.get("low"), r.get("close"),
            r.get("vol"), r.get("amount"), r.get("pct_chg"), SOURCE, now,
        )
        for r in rows
        if r.get("close") is not None
    ]
    con.executemany(
        f"""INSERT INTO {table}
            (code,date,open,high,low,close,vol,amount,pct_chg,source,fetched_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(code,date) DO UPDATE SET
              open=excluded.open, high=excluded.high, low=excluded.low,
              close=excluded.close, vol=excluded.vol, amount=excluded.amount,
              pct_chg=excluded.pct_chg, source=excluded.source,
              fetched_at=excluded.fetched_at""",
        payload,
    )
    return len(payload)


def _log(con: sqlite3.Connection, now: str, kind: str, code: str, status: str, rows: int, reason: str | None) -> None:
    con.execute(
        "INSERT INTO fetch_log (run_at,kind,code,status,rows,reason) VALUES (?,?,?,?,?,?)",
        (now, kind, code, status, int(rows), reason),
    )


def _stock_code(raw: str) -> tuple[str, str]:
    """``600519`` / ``600519.SH`` / ``sh600519`` → (bare, ``600519.SH``)."""
    s = str(raw or "").strip().upper()
    for p in ("SH", "SZ", "BJ"):
        if s.startswith(p) and s[len(p):].isdigit():
            s = s[len(p):]
            break
    bare = s.split(".", 1)[0]
    if not (bare.isdigit() and len(bare) == 6):
        raise ValueError(f"非 6 位 A 股代码：{raw!r}")
    return bare, f"{bare}.{exchange_prefix(bare).upper()}"


def plan_aux_sync(
    *,
    indices: Sequence[str] = (),
    codes: Sequence[str] = (),
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    """Requests that :func:`sync_aux_market` would issue (no network, no DB)."""
    plan: list[dict[str, Any]] = []
    for c in indices:
        secid = INDEX_SECIDS.get(str(c))
        plan.append({"kind": "index", "code": str(c), "secid": secid, "supported": secid is not None})
    for raw in codes:
        try:
            bare, full = _stock_code(raw)
            plan.append({"kind": "stock", "code": full, "secid": em_secid(bare), "supported": True})
        except Exception as exc:  # noqa: BLE001
            plan.append({"kind": "stock", "code": str(raw), "secid": None, "supported": False, "reason": str(exc)})
    for p in plan:
        p["start"] = start.isoformat()
        p["end"] = end.isoformat()
    return plan


def sync_aux_market(
    *,
    indices: Sequence[str] = (),
    codes: Sequence[str] = (),
    start: date,
    end: date,
    name_hints: Mapping[str, Sequence[str]] | None,
    db_path: str | Path | None = None,
    get_json: GetJson | None = None,
    daily_budget: int | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Fetch + idempotently upsert. **Never raises.**

    ``name_hints`` (bare index code → accepted name substrings) is required for
    index writes; a code without hints is rejected (fail-closed).
    """
    results: list[dict[str, Any]] = []
    out: dict[str, Any] = {"ok": False, "results": results}
    try:
        path = resolve_aux_market_db(db_path)
        out["db"] = str(path)
        con = _connect_rw(path)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return out
    hints = dict(name_hints or {})
    try:
        now = datetime.now(_CN_TZ).isoformat(timespec="seconds")
        run_day = (today or datetime.now(_CN_TZ).date()).isoformat()
        limit = daily_budget_limit() if daily_budget is None else max(0, int(daily_budget))
        row = con.execute("SELECT used FROM em_budget WHERE day=?", (run_day,)).fetchone()
        used_before = int(row[0]) if row else 0
        fetcher = _BudgetedGetJson(get_json or _em_get_json, limit - used_before)

        def _fetch(secid: str) -> dict[str, Any]:
            resp = fetcher(KLINE_URL, params=_kline_params(secid, start, end))
            if not isinstance(resp, dict):
                resp = resp.json()
            return resp

        def _record(kind: str, code: str, status: str, rows: int = 0, reason: str | None = None, **extra: Any) -> None:
            results.append({"kind": kind, "code": code, "status": status, "rows": rows, "reason": reason, **extra})
            _log(con, now, kind, code, status, rows, reason)

        for c in indices:
            code = str(c)
            secid = INDEX_SECIDS.get(code)
            if secid is None:
                _record("index", code, "rejected", reason=f"不支持的指数代码 {code}（无指数 secid）")
                continue
            if not hints.get(code):
                _record("index", code, "rejected", reason=f"{code} 无指数名称别名，无法核对身份（fail-closed）")
                continue
            try:
                payload = _fetch(secid)
                data = payload.get("data") or {}
                ret_code = str(data.get("code") or "")
                ret_name = data.get("name")
                if ret_code and ret_code != code:
                    _record("index", code, "rejected", reason=f"返回代码 {ret_code} ≠ {code}", name=ret_name)
                    continue
                hit = match_index_name(code, ret_name, hints)
                if hit is None:
                    _record(
                        "index", code, "rejected",
                        reason=f"返回名称 {ret_name!r} 未命中指数别名 {list(hints.get(code) or [])}，拒写",
                        name=ret_name,
                    )
                    continue
                rows = parse_klines(payload, start, end)
                if not rows:
                    _record("index", code, "empty", reason="区间内无 kline", name=ret_name)
                    continue
                n = _upsert(con, "index_daily", code, rows, now)
                con.execute(
                    """INSERT INTO index_meta (code,secid,name,verified_hint,verified_at)
                       VALUES (?,?,?,?,?)
                       ON CONFLICT(code) DO UPDATE SET secid=excluded.secid, name=excluded.name,
                         verified_hint=excluded.verified_hint, verified_at=excluded.verified_at""",
                    (code, secid, str(ret_name), hit, now),
                )
                _record(
                    "index", code, "ok", rows=n, name=ret_name, hint=hit,
                    first=rows[0]["date"], last=rows[-1]["date"],
                )
            except AuxBudgetExceeded as exc:
                _record("index", code, "budget_exceeded", reason=str(exc))
            except Exception as exc:  # noqa: BLE001 — one code never sinks the rest
                _record("index", code, "failed", reason=f"{type(exc).__name__}: {exc}"[:300])

        for raw in codes:
            try:
                bare, full = _stock_code(raw)
            except Exception as exc:  # noqa: BLE001
                _record("stock", str(raw), "rejected", reason=str(exc))
                continue
            try:
                payload = _fetch(em_secid(bare))
                data = payload.get("data") or {}
                ret_code = str(data.get("code") or "")
                if ret_code and ret_code != bare:
                    _record("stock", full, "rejected", reason=f"返回代码 {ret_code} ≠ {bare}")
                    continue
                rows = parse_klines(payload, start, end)
                if not rows:
                    _record("stock", full, "empty", reason="区间内无 kline", name=data.get("name"))
                    continue
                n = _upsert(con, "stock_ohlc", full, rows, now)
                _record(
                    "stock", full, "ok", rows=n, name=data.get("name"),
                    first=rows[0]["date"], last=rows[-1]["date"],
                )
            except AuxBudgetExceeded as exc:
                _record("stock", full, "budget_exceeded", reason=str(exc))
            except Exception as exc:  # noqa: BLE001
                _record("stock", full, "failed", reason=f"{type(exc).__name__}: {exc}"[:300])

        used_total = used_before + fetcher.used
        con.execute(
            "INSERT INTO em_budget (day,used) VALUES (?,?) ON CONFLICT(day) DO UPDATE SET used=excluded.used",
            (run_day, used_total),
        )
        con.commit()
        out.update(
            ok=all(r["status"] == "ok" for r in results),
            budget={
                "dailyLimit": limit,
                "runDate": run_day,
                "usedThisRun": fetcher.used,
                "usedToday": used_total,
                "exceeded": any(r["status"] == "budget_exceeded" for r in results),
            },
        )
        return out
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return out
    finally:
        try:
            con.close()
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- #
# Read side (read-only; missing store → None)
# --------------------------------------------------------------------------- #
def _connect_ro(path: Path) -> sqlite3.Connection | None:
    if not path.is_file():
        return None
    uri = "file:%s?mode=ro" % str(path.resolve()).replace("\\", "/")
    return sqlite3.connect(uri, uri=True)


def read_index_meta(code: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    try:
        con = _connect_ro(resolve_aux_market_db(db_path))
        if con is None:
            return None
        try:
            row = con.execute(
                "SELECT code,secid,name,verified_hint,verified_at FROM index_meta WHERE code=?",
                (str(code),),
            ).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return None
    if not row:
        return None
    return dict(zip(("code", "secid", "name", "verifiedHint", "verifiedAt"), row))


def read_index_closes(
    code: str, start: str, end: str, *, db_path: str | Path | None = None
) -> dict[str, float] | None:
    """``date → close`` for a verified index; ``None`` when store / rows absent."""
    try:
        con = _connect_ro(resolve_aux_market_db(db_path))
        if con is None:
            return None
        try:
            rows = con.execute(
                "SELECT date, close FROM index_daily WHERE code=? AND date>=? AND date<=? ORDER BY date",
                (str(code), str(start)[:10], str(end)[:10]),
            ).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return None
    out = {str(d)[:10]: float(c) for d, c in rows if c is not None}
    return out or None


def read_ohlc(
    code: str, start: str, end: str, *, db_path: str | Path | None = None
) -> list[dict[str, Any]] | None:
    """Stock OHLC rows for ``XXXXXX.EX`` (or bare); ``None`` when absent."""
    try:
        _, full = _stock_code(code)
        con = _connect_ro(resolve_aux_market_db(db_path))
        if con is None:
            return None
        try:
            cur = con.execute(
                "SELECT code,date,open,high,low,close,vol,amount,pct_chg FROM stock_ohlc "
                "WHERE code=? AND date>=? AND date<=? ORDER BY date",
                (full, str(start)[:10], str(end)[:10]),
            )
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        finally:
            con.close()
    except (sqlite3.Error, ValueError):
        return None
    return rows or None


__all__ = [
    "DEFAULT_DAILY_BUDGET",
    "DEFAULT_INDICES",
    "ENV_AUX_MARKET_DB",
    "ENV_AUX_MARKET_EM_BUDGET",
    "INDEX_SECIDS",
    "AuxBudgetExceeded",
    "daily_budget_limit",
    "match_index_name",
    "parse_klines",
    "plan_aux_sync",
    "read_index_closes",
    "read_index_meta",
    "read_ohlc",
    "resolve_aux_market_db",
    "sync_aux_market",
]
