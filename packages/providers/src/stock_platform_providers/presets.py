"""Preference presets — production default is CN live; replay for CI/offline."""

from __future__ import annotations

import os
from typing import Any

# Capability ids that CN live HTTP actually serves (matrix-usable on astock_http).
_CN_LIVE_CAPABILITIES: tuple[str, ...] = (
    "daily",
    "realtime",
    "adj_factor",
    "minute",
    "depth5",
    "financial",
    "full_minute",
    "fund_flow",
    "lhb",
    "unlock",
    "sector_fund_flow",
    "news",
)

_REPLAY_PREFS: dict[str, str] = {cap: "replay" for cap in _CN_LIVE_CAPABILITIES}

# Env override for CI / offline (pytest + GitHub Actions). Unset → production CN live.
ENV_PROVIDER_PRESET = "STOCK_PLATFORM_PROVIDER_PRESET"
DEFAULT_STARTUP_PRESET = "cn_astock_http"

PREFERENCE_PRESETS: dict[str, dict[str, Any]] = {
    "replay": {
        "id": "replay",
        "label": "Replay fixtures (offline / CI)",
        "is_default": False,
        "preferences": dict(_REPLAY_PREFS),
        "note": (
            "Force via STOCK_PLATFORM_PROVIDER_PRESET=replay for CI/tests. "
            "Production startup defaults to cn_astock_http."
        ),
    },
    "cn_astock_http": {
        "id": "cn_astock_http",
        "label": "CN live via astock_http (em_get)",
        "is_default": True,
        "preferences": {cap: "astock_http" for cap in _CN_LIVE_CAPABILITIES},
        "note": (
            "Production startup default. Does not enable live trading. "
            "EM traffic still goes through em_get."
        ),
    },
    "us_hk_global_http": {
        "id": "us_hk_global_http",
        "label": "US/HK live via global_http (Yahoo+Sina)",
        "is_default": False,
        "preferences": {
            **_REPLAY_PREFS,
            "daily": "global_http",
            "realtime": "global_http",
        },
        "note": (
            "Apply for US/HK daily/realtime. CN-only datasets stay replay "
            "(global_http has no fund_flow/lhb/…). Does not use em_get."
        ),
    },
}


def list_preference_presets() -> list[dict[str, Any]]:
    return [dict(PREFERENCE_PRESETS[k]) for k in ("replay", "cn_astock_http", "us_hk_global_http")]


def get_preference_preset(preset_id: str) -> dict[str, Any]:
    key = str(preset_id).strip()
    if key not in PREFERENCE_PRESETS:
        raise KeyError(f"unknown preference preset: {preset_id!r}")
    return dict(PREFERENCE_PRESETS[key])


def resolve_startup_preset_id(env: dict[str, str] | None = None) -> str:
    """Resolve which preset workbench starts with.

    ``STOCK_PLATFORM_PROVIDER_PRESET`` wins when set to a known id;
    otherwise production default is ``cn_astock_http``.
    """
    source = env if env is not None else os.environ
    raw = str(source.get(ENV_PROVIDER_PRESET, "") or "").strip()
    if not raw:
        return DEFAULT_STARTUP_PRESET
    if raw not in PREFERENCE_PRESETS:
        raise KeyError(
            f"unknown {ENV_PROVIDER_PRESET}={raw!r}; "
            f"expected one of {sorted(PREFERENCE_PRESETS)}"
        )
    return raw


def startup_preferences(
    preferences: dict[str, str] | None = None,
    *,
    env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build the preference map used at process start.

    Base map comes from ``resolve_startup_preset_id`` (production: cn_astock_http;
    CI: STOCK_PLATFORM_PROVIDER_PRESET=replay). Explicit ``preferences`` overlay on top.
    """
    preset = get_preference_preset(resolve_startup_preset_id(env=env))
    base = dict(preset["preferences"])
    if preferences:
        base.update(dict(preferences))
    return base
