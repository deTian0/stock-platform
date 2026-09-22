"""Optional strategy A/B sidecar on the daily recommend path (M-R5).

Default **off**. Enable with ``STOCK_PLATFORM_STRATEGY_AB=1`` and/or request
flag ``strategyAb=true``. Does **not** replace primary lvrev picks; attaches a
compare summary only. Zero public net in unit tests (caller injects panel).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from .strategy_config import (
    compare_strategy_configs,
    default_strategy_config_dir,
    load_strategy_config,
)

ENV_STRATEGY_AB = "STOCK_PLATFORM_STRATEGY_AB"
ENV_STRATEGY_AB_A = "STOCK_PLATFORM_STRATEGY_AB_A"
ENV_STRATEGY_AB_B = "STOCK_PLATFORM_STRATEGY_AB_B"
DEFAULT_CONFIG_A = "lvrev-default-v1"
DEFAULT_CONFIG_B = "lvrev-rev-heavy-v1"


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def strategy_ab_enabled(*, env: Mapping[str, str] | None = None, request_flag: bool = False) -> bool:
    """True when env opt-in or explicit per-request flag is set."""
    if request_flag:
        return True
    source = env if env is not None else os.environ
    return _truthy(source.get(ENV_STRATEGY_AB))


def strategy_ab_status(*, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = env if env is not None else os.environ
    enabled = strategy_ab_enabled(env=source)
    return {
        "enabled": enabled,
        "defaultOnDailyPath": False,
        "envVar": ENV_STRATEGY_AB,
        "configA": (source.get(ENV_STRATEGY_AB_A) or DEFAULT_CONFIG_A).strip()
        or DEFAULT_CONFIG_A,
        "configB": (source.get(ENV_STRATEGY_AB_B) or DEFAULT_CONFIG_B).strip()
        or DEFAULT_CONFIG_B,
        "note": (
            "默认关闭；设 STOCK_PLATFORM_STRATEGY_AB=1 或请求 strategyAb=true 后，"
            "推荐响应附带 strategyAb 对比摘要，不替换主路径 picks。"
        ),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
    }


def _resolve_config_ref(ref: str) -> Path | Mapping[str, Any]:
    raw = (ref or "").strip()
    root = default_strategy_config_dir()
    candidate = root / f"{raw}.json" if not raw.endswith(".json") else root / Path(raw).name
    if candidate.is_file():
        return candidate
    path = Path(raw)
    if path.is_file():
        return path
    # Allow packaged id without suffix.
    packaged = root / f"{raw}.json"
    if packaged.is_file():
        return packaged
    raise FileNotFoundError(f"strategy config not found: {ref}")


def run_strategy_ab_sidecar(
    panel: pd.DataFrame,
    *,
    config_a: str | None = None,
    config_b: str | None = None,
    panel_source: str = "caller",
    panel_note: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Compare two packaged configs on an injected panel (research sidecar)."""
    source = env if env is not None else os.environ
    a_ref = (config_a or source.get(ENV_STRATEGY_AB_A) or DEFAULT_CONFIG_A).strip()
    b_ref = (config_b or source.get(ENV_STRATEGY_AB_B) or DEFAULT_CONFIG_B).strip()
    a_path = _resolve_config_ref(a_ref)
    b_path = _resolve_config_ref(b_ref)
    # Validate load early for clearer errors.
    load_strategy_config(a_path)
    load_strategy_config(b_path)
    cmp = compare_strategy_configs(panel, a_path, b_path)
    return {
        "ok": True,
        "enabled": True,
        "onDailyPath": True,
        "replacesPicks": False,
        "configA": a_ref,
        "configB": b_ref,
        "winner": cmp.get("winner"),
        "deltaFinalEquity": cmp.get("deltaFinalEquity"),
        "a": {
            "configId": (cmp.get("a") or {}).get("config", {}).get("id"),
            "finalEquity": (cmp.get("a") or {}).get("finalEquity"),
            "tradeCount": (cmp.get("a") or {}).get("tradeCount"),
        },
        "b": {
            "configId": (cmp.get("b") or {}).get("config", {}).get("id"),
            "finalEquity": (cmp.get("b") or {}).get("finalEquity"),
            "tradeCount": (cmp.get("b") or {}).get("tradeCount"),
        },
        "panelSource": panel_source,
        "panelNote": panel_note,
        "compare": cmp,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "disclaimer": (
            "策略 A/B 旁路摘要（M-R5）；默认关闭；不替换主路径 picks；"
            "非投资建议；SIMULATE。"
        ),
    }


def attach_strategy_ab(
    brief: dict[str, Any],
    panel: pd.DataFrame,
    *,
    config_a: str | None = None,
    config_b: str | None = None,
    panel_source: str = "caller",
    panel_note: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Mutate brief with ``strategyAb`` key; return brief."""
    try:
        brief["strategyAb"] = run_strategy_ab_sidecar(
            panel,
            config_a=config_a,
            config_b=config_b,
            panel_source=panel_source,
            panel_note=panel_note,
            env=env,
        )
    except Exception as exc:  # noqa: BLE001 — sidecar must not break recommend
        brief["strategyAb"] = {
            "ok": False,
            "enabled": True,
            "error": f"{type(exc).__name__}: {exc}",
            "replacesPicks": False,
            "environment": "SIMULATE",
            "liveTradingEnabled": False,
            "note": "A/B 旁路失败（fail-visible）；主路径 picks 不受影响。",
        }
    return brief
