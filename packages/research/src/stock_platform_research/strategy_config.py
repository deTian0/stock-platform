"""Versioned strategy configs + PIT / engine compare helpers.

A ``StrategyConfig`` is the *versioned* description of one research strategy arm:
its factor ``weights``, the ``reversal_q`` cross-section gate, an optional value
factor, **entry-gate knobs** (milestone ``S1``) and (for the light PIT path) a
``universe_ref``. Two configs are the two arms of an A/B run.

``S1`` extends the original M-R5 shape with ``gates`` so a **闸门变更** is
expressible in a config (not only a factor-weight change). ``min_pick_score`` is
the first gate; any other numeric gate can ride in the same mapping. An arm that
names no gate inherits :data:`DEFAULT_MIN_PICK_SCORE`, so an A/B that only moves
weights is still compared against the packaged default floor.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from .lvrev import W_DEFAULT
from .pit import run_pit_long_only

# The screener's score floor (``B1`` / ``S1``). A config that names no gate
# inherits this, so a weights-only A/B arm is still compared on a common floor.
DEFAULT_MIN_PICK_SCORE = 0.80

# Flat aliases accepted in a config JSON; folded into ``gates`` on load.
_GATE_ALIASES = {
    "min_pick_score": "min_pick_score",
    "minPickScore": "min_pick_score",
}


def _parse_gates(data: Mapping[str, Any]) -> dict[str, float]:
    """Collect entry-gate knobs from a ``gates`` mapping plus flat aliases.

    Non-numeric / ``None`` values are skipped rather than coerced to ``0`` — a
    missing gate must fall back to the default, never silently seal every entry.
    """
    out: dict[str, float] = {}
    raw = data.get("gates")
    if isinstance(raw, Mapping):
        for key, value in raw.items():
            if value is None:
                continue
            try:
                out[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
    for alias, name in _GATE_ALIASES.items():
        if name in out:
            continue
        value = data.get(alias)
        if value is None:
            continue
        try:
            out[name] = float(value)
        except (TypeError, ValueError):
            continue
    return out


@dataclass
class StrategyConfig:
    """Versioned research strategy knobs (weights / gates / universe ref)."""

    id: str
    version: str
    top_n: int = 1
    reversal_q: float = 0.30
    value_factor: bool = False
    weights: dict[str, float] = field(default_factory=lambda: dict(W_DEFAULT))
    # ``S1``: entry-gate knobs (e.g. ``min_pick_score``). Empty = inherit defaults.
    gates: dict[str, float] = field(default_factory=dict)
    universe_ref: str | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def min_pick_score(self) -> float:
        """Engine score floor; falls back to :data:`DEFAULT_MIN_PICK_SCORE`."""
        raw = self.gates.get("min_pick_score", DEFAULT_MIN_PICK_SCORE)
        return float(raw)

    def gate(self, name: str, default: float | None = None) -> float | None:
        """Read one gate (``None`` when unset and no ``default`` given)."""
        raw = self.gates.get(name, default)
        return None if raw is None else float(raw)

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
            gates=_parse_gates(data),
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
        # Accept a packaged **bare id** as well as a name / path: ``<id>`` and
        # ``<id>.json`` both resolve against ``strategy_configs/``. (The
        # sidecar / CLI / HTTP routes already resolve bare ids this way; keeping
        # the public loader consistent removes a footgun.)
        root = default_strategy_config_dir()
        for candidate in (root / p.name, root / f"{p.name}.json"):
            if candidate.is_file():
                p = candidate
                break
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
    """Thin wrapper: apply versioned config to ``run_pit_long_only``.

    The light PIT path honours the factor knobs (``top_n`` / ``reversal_q`` /
    ``value_factor`` / ``weights``). Entry-``gates`` are **engine-path** knobs
    (``S1``): the PIT sketch has no score floor, so ``gates`` are echoed in the
    returned ``config`` but not applied here — use
    :func:`strategy_ab.compare_strategy_ab_engine` for a gate-aware compare.
    """
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
    """Compare two configs on the same PIT panel (light, path-agnostic)."""
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
        "disclaimer": (
            "轻量 PIT 策略对比（研究指标）；非投资建议；默认 SIMULATE；"
            "面板来源见 panelSource。"
        ),
    }
