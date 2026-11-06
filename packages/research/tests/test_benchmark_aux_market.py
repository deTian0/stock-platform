"""ADR 0095 — benchmark closes fall back to the verified aux store; absent store ⇒ bit-identical."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from stock_platform_providers.aux_market import ENV_AUX_MARKET_DB, INDEX_SECIDS, sync_aux_market
from stock_platform_research.benchmark import (
    ENV_BENCHMARK_SYMBOL,
    aux_index_name_hints,
    load_benchmark_closes,
    resolve_benchmark_identity,
    resolve_benchmark_symbol,
)
from stock_platform_research.shadow_board.cli import resolve_backtest_benchmark


def _market_db(tmp_path: Path, rows: list[tuple[str, str, float]]) -> str:
    path = tmp_path / "market.db"
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE daily_price (code TEXT, date TEXT, close REAL, pct_chg REAL, vol REAL, amount REAL)"
    )
    con.executemany("INSERT INTO daily_price (code, date, close) VALUES (?, ?, ?)", rows)
    con.commit()
    con.close()
    return str(path)


def _legacy_resolve(db: str, start: str, end: str, *, names: dict[str, str] | None):
    """Verbatim copy of the pre-ADR-0095 ``resolve_backtest_benchmark`` body."""
    bench = resolve_benchmark_symbol()
    ident = resolve_benchmark_identity(bench, names=names or {})
    block: dict[str, Any] = {
        "symbol": ident.get("symbol"),
        "engineCode": ident.get("engineCode"),
        "name": ident.get("name"),
        "identityChecked": bool(ident.get("checked")),
        "identityOk": bool(ident.get("ok")),
    }
    if not ident.get("alphaAvailable", True):
        block["reason"] = str(ident.get("warning") or "基准身份校验未通过")
        return None, block
    uri = "file:%s?mode=ro" % str(db).replace("\\", "/")
    con = sqlite3.connect(uri, uri=True)
    try:
        rows = con.execute(
            "SELECT date, close FROM daily_price WHERE code=? AND date>=? AND date<=?",
            (str(ident.get("engineCode")), start, end),
        ).fetchall()
    finally:
        con.close()
    closes = {str(d)[:10]: float(c) for d, c in rows if c is not None}
    if not closes:
        block["reason"] = f"market.db daily_price 无 `{ident.get('engineCode')}` 行（{start}~{end}）"
        return None, block
    return closes, block


def _fake_index_transport(name_by_code: dict[str, str]):
    secid_to_code = {v: k for k, v in INDEX_SECIDS.items()}

    def get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        code = secid_to_code[str((params or {})["secid"])]
        return {
            "data": {
                "code": code,
                "name": name_by_code[code],
                "klines": [
                    "2025-01-02,100.0,100.0,101.0,99.0,1000,100000,0,1.0,0,0",
                    "2025-06-30,108.0,110.0,111.0,107.0,1000,100000,0,1.5,0,0",
                ],
            }
        }

    return get_json


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.delenv(ENV_BENCHMARK_SYMBOL, raising=False)
    aux = tmp_path / "aux" / "aux_market.db"
    monkeypatch.setenv(ENV_AUX_MARKET_DB, str(aux))
    return aux


CASES = [
    ([("000905.SZ", "2025-01-02", 5.0), ("000905.SZ", "2025-06-30", 6.0)], {"000905": "厦门港务"}),
    ([], {"000905": "中证500"}),
    ([("000905.SZ", "2025-01-02", 5.0)], {"000905": "中证500"}),
    ([], {}),
]


@pytest.mark.parametrize("rows,names", CASES)
def test_no_aux_store_bit_identical_to_legacy(tmp_path: Path, rows, names, _env: Path) -> None:
    assert not _env.exists()
    db = _market_db(tmp_path, rows)
    legacy = _legacy_resolve(db, "2025-01-01", "2025-12-31", names=names)
    assert load_benchmark_closes(db, "2025-01-01", "2025-12-31", names=names) == legacy
    assert resolve_backtest_benchmark(db, "2025-01-01", "2025-12-31", names=names) == legacy
    assert not _env.exists()  # read side never creates the store


def test_aux_fallback_on_stock_collision(tmp_path: Path, _env: Path) -> None:
    res = sync_aux_market(
        indices=["000905"],
        start=date(2025, 1, 1),
        end=date(2025, 12, 31),
        name_hints=aux_index_name_hints(),
        get_json=_fake_index_transport({"000905": "中证500"}),
        daily_budget=10,
    )
    assert res["ok"] is True
    db = _market_db(tmp_path, [("000905.SZ", "2025-01-02", 5.0), ("000905.SZ", "2025-06-30", 6.0)])
    closes, block = resolve_backtest_benchmark(db, "2025-01-01", "2025-12-31", names={"000905": "厦门港务"})
    assert closes == {"2025-01-02": 100.0, "2025-06-30": 110.0}  # index, not the 厦门港务 stock
    assert block["source"] == "aux_market"
    assert block["identityOk"] is True
    assert block["auxName"] == "中证500"
    assert "厦门港务" in block["marketDbReason"]
    assert "reason" not in block


def test_market_db_rows_win_over_aux(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_BENCHMARK_SYMBOL, "000300")
    sync_aux_market(
        indices=["000300"],
        start=date(2025, 1, 1),
        end=date(2025, 12, 31),
        name_hints=aux_index_name_hints(),
        get_json=_fake_index_transport({"000300": "沪深300"}),
        daily_budget=10,
    )
    db = _market_db(tmp_path, [("000300.SZ", "2025-01-02", 3000.0), ("000300.SZ", "2025-06-30", 3100.0)])
    closes, block = load_benchmark_closes(db, "2025-01-01", "2025-12-31", names={"000300": "沪深300"})
    assert closes == {"2025-01-02": 3000.0, "2025-06-30": 3100.0}
    assert "source" not in block


def test_aux_meta_with_wrong_name_is_ignored(tmp_path: Path, _env: Path) -> None:
    """Tampered / stale meta that no longer matches aliases is never read."""
    sync_aux_market(
        indices=["000905"],
        start=date(2025, 1, 1),
        end=date(2025, 12, 31),
        name_hints=aux_index_name_hints(),
        get_json=_fake_index_transport({"000905": "中证500"}),
        daily_budget=10,
    )
    con = sqlite3.connect(_env)
    con.execute("UPDATE index_meta SET name='厦门港务' WHERE code='000905'")
    con.commit()
    con.close()
    db = _market_db(tmp_path, [])
    closes, block = load_benchmark_closes(db, "2025-01-01", "2025-12-31", names={"000905": "厦门港务"})
    assert closes is None
    assert "厦门港务" in block["reason"]


def test_resolve_identity_unchanged_by_aux_store(tmp_path: Path) -> None:
    sync_aux_market(
        indices=["000905"],
        start=date(2025, 1, 1),
        end=date(2025, 12, 31),
        name_hints=aux_index_name_hints(),
        get_json=_fake_index_transport({"000905": "中证500"}),
        daily_budget=10,
    )
    ident = resolve_benchmark_identity("000905", names={"000905": "厦门港务"})
    assert ident["alphaAvailable"] is False  # live settle chains stay fail-closed


def test_lvrev_enhancement_excess_only_when_benchmark_given() -> None:
    """No benchmark args ⇒ payload keys unchanged; with an index series ⇒ excess block computed."""
    from test_lvrev_enhancement import _bars, _industry, _names  # type: ignore[import-not-found]

    from stock_platform_research.lvrev_enhancement import compare_lvrev_enhancements
    from stock_platform_research.shadow_board.backtest import prepare_shadow_frame

    feats = prepare_shadow_frame(_bars(), industry_map=_industry())
    base = compare_lvrev_enhancements(feats, variants=["trail_tp"], name_map=_names(), run_y1=False)
    assert base["excessAvailable"] is False
    assert "excess" not in base and "benchmark" not in base

    dates = sorted({d.date().isoformat() for d in feats["trade_date"]})
    closes = {d: 100.0 + i * 0.1 for i, d in enumerate(dates)}
    out = compare_lvrev_enhancements(
        feats,
        variants=["trail_tp"],
        name_map=_names(),
        run_y1=False,
        index_close=closes,
        benchmark={"symbol": "000905", "source": "aux_market"},
    )
    assert out["excessAvailable"] is True
    ex = out["excess"]
    assert ex["benchmarkReturn"] == pytest.approx(closes[ex["end"]] / closes[ex["start"]] - 1)
    for arm in ("baseline", "trail_tp"):
        a = ex["arms"][arm]
        assert a["excessReturn"] == pytest.approx(a["totalReturn"] - ex["benchmarkReturn"])
    # Criteria untouched by the benchmark
    assert out["comparisons"]["trail_tp"]["criteria"] == base["comparisons"]["trail_tp"]["criteria"]
