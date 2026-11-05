"""Minimal paper CLI smoke (SIMULATE only)."""

from __future__ import annotations

from pathlib import Path

from stock_platform_execution.paper_cli import main


def test_paper_cli_demo(tmp_path: Path, capsys) -> None:
    state = tmp_path / "paper.json"
    rc = main(["--state", str(state), "demo"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "liveTradingEnabled" in out
    assert "false" in out.lower() or "False" in out
    assert state.is_file()


def test_paper_cli_status(tmp_path: Path, capsys) -> None:
    state = tmp_path / "paper.json"
    assert main(["--state", str(state), "status"]) == 0
    assert "SIMULATE" in capsys.readouterr().out
