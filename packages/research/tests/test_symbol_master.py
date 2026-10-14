"""symbol master：本地「代码 ↔ 名称」主数据表 + 名称解析唯一入口。

锁定 2026-10-14 那次事故的修法：**未知名称绝不回退成代码**。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from stock_platform_research.symbol_master import (
    UNKNOWN_NAME,
    SymbolMasterRepository,
    display_name,
    load_engine_symbol_rows,
    name_map_from_master,
    open_symbol_master,
    refresh_from_engine,
    reset_symbol_master_cache,
)


@pytest.fixture()
def repo(tmp_path: Path) -> SymbolMasterRepository:
    return SymbolMasterRepository(tmp_path / "sym.db")


def _engine_db(path: Path, rows: list[tuple[str, str, str]]) -> Path:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE fundamentals (code TEXT, name TEXT, market TEXT)")
    con.executemany("INSERT INTO fundamentals VALUES (?,?,?)", rows)
    con.commit()
    con.close()
    return path


# ---------------------------------------------------------------------------
# refresh
# ---------------------------------------------------------------------------


def test_refresh_from_engine_fills_the_table(repo, tmp_path: Path) -> None:
    engine = _engine_db(
        tmp_path / "market.db",
        [("601038", "一拖股份", "sh"), ("000801", "四川九洲", "sz")],
    )
    result = refresh_from_engine(engine, db_url=repo._path)
    assert result["ok"] is True
    assert result["written"] == 2
    assert repo.load() == {"601038": "一拖股份", "000801": "四川九洲"}


def test_refresh_is_idempotent(repo, tmp_path: Path) -> None:
    engine = _engine_db(tmp_path / "market.db", [("601038", "一拖股份", "sh")])
    refresh_from_engine(engine, db_url=repo._path)
    refresh_from_engine(engine, db_url=repo._path)
    assert repo.count() == 1


def test_refresh_skips_blank_and_code_as_name(repo, tmp_path: Path) -> None:
    """空名称 / 名称等于代码 → 不写库（宁可缺失，也不写伪名称）。"""
    engine = _engine_db(
        tmp_path / "market.db",
        [("600519", "贵州茅台", "sh"), ("000001", "", "sz"), ("000002", "000002", "sz")],
    )
    result = refresh_from_engine(engine, db_url=repo._path)
    assert result["written"] == 1
    assert repo.load() == {"600519": "贵州茅台"}


def test_refresh_missing_engine_db_is_fail_closed(repo, tmp_path: Path) -> None:
    """引擎库不存在 → 不动既有表（fail-closed，绝不清空）。"""
    engine = _engine_db(tmp_path / "market.db", [("600519", "贵州茅台", "sh")])
    refresh_from_engine(engine, db_url=repo._path)
    result = refresh_from_engine(tmp_path / "nope.db", db_url=repo._path)
    assert result["ok"] is False
    assert result["total"] == 1
    assert repo.load() == {"600519": "贵州茅台"}


def test_engine_db_without_fundamentals_yields_nothing(tmp_path: Path) -> None:
    db = tmp_path / "bare.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE daily_price (code TEXT, date TEXT, close REAL)")
    con.commit()
    con.close()
    assert load_engine_symbol_rows(db) == []


def test_upsert_many_accepts_symbol_and_ts_code_forms(repo) -> None:
    written = repo.upsert_many(
        [{"symbol": "600519.SH", "name": "贵州茅台"}, {"ts_code": "sh601038", "name": "一拖股份"}]
    )
    assert written == 2
    assert repo.resolve("600519") == "贵州茅台"
    assert repo.resolve("601038.SH") == "一拖股份"


# ---------------------------------------------------------------------------
# resolve / load
# ---------------------------------------------------------------------------


def test_resolve_returns_none_when_unknown(repo) -> None:
    repo.upsert_many([{"code": "600519", "name": "贵州茅台"}])
    assert repo.resolve("600519") == "贵州茅台"
    assert repo.resolve("999999") is None  # 未收录返回 None —— 不是代码
    assert repo.resolve("") is None


def test_resolve_many_is_batched(repo) -> None:
    """>500 个代码必须走分片，且全量返回（不被 SQLite 变量上限截断）。"""
    codes = [f"60{i:04d}" for i in range(1, 601)]
    repo.upsert_many([{"code": c, "name": f"名称{i}"} for i, c in enumerate(codes, start=1)])
    got = repo.resolve_many([*codes, "000000"])
    assert len(got) == 600
    assert got["600001"] == "名称1"
    assert got["600600"] == "名称600"
    assert "000000" not in got


# ---------------------------------------------------------------------------
# display_name —— 名称解析唯一入口
# ---------------------------------------------------------------------------


def test_display_name_never_returns_code(tmp_path: Path, monkeypatch) -> None:
    """未收录时给占位符；stored 等于代码时也必须被识别为「伪名称」。"""
    monkeypatch.setenv("STOCK_PLATFORM_DB_URL", f"sqlite:///{(tmp_path / 's.db').as_posix()}")
    reset_symbol_master_cache()
    try:
        repo = open_symbol_master()
        repo.upsert_many([{"code": "600519", "name": "贵州茅台"}])
        assert display_name("600519") == "贵州茅台"
        assert display_name("999999") == UNKNOWN_NAME
        # 关键回归：库里曾把代码写进 name 列 —— 不能再当名称用
        assert display_name("000801", "000801") == UNKNOWN_NAME
        assert display_name("000801", "") == UNKNOWN_NAME
    finally:
        reset_symbol_master_cache()


def test_display_name_prefers_stored_then_map(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STOCK_PLATFORM_DB_URL", f"sqlite:///{(tmp_path / 's2.db').as_posix()}")
    reset_symbol_master_cache()
    try:
        assert display_name("000801", "四川九洲") == "四川九洲"
        assert display_name("000801", None, name_map={"000801": "别的名字"}) == "别的名字"
        assert display_name("000801", "   ") == UNKNOWN_NAME
    finally:
        reset_symbol_master_cache()


def test_name_map_from_master_backfills_from_engine(tmp_path: Path, monkeypatch) -> None:
    """本地表为空 → 按需从引擎回源一次并落表。"""
    monkeypatch.setenv("STOCK_PLATFORM_DB_URL", f"sqlite:///{(tmp_path / 's3.db').as_posix()}")
    reset_symbol_master_cache()
    engine = _engine_db(tmp_path / "market.db", [("601038", "一拖股份", "sh")])
    try:
        got = name_map_from_master(engine_db=engine)
        assert got == {"601038": "一拖股份"}
        assert open_symbol_master().count() == 1
    finally:
        reset_symbol_master_cache()


def test_name_map_from_master_without_any_source_is_none(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STOCK_PLATFORM_DB_URL", f"sqlite:///{(tmp_path / 's4.db').as_posix()}")
    reset_symbol_master_cache()
    try:
        assert name_map_from_master(engine_db=tmp_path / "missing.db") is None
    finally:
        reset_symbol_master_cache()
