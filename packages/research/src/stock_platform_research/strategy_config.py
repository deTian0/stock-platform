"""Versioned strategy configs + PIT compare helper."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from .lvrev import W_DEFAULT
from .pit import run_pit_long_only


@dataclass
class StrategyConfig:
    """Versioned research strategy knobs (weights / gates / universe ref)."""

    id: str
    version: str
    top_n: int = 1
    reversal_q: float = 0.30
    value_factor: bool = False
    weights: dict[str, float] = field(default_factory=lambda: dict(W_DEFAULT))
    universe_ref: str | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> StrategyConfig:
        weights = data.get("weights")
        if weights is None:
            weights = dict(W_DEFAULT)
        return cls(
            id=str(data["id"]),
            version=str(data.get("version") or "1"),
            top_n=int(data.get("top_n") or data.get("topN") or 1),
            reversal_q=float(data.get("reversal_q") or data.get("reversalQ") or 0.30),
            value_factor=bool(data.get("value_factor") or data.get("valueFactor") or False),
            weights={str(k): float(v) for k, v in dict(weights).items()},
            universe_ref=(
                str(data["universe_ref"])
                if data.get("universe_ref") is not None
                else (
                    str(data["universeRef"])
                    if data.get("universeRef") is not None
                    else None
                )
            ),
            description=str(data.get("description") or ""),
        )


def default_strategy_config_dir() -> Path:
    """Packaged strategy_configs directory (editable install)."""
    return Path(__file__).resolve().parent / "strategy_configs"


def load_strategy_config(path: str | Path | Mapping[str, Any]) -> StrategyConfig:
    if isinstance(path, Mapping):
        return StrategyConfig.from_mapping(path)
    p = Path(path)
    if not p.is_file():
        # Try packaged name
        packaged = default_strategy_config_dir() / p.name
        if packaged.is_file():
            p = packaged
        else:
            raise FileNotFoundError(f"strategy config not found: {path}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("strategy config must be a JSON object")
    return StrategyConfig.from_mapping(data)


def list_strategy_configs(directory: str | Path | None = None) -> list[dict[str, Any]]:
    root = Path(directory) if directory else default_strategy_config_dir()
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(root.glob("*.json")):
        cfg = load_strategy_config(p)
        row = cfg.to_dict()
        row["path"] = str(p)
        out.append(row)
    return out


def run_strategy_pit(
    panel: pd.DataFrame,
    config: StrategyConfig | Mapping[str, Any] | str | Path,
) -> dict[str, Any]:
    """Thin wrapper: apply versioned config to ``run_pit_long_only``."""
    cfg = (
        config
        if isinstance(config, StrategyConfig)
        else load_strategy_config(config)
    )
    result = run_pit_long_only(
        panel,
        top_n=cfg.top_n,
        reversal_q=cfg.reversal_q,
        value_factor=cfg.value_factor,
        weights=cfg.weights,
    )
    return {
        "config": cfg.to_dict(),
        "result": result,
        "finalEquity": result["final_equity"],
        "tradeCount": len(result["trades"]),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
    }


def compare_strategy_configs(
    panel: pd.DataFrame,
    config_a: StrategyConfig | Mapping[str, Any] | str | Path,
    config_b: StrategyConfig | Mapping[str, Any] | str | Path,
) -> dict[str, Any]:
    """Compare two configs on the same PIT panel."""
    a = run_strategy_pit(panel, config_a)
    b = run_strategy_pit(panel, config_b)
    eq_a = float(a["finalEquity"])
    eq_b = float(b["finalEquity"])
    return {
        "a": a,
        "b": b,
        "deltaFinalEquity": eq_b - eq_a,
        "winner": (
            a["config"]["id"]
            if eq_a > eq_b
            else b["config"]["id"]
            if eq_b > eq_a
            else "tie"
        ),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "disclaimer": "Light PIT compare on fixture/panel; not investment advice.",
    }
