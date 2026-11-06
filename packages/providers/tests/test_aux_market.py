"""ADR 0095 — aux_market store: fake transport only (no network)."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from stock_platform_providers.aux_market import (
    INDEX_SECIDS,
    plan_aux_sync,
    read_index_closes,
    read_index_meta,
    read_ohlc,
    sync_aux_market,
)

HINTS = {
    "000905": ("中证500",),
    "000300": ("沪深300",),
    "399006": ("创业板指",),
}
START = date(2025, 1, 1)
END = date(2025, 1, 31)


def _kl(d: str, close: float, pct: float) -> str:
    # date,open,close,high,low,vol,amount,amplitude,pct(%),change,turnover
    return f"{d},{close - 1},{close},{close + 2},{close - 2},1000,2000000.0,1.0,{pct},0.1,0.5"


def _fake(payloads: dict[str, dict], calls: list[str] | None = None):
    def get_json(url, params=None):
        secid = params["secid"]
        if calls is not None:
            calls.append(secid)
        if secid not in payloads:
            raise ConnectionError(f"no fixture for {secid}")
        return payloads[secid]

    return get_json


def _index_payload(code: str, name: str) -> dict:
    return {
        "data": {
            "code": code,
            "name": name,
            "klines": [_kl("2025-01-02", 100.0, 1.5), _kl("2025-01-03", 101.0, 1.0)],
        }
    }


def test_index_secids_use_index_table_not_stock_rule() -> None:
    assert INDEX_SECIDS["000905"] == "1.000905"  # stock 厦门港务 would be 0.000905
    assert INDEX_SECIDS["399006"] == "0.399006"


def test_index_written_when_name_matches(tmp_path: Path) -> None:
    db = tmp_path / "aux.db"
    calls: list[str] = []
    out = sync_aux_market(
        indices=["000905"],
        start=START,
        end=END,
        name_hints=HINTS,
        db_path=db,
        get_json=_fake({"1.000905": _index_payload("000905", "中证500")}, calls),
        today=date(2026, 11, 6),
    )
    assert out["ok"] is True
    assert calls == ["1.000905"]
    r = out["results"][0]
    assert r["status"] == "ok" and r["rows"] == 2 and r["hint"] == "中证500"
    closes = read_index_closes("000905", "2025-01-01", "2025-01-31", db_path=db)
    assert closes == {"2025-01-02": 100.0, "2025-01-03": 101.0}
    meta = read_index_meta("000905", db_path=db)
    assert meta and meta["name"] == "中证500" and meta["secid"] == "1.000905"
    con = sqlite3.connect(db)
    pct = con.execute("SELECT pct_chg FROM index_daily WHERE date='2025-01-02'").fetchone()[0]
    con.close()
    assert pct == pytest.approx(0.015)  # decimal, not percent


def test_name_mismatch_rejected_and_logged(tmp_path: Path) -> None:
    db = tmp_path / "aux.db"
    out = sync_aux_market(
        indices=["000905"],
        start=START,
        end=END,
        name_hints=HINTS,
        db_path=db,
        get_json=_fake({"1.000905": _index_payload("000905", "厦门港务")}),
    )
    r = out["results"][0]
    assert out["ok"] is False
    assert r["status"] == "rejected" and "厦门港务" in r["reason"]
    assert read_index_closes("000905", "2025-01-01", "2025-01-31", db_path=db) is None
    con = sqlite3.connect(db)
    log = con.execute("SELECT status, reason FROM fetch_log").fetchall()
    con.close()
    assert log[0][0] == "rejected" and "厦门港务" in log[0][1]


def test_missing_name_or_hints_fail_closed(tmp_path: Path) -> None:
    db = tmp_path / "aux.db"
    no_name = {"data": {"code": "000300", "klines": [_kl("2025-01-02", 1.0, 0.1)]}}
    out = sync_aux_market(
        indices=["000300", "000852", "999999"],
        start=START,
        end=END,
        name_hints=HINTS,  # 000852 has no hints here
        db_path=db,
        get_json=_fake({"1.000300": no_name}),
    )
    st = {r["code"]: r["status"] for r in out["results"]}
    assert st == {"000300": "rejected", "000852": "rejected", "999999": "rejected"}
    assert read_index_closes("000300", "2025-01-01", "2025-01-31", db_path=db) is None


def test_budget_exceeded_skips_remaining_and_persists(tmp_path: Path) -> None:
    db = tmp_path / "aux.db"
    payloads = {
        "1.000905": _index_payload("000905", "中证500"),
        "1.000300": _index_payload("000300", "沪深300"),
        "0.399006": _index_payload("399006", "创业板指"),
    }
    calls: list[str] = []
    day = date(2026, 11, 6)
    out = sync_aux_market(
        indices=["000905", "000300", "399006"],
        start=START, end=END, name_hints=HINTS, db_path=db,
        get_json=_fake(payloads, calls), daily_budget=2, today=day,
    )
    st = [r["status"] for r in out["results"]]
    assert st == ["ok", "ok", "budget_exceeded"]
    assert calls == ["1.000905", "1.000300"]
    assert out["budget"]["exceeded"] is True and out["budget"]["usedToday"] == 2
    # Same day rerun: ledger carries over → zero network.
    calls.clear()
    again = sync_aux_market(
        indices=["399006"], start=START, end=END, name_hints=HINTS, db_path=db,
        get_json=_fake(payloads, calls), daily_budget=2, today=day,
    )
    assert calls == []
    assert again["results"][0]["status"] == "budget_exceeded"


def test_idempotent_upsert(tmp_path: Path) -> None:
    db = tmp_path / "aux.db"
    fake = _fake({"1.000905": _index_payload("000905", "中证500")})
    for _ in range(3):
        sync_aux_market(indices=["000905"], start=START, end=END, name_hints=HINTS, db_path=db, get_json=fake)
    con = sqlite3.connect(db)
    n = con.execute("SELECT COUNT(*) FROM index_daily").fetchone()[0]
    con.close()
    assert n == 2


def test_fail_soft_transport_error_never_raises(tmp_path: Path) -> None:
    db = tmp_path / "aux.db"
    out = sync_aux_market(
        indices=["000905"], codes=["600519"], start=START, end=END,
        name_hints=HINTS, db_path=db, get_json=_fake({}),
    )
    assert [r["status"] for r in out["results"]] == ["failed", "failed"]


def test_stock_ohlc_explicit_codes_and_code_check(tmp_path: Path) -> None:
    db = tmp_path / "aux.db"
    payloads = {
        "1.600519": {"data": {"code": "600519", "name": "贵州茅台", "klines": [_kl("2025-01-02", 1500.0, 0.5)]}},
        "0.000001": {"data": {"code": "000002", "name": "万科A", "klines": [_kl("2025-01-02", 10.0, 0.5)]}},
    }
    out = sync_aux_market(
        codes=["SH600519", "000001"], start=START, end=END,
        name_hints=None, db_path=db, get_json=_fake(payloads),
    )
    st = {r["code"]: r["status"] for r in out["results"]}
    assert st == {"600519.SH": "ok", "000001.SZ": "rejected"}
    rows = read_ohlc("600519", "2025-01-01", "2025-01-31", db_path=db)
    assert rows and rows[0]["open"] == 1499.0 and rows[0]["high"] == 1502.0 and rows[0]["low"] == 1498.0


def test_refuses_market_db_as_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = sync_aux_market(indices=["000905"], start=START, end=END, name_hints=HINTS,
                          db_path=tmp_path / "market.db", get_json=_fake({}))
    assert out["ok"] is False and "market.db" in out["error"]
    assert not (tmp_path / "market.db").exists()
    eng = tmp_path / "engine.db"
    monkeypatch.setenv("STOCK_PLATFORM_ENGINE_MARKET_DB", str(eng))
    out2 = sync_aux_market(indices=["000905"], start=START, end=END, name_hints=HINTS,
                           db_path=eng, get_json=_fake({}))
    assert out2["ok"] is False and not eng.exists()


def test_read_side_missing_store_returns_none(tmp_path: Path) -> None:
    db = tmp_path / "nope.db"
    assert read_index_closes("000905", "2025-01-01", "2025-12-31", db_path=db) is None
    assert read_index_meta("000905", db_path=db) is None
    assert read_ohlc("600519", "2025-01-01", "2025-12-31", db_path=db) is None
    assert not db.exists()


def test_plan_is_offline() -> None:
    plan = plan_aux_sync(indices=["000905", "123456"], codes=["600519", "bad"], start=START, end=END)
    assert [p["supported"] for p in plan] == [True, False, True, False]
    assert plan[0]["secid"] == "1.000905" and plan[2]["secid"] == "1.600519"
