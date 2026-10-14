"""本地「代码 ↔ 名称」主数据表（symbol master）—— 名称的**唯一权威来源**。

背景（2026-10-14 修复）::

    命中追踪报告曾出现「名称 = 代码」（如 ``000801 | 000801``）。根因是名称在
    记录时从 brief 条目取，而 brief 的 ``name`` 依赖一次性 ``name_map``；当该 map
    缺席（不同 provider / 重跑）时 ``hit_tracking._clean_name`` **拿代码顶替名称**，
    于是「未知」被渲染成「看起来正确」的错值；且 ``hit_tracking`` 按
    ``UNIQUE(code, session_type, pick_date)`` 去重，后续补齐的名称永远写不回去。

本模块把名称下沉成一张**本地全量主数据表**，供所有展示层（命中追踪 / 榜单 /
brief / digest）统一查询，从而:

- 名称与「哪一次跑批带了 name_map」彻底解耦；
- 未知**永不**回退成代码 —— 调用方拿不到就显示占位符，而不是伪装成正确值。

数据源：引擎只读 ``market.db`` 的 ``fundamentals(code, name, market)``
（当前覆盖 5237/5237，全量代码都有名字）。刷新是**幂等**的（``INSERT … ON
CONFLICT``），只读引擎库、只写平台库。

零依赖（stdlib only）；名称是装饰性信息，取不到绝不影响选股 / 评分 / 结算。

SIMULATE only. Not investment advice.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .persistence import default_db_url, resolve_sqlite_path
from .rankings import code_key

# 引擎 ``market.db`` 的默认定位环境变量（与 daily_cli / backtest_cli 共用）。
ENV_ENGINE_MARKET_DB = "STOCK_PLATFORM_ENGINE_MARKET_DB"

# 未知名称的展示占位符 —— **绝不**用代码顶替。
UNKNOWN_NAME = "—"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS symbol_master (
  code       TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  market     TEXT,
  source     TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_symbol_master_name ON symbol_master(name);
"""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def norm_code(value: Any) -> str:
    """6 位裸码（``600519.SH`` / ``sh600519`` / ``600519`` → ``600519``）。"""
    core = code_key(value)
    if core:
        return core
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits.zfill(6) if digits else ""


def clean_name(value: Any) -> str:
    """归一化名称：空 / ``nan`` / ``None`` / 等于代码 → ``""``（不伪造）。"""
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def resolve_engine_market_db(explicit: str | Path | None = None) -> Path | None:
    """定位引擎 ``market.db``：显式参数 > 环境变量；不存在返回 ``None``（fail-closed）。"""
    raw = str(explicit or os.environ.get(ENV_ENGINE_MARKET_DB) or "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None


class SymbolMasterRepository:
    """平台 SQLite 上的 symbol master 适配器（SQL 只留在这里）。"""

    def __init__(self, db_url: str | Path | None = None) -> None:
        if isinstance(db_url, Path):
            self._path: str | Path = db_url
            self.db_url = f"sqlite:///{db_url.as_posix()}"
        else:
            url = db_url if db_url is not None else default_db_url()
            self.db_url = url
            self._path = resolve_sqlite_path(url)
        self._ensure_schema()

    # -- plumbing ---------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        if self._path == ":memory:":
            conn = getattr(self, "_mem_conn", None)
            if conn is None:
                conn = sqlite3.connect(":memory:", check_same_thread=False)
                conn.row_factory = sqlite3.Row
                self._mem_conn = conn
            return conn
        path = Path(self._path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            if self._path != ":memory:":
                conn.close()

    # -- writes -----------------------------------------------------------
    def upsert_many(self, rows: Iterable[Mapping[str, Any]], *, source: str = "engine") -> int:
        """幂等写入 ``{code, name, market?}`` 序列；返回成功写入条数。

        名称缺失 / 归一化后为空的条目**跳过**（不写空值、不写代码）。
        """
        now = _utcnow_iso()
        payload: list[tuple[str, str, str | None, str, str]] = []
        for row in rows:
            code = norm_code(row.get("code") or row.get("symbol") or row.get("ts_code"))
            name = clean_name(row.get("name"))
            if not code or not name or name == code:
                continue
            market = str(row.get("market") or "").strip() or None
            payload.append((code, name, market, source, now))
        if not payload:
            return 0
        conn = self._connect()
        try:
            conn.executemany(
                """
                INSERT INTO symbol_master (code, name, market, source, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                  name=excluded.name,
                  market=COALESCE(excluded.market, symbol_master.market),
                  source=excluded.source,
                  updated_at=excluded.updated_at
                """,
                payload,
            )
            conn.commit()
        finally:
            if self._path != ":memory:":
                conn.close()
        return len(payload)

    # -- reads ------------------------------------------------------------
    def resolve(self, code: Any) -> str | None:
        """单个代码的名称；未收录返回 ``None``（**不是**代码）。"""
        key = norm_code(code)
        if not key:
            return None
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT name FROM symbol_master WHERE code=?", (key,)
            ).fetchone()
            return clean_name(row["name"]) or None if row is not None else None
        finally:
            if self._path != ":memory:":
                conn.close()

    def resolve_many(self, codes: Iterable[Any]) -> dict[str, str]:
        """批量解析，只返回命中的 ``{code: name}``。"""
        keys = [k for k in (norm_code(c) for c in codes) if k]
        if not keys:
            return {}
        out: dict[str, str] = {}
        conn = self._connect()
        try:
            # 分批以避开 SQLite 变量上限（默认 999）。
            for i in range(0, len(keys), 500):
                chunk = keys[i : i + 500]
                marks = ",".join("?" * len(chunk))
                for row in conn.execute(
                    f"SELECT code, name FROM symbol_master WHERE code IN ({marks})", chunk
                ).fetchall():
                    name = clean_name(row["name"])
                    if name:
                        out[row["code"]] = name
        finally:
            if self._path != ":memory:":
                conn.close()
        return out

    def load(self) -> dict[str, str]:
        """整表 ``{code: name}``（全量映射表）。"""
        conn = self._connect()
        try:
            return {
                row["code"]: clean_name(row["name"])
                for row in conn.execute("SELECT code, name FROM symbol_master").fetchall()
                if clean_name(row["name"])
            }
        finally:
            if self._path != ":memory:":
                conn.close()

    def count(self) -> int:
        conn = self._connect()
        try:
            return int(conn.execute("SELECT COUNT(*) FROM symbol_master").fetchone()[0])
        finally:
            if self._path != ":memory:":
                conn.close()

    def stats(self) -> dict[str, Any]:
        """覆盖情况（按数据源分组），供运维体检 / CLI 汇报。"""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT COALESCE(source, 'unknown') AS src, COUNT(*) AS n, "
                "MAX(updated_at) AS ts FROM symbol_master GROUP BY src ORDER BY n DESC"
            ).fetchall()
            return {
                "total": self.count(),
                "bySource": [
                    {"source": r["src"], "count": int(r["n"]), "updatedAt": r["ts"]} for r in rows
                ],
            }
        finally:
            if self._path != ":memory:":
                conn.close()


_SYMBOL_MASTER_CACHE: dict[str, SymbolMasterRepository] = {}


def open_symbol_master(db_url: str | Path | None = None) -> SymbolMasterRepository:
    """打开（并缓存）默认平台的 symbol master 仓库。"""
    if isinstance(db_url, Path):
        key = str(db_url.resolve())
        repo = _SYMBOL_MASTER_CACHE.get(key)
        if repo is None:
            repo = SymbolMasterRepository(db_url)
            _SYMBOL_MASTER_CACHE[key] = repo
        return repo
    key = db_url if db_url is not None else default_db_url()
    repo = _SYMBOL_MASTER_CACHE.get(key)
    if repo is None:
        repo = SymbolMasterRepository(key)
        _SYMBOL_MASTER_CACHE[key] = repo
    return repo


def reset_symbol_master_cache() -> None:
    """测试助手 —— 丢弃缓存仓库。"""
    _SYMBOL_MASTER_CACHE.clear()


# ---------------------------------------------------------------------------
# high-level helpers
# ---------------------------------------------------------------------------


def load_engine_symbol_rows(market_db: str | Path) -> list[dict[str, Any]]:
    """从引擎 ``market.db.fundamentals`` 读 ``{code, name, market}``（只读、fail-open）。

    缺表 / 缺列 / 打不开 → ``[]``（名称是装饰性的，绝不因此中断主链）。
    """
    path = Path(market_db)
    if not path.is_file():
        return []
    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(fundamentals)")}
        if not {"code", "name"} <= cols:
            return []
        market_col = "market" if "market" in cols else "'' AS market"
        rows = con.execute(
            f"SELECT code, name, {market_col} AS market FROM fundamentals"
        ).fetchall()
        return [{"code": r[0], "name": r[1], "market": r[2]} for r in rows]
    except sqlite3.Error:
        return []
    finally:
        con.close()


def refresh_from_engine(
    market_db: str | Path | None = None,
    *,
    db_url: str | Path | None = None,
) -> dict[str, Any]:
    """把引擎库的全量代码名称刷进本地 ``symbol_master``。

    返回 ``{ok, written, total, marketDb}``；引擎库缺失时 ``ok=False`` 且
    **不动**既有表（fail-closed：宁可保持旧数据，也不清空）。
    """
    resolved = resolve_engine_market_db(market_db)
    if resolved is None:
        return {
            "ok": False,
            "written": 0,
            "total": open_symbol_master(db_url).count(),
            "marketDb": None,
            "reason": f"引擎 market.db 不存在（${ENV_ENGINE_MARKET_DB} 未指向有效文件）",
        }
    rows = load_engine_symbol_rows(resolved)
    repo = open_symbol_master(db_url)
    written = repo.upsert_many(rows, source="engine_fundamentals")
    return {
        "ok": True,
        "written": written,
        "total": repo.count(),
        "marketDb": str(resolved),
        "reason": None,
    }


def name_map_from_master(
    *,
    db_url: str | Path | None = None,
    engine_db: str | Path | None = None,
) -> dict[str, str] | None:
    """``6位码 → 名称`` 映射：本地表优先，表空时按需从引擎库回源一次并落表。

    两者都拿不到 → ``None``（调用方据此**不写** name 键，保持既有字节契约）。
    """
    repo = open_symbol_master(db_url)
    table = repo.load()
    if table:
        return table
    refreshed = refresh_from_engine(engine_db, db_url=db_url)
    if not refreshed.get("ok"):
        return None
    table = repo.load()
    return table or None


def lookup_name(code: Any, *, db_url: str | Path | None = None) -> str:
    """展示用名称：命中返回名称，未收录返回 :data:`UNKNOWN_NAME`（绝不回退成代码）。"""
    got = open_symbol_master(db_url).resolve(code)
    return got or UNKNOWN_NAME


def display_name(
    code: Any,
    stored: Any = None,
    *,
    name_map: Mapping[str, str] | None = None,
) -> str:
    """名称解析的唯一入口，按优先级取：

    1. ``stored`` —— 记录里已存的真实名称（**排除**等于代码的伪名称）
    2. ``name_map`` —— 调用方显式提供的权威映射（给了就以它为准，不再回查库）
    3. 本地 ``symbol_master``（仅当 ``name_map is None``）
    4. :data:`UNKNOWN_NAME` 占位符

    任何一层都不能把代码当名称返回 —— 这正是 2026-10-14 那次事故的修法。
    """
    key = norm_code(code)
    text = clean_name(stored)
    if text and text != key:
        return text
    if name_map is not None:
        return clean_name(name_map.get(key)) or UNKNOWN_NAME
    return lookup_name(key) if key else UNKNOWN_NAME


__all__ = [
    "ENV_ENGINE_MARKET_DB",
    "UNKNOWN_NAME",
    "SymbolMasterRepository",
    "clean_name",
    "display_name",
    "load_engine_symbol_rows",
    "lookup_name",
    "name_map_from_master",
    "norm_code",
    "open_symbol_master",
    "refresh_from_engine",
    "reset_symbol_master_cache",
    "resolve_engine_market_db",
]
