"""Preference preset tests (no network)."""

from stock_platform_providers import (
    get_preference_preset,
    list_preference_presets,
)


def test_replay_preset_is_default() -> None:
    presets = {p["id"]: p for p in list_preference_presets()}
    assert presets["replay"]["is_default"] is True
    assert all(v == "replay" for v in presets["replay"]["preferences"].values())
    assert presets["cn_astock_http"]["is_default"] is False
    assert presets["cn_astock_http"]["preferences"]["daily"] == "astock_http"
    assert presets["cn_astock_http"]["preferences"]["full_minute"] == "astock_http"
    assert presets["us_hk_global_http"]["preferences"]["daily"] == "global_http"
    assert presets["us_hk_global_http"]["preferences"]["fund_flow"] == "replay"
    assert presets["us_hk_global_http"]["preferences"]["sector_fund_flow"] == "replay"
    assert presets["us_hk_global_http"]["preferences"]["news"] == "replay"
    assert presets["cn_astock_http"]["preferences"]["sector_fund_flow"] == "astock_http"
    assert presets["cn_astock_http"]["preferences"]["news"] == "astock_http"


def test_unknown_preset() -> None:
    try:
        get_preference_preset("tickflow")
        raise AssertionError("expected KeyError")
    except KeyError:
        pass
