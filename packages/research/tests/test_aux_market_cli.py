"""ADR 0095 — ``stock-platform-aux-market`` CLI (no network)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from stock_platform_providers import aux_market as aux
from stock_platform_research import aux_market_cli


def test_dry_run_is_zero_network_and_creates_no_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "aux" / "aux_market.db"

    def boom(*a: Any, **k: Any) -> Any:
        raise AssertionError("dry-run must not hit the network")

    monkeypatch.setattr(aux, "_em_get_json", boom)
    rc = aux_market_cli.main(
        ["--db", str(db), "--codes", "600519", "--start", "2025-01-01", "--end", "2025-01-31", "--dry-run", "--json"]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dryRun"] is True
    assert out["requests"] == len(aux.DEFAULT_INDICES) + 1
    assert {p["secid"] for p in out["plan"] if p["kind"] == "index"} == set(aux.INDEX_SECIDS.values())
    assert any(p["secid"] == "1.600519" for p in out["plan"])
    assert not db.exists()


def test_sync_through_injected_transport_rejects_wrong_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "aux_market.db"
    names = {"1.000905": ("000905", "中证500"), "1.000300": ("000300", "厦门港务")}

    def fake(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        code, name = names[params["secid"]]
        return {
            "data": {
                "code": code,
                "name": name,
                "klines": ["2025-01-02,1,2,3,0.5,10,100,0,1.0,0,0"],
            }
        }

    monkeypatch.setattr(aux, "_em_get_json", fake)
    rc = aux_market_cli.main(
        ["--db", str(db), "--indices", "000905,000300", "--start", "2025-01-01", "--end", "2025-01-31", "--json"]
    )
    assert rc == 0
    res = json.loads(capsys.readouterr().out)
    by = {r["code"]: r for r in res["results"]}
    assert by["000905"]["status"] == "ok"
    assert by["000300"]["status"] == "rejected"
    assert aux.read_index_closes("000905", "2025-01-01", "2025-01-31", db_path=db) == {"2025-01-02": 2.0}
    assert aux.read_index_closes("000300", "2025-01-01", "2025-01-31", db_path=db) is None


def test_refuses_market_db_name(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = aux_market_cli.main(
        ["--db", str(tmp_path / "market.db"), "--indices", "000905", "--start", "2025-01-01", "--end", "2025-01-31", "--json"]
    )
    assert rc == 0
    res = json.loads(capsys.readouterr().out)
    assert res["ok"] is False and "market.db" in res["error"]
    assert not (tmp_path / "market.db").exists()
