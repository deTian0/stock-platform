"""Preference preset tests (no network)."""

from stock_platform_providers import (
    DEFAULT_STARTUP_PRESET,
    get_preference_preset,
    list_preference_presets,
    resolve_startup_preset_id,
    startup_preferences,
)


def test_cn_live_preset_is_default() -> None:
    presets = {p["id"]: p for p in list_preference_presets()}
    assert DEFAULT_STARTUP_PRESET == "cn_astock_http"
    assert presets["cn_astock_http"]["is_default"] is True
    assert presets["replay"]["is_default"] is False
    assert all(v == "astock_http" for v in presets["cn_astock_http"]["preferences"].values())
    assert all(v == "replay" for v in presets["replay"]["preferences"].values())
    assert presets["cn_astock_http"]["preferences"]["daily"] == "astock_http"
    assert presets["cn_astock_http"]["preferences"]["full_minute"] == "astock_http"
    assert presets["us_hk_global_http"]["preferences"]["daily"] == "global_http"
    assert presets["us_hk_global_http"]["preferences"]["fund_flow"] == "replay"
    assert presets["us_hk_global_http"]["preferences"]["sector_fund_flow"] == "replay"
    assert presets["us_hk_global_http"]["preferences"]["news"] == "replay"
    assert presets["cn_astock_http"]["preferences"]["sector_fund_flow"] == "astock_http"
    assert presets["cn_astock_http"]["preferences"]["news"] == "astock_http"
    assert presets["cn_astock_http"]["preferences"]["concept_blocks"] == "astock_http"
    assert presets["us_hk_global_http"]["preferences"]["concept_blocks"] == "replay"
    assert "cn_tushare_http" in presets
    assert presets["cn_tushare_http"]["is_default"] is False
    assert presets["cn_tushare_http"]["preferences"]["daily"] == "tushare_http"
    assert presets["cn_tushare_http"]["preferences"]["fund_flow"] == "astock_http"


def test_startup_preferences_env_replay() -> None:
    assert resolve_startup_preset_id(env={}) == "cn_astock_http"
    assert resolve_startup_preset_id(env={"STOCK_PLATFORM_PROVIDER_PRESET": "replay"}) == "replay"
    prefs = startup_preferences(env={"STOCK_PLATFORM_PROVIDER_PRESET": "replay"})
    assert prefs["daily"] == "replay"
    assert prefs["news"] == "replay"
    live = startup_preferences(env={})
    assert live["daily"] == "astock_http"
    assert live["concept_blocks"] == "astock_http"
    overlay = startup_preferences({"daily": "global_http"}, env={})
    assert overlay["daily"] == "global_http"
    assert overlay["fund_flow"] == "astock_http"


def test_unknown_preset() -> None:
    try:
        get_preference_preset("tickflow")
        raise AssertionError("expected KeyError")
    except KeyError:
        pass
