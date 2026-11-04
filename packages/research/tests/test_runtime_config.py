"""Runtime config seed / init CLI — idempotent, fail-closed, never opens live."""

from __future__ import annotations

from pathlib import Path

import pytest

from stock_platform_research.init_cli import main as init_main
from stock_platform_research.runtime_config import (
    read_runtime_config,
    seed_runtime_config,
)


def test_seed_creates_singleton_and_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "platform.db"
    url = f"sqlite:///{db.as_posix()}"
    cfg1, created1 = seed_runtime_config(url)
    assert created1 is True
    assert cfg1.live_trading_enabled is False
    assert cfg1.capital_limit_cny == 10000.0
    assert cfg1.broker_suggestion == "华宝证券"

    cfg2, created2 = seed_runtime_config(url, broker_suggestion="其他券商")
    assert created2 is False
    assert cfg2.broker_suggestion == "华宝证券"  # unchanged without force

    cfg3, created3 = seed_runtime_config(
        url, broker_suggestion="其他券商", force=True
    )
    assert created3 is True
    assert cfg3.broker_suggestion == "其他券商"
    assert cfg3.live_trading_enabled is False


def test_seed_rejects_non_positive_capital(tmp_path: Path) -> None:
    db = tmp_path / "platform.db"
    url = f"sqlite:///{db.as_posix()}"
    with pytest.raises(ValueError):
        seed_runtime_config(url, capital_limit_cny=0)


def test_init_cli_idempotent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "platform.db"
    url = f"sqlite:///{db.as_posix()}"
    assert init_main(["--db-url", url]) == 0
    out1 = capsys.readouterr().out
    assert "created" in out1
    assert init_main(["--db-url", url]) == 0
    out2 = capsys.readouterr().out
    assert "exists" in out2
    cfg = read_runtime_config(url)
    assert cfg is not None
    assert cfg.live_trading_enabled is False
