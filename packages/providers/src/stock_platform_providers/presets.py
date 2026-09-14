"""CLI: apply documented live preference presets (never the process default)."""

from __future__ import annotations

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

PREFERENCE_PRESETS: dict[str, dict[str, Any]] = {
    "replay": {
        "id": "replay",
        "label": "Default replay (offline / CI)",
        "is_default": True,
        "preferences": dict(_REPLAY_PREFS),
        "note": "Process startup and CI stay on this map. Live presets are opt-in.",
    },
    "cn_astock_http": {
        "id": "cn_astock_http",
        "label": "CN live via astock_http (em_get)",
        "is_default": False,
        "preferences": {cap: "astock_http" for cap in _CN_LIVE_CAPABILITIES},
        "note": "Does not enable paper live trading. EM traffic still goes through em_get.",
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
        "note": "CN-only datasets stay replay. global_http does not use em_get.",
    },
}


def list_preference_presets() -> list[dict[str, Any]]:
    return [dict(PREFERENCE_PRESETS[k]) for k in ("replay", "cn_astock_http", "us_hk_global_http")]


def get_preference_preset(preset_id: str) -> dict[str, Any]:
    key = str(preset_id).strip()
    if key not in PREFERENCE_PRESETS:
        raise KeyError(f"unknown preference preset: {preset_id!r}")
    return dict(PREFERENCE_PRESETS[key])
