"""Shadow backtest benchmark goes through the F1 single point and fails closed."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from stock_platform_research.benchmark import ENV_BENCHMARK_SYMBOL
from stock_platform_research.shadow_board.backtest import (
    compare_shadow_vs_lvrev,
    prepare_shadow_frame,
    render_shadow_backtest_markdown,
)
from stock_platform_research.shadow_board.cli import resolve_backtest_benchmark

from test_shadow_board_backtest import _bars, _industry, _names  # type: ignore[import-not-found]


def _db(tmp_path: Path, rows: list[tuple[str, str, float]]) -> str:
    path = tmp_path / "market.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE daily_price (code TEXT, date TEXT, close REAL, pct_chg REAL, vol REAL, amount REAL)")
    con.executemany("INSERT INTO daily_price (code, date, close) VALUES (?, ?, ?)", rows)
    con.commit()
    con.close()
    return str(path)


@pytest.fixture(autouse=True)
def _default_bench(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_BENCHMARK_SYMBOL, raising=False)


def test_stock_collision_fails_closed_even_if_rows_exist(tmp_path: Path) -> None:
    # 000905.SZ in the engine DB is the stock 厦门港务, not 中证500.
    db = _db(tmp_path, [("000905.SZ", "2025-01-02", 5.0), ("000905.SZ", "2025-06-30", 6.0)])
    closes, block = resolve_backtest_benchmark(db, "2025-01-01", "2025-12-31", names={"000905": "厦门港务"})
    assert closes is None
    assert block["identityOk"] is False
    assert "厦门港务" in block["reason"]


def test_index_identity_ok_but_no_rows(tmp_path: Path) -> None:
    db = _db(tmp_path, [])
    closes, block = resolve_backtest_benchmark(db, "2025-01-01", "2025-12-31", names={"000905": "中证500"})
    assert closes is None
    assert block["identityOk"] is True
    assert "无" in block["reason"] and block["engineCode"] in block["reason"]


def test_index_identity_ok_with_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_BENCHMARK_SYMBOL, "000300")
    from stock_platform_research.benchmark import engine_benchmark_code

    code = engine_benchmark_code("000300")
    db = _db(tmp_path, [(code, "2025-01-02", 100.0), (code, "2025-06-30", 110.0)])
    closes, block = resolve_backtest_benchmark(db, "2025-01-01", "2025-12-31", names={"000300": "沪深300"})
    assert closes == {"2025-01-02": 100.0, "2025-06-30": 110.0}
    assert "reason" not in block


def test_unavailable_benchmark_is_explicit_in_payload_and_report() -> None:
    feats = prepare_shadow_frame(_bars(), industry_map=_industry())
    out = compare_shadow_vs_lvrev(
        feats,
        name_map=_names(),
        benchmark={"symbol": "000905", "engineCode": "000905.SZ", "reason": "身份碰撞：厦门港务"},
    )
    assert out["benchmark"]["available"] is False
    assert out["benchmark"]["reason"] == "身份碰撞：厦门港务"
    for arm in ("lvrev", "shadow"):
        assert out[arm]["excessReturn"] is None
        assert out[arm]["excessAvailable"] is False
    assert any("超额不可用" in x and "厦门港务" in x for x in out["limitations"])
    md = render_shadow_backtest_markdown(out)
    assert "| 超额 | 不可用 | 不可用 |" in md
    assert "超额不可用" in md


def test_available_benchmark_computes_excess() -> None:
    feats = prepare_shadow_frame(_bars(), industry_map=_industry())
    dates = sorted({d.date().isoformat() for d in feats["trade_date"]})
    out = compare_shadow_vs_lvrev(
        feats,
        name_map=_names(),
        index_close={d: 100.0 + i for i, d in enumerate(dates)},
        benchmark={"symbol": "000300", "engineCode": "000300.SH", "name": "沪深300"},
    )
    assert out["benchmark"]["available"] is True and out["benchmark"]["reason"] is None
    assert out["shadow"]["excessAvailable"] is True
    assert not any("超额不可用" in x for x in out["limitations"])
