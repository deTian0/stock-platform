"""Debate CLI — off engine needs no market.db; help always works."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stock_platform_agents.debate_cli import main


def test_debate_cli_help() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_debate_cli_off_no_db(tmp_path: Path, capsys, monkeypatch) -> None:
    # off path still constructs provider today — point at empty so we use off early.
    # Use deterministic with a tiny fake: monkeypatch _provider.
    from stock_platform_agents import debate_cli as mod

    class _P:
        def get_daily(self, *a, **k):
            return []

        def get_realtime(self, *a, **k):
            return []

    monkeypatch.setattr(mod, "_provider", lambda *a, **k: _P())
    out_path = tmp_path / "lane.json"
    rc = main(
        [
            "--engine",
            "off",
            "--symbol",
            "600519",
            "--asof",
            "2026-10-07",
            "--json-out",
            str(out_path),
        ]
    )
    assert rc == 0
    lane = json.loads(out_path.read_text(encoding="utf-8"))
    assert lane["excludedFromPerformance"] is True
    assert lane["engine"] == "off"
    assert lane["liveTradingEnabled"] is False
