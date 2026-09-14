"""Tests for capability matrix."""

from __future__ import annotations

from stock_platform_providers.capabilities import (
    CAPABILITY_IDS,
    ProviderDeclaration,
    ProviderRegistry,
    build_capability_matrix,
    register_builtin_providers,
    reset_provider_registry,
)


def test_registry_has_nine_capabilities() -> None:
    assert len(CAPABILITY_IDS) == 9
    assert CAPABILITY_IDS[0] == "daily"
    assert CAPABILITY_IDS[6] == "full_minute"
    assert CAPABILITY_IDS[7] == "fund_flow"
    assert CAPABILITY_IDS[8] == "lhb"


def test_build_matrix_replay_usable_for_daily_realtime() -> None:
    reg = reset_provider_registry()
    register_builtin_providers(reg)
    matrix = build_capability_matrix(
        preferences={
            "daily": "replay",
            "realtime": "replay",
            "minute": "replay",
            "fund_flow": "replay",
            "lhb": "replay",
        },
        providers=reg.list(),
    )
    by_id = {row["id"]: row for row in matrix}
    assert by_id["daily"]["usable"] is True
    assert by_id["daily"]["effective"] == "replay"
    assert by_id["realtime"]["usable"] is True
    assert by_id["minute"]["usable"] is False
    assert by_id["minute"]["effective"] is None
    # preferred minute=replay but replay does not offer minute → fail-closed
    assert by_id["minute"]["candidates"] == []
    assert by_id["fund_flow"]["usable"] is True
    assert by_id["fund_flow"]["effective"] == "replay"
    assert any(c["name"] == "astock_http" for c in by_id["fund_flow"]["candidates"])
    assert not any(c["name"] == "global_http" for c in by_id["fund_flow"]["candidates"])
    assert by_id["lhb"]["usable"] is True
    assert by_id["lhb"]["effective"] == "replay"
    assert any(c["name"] == "astock_http" for c in by_id["lhb"]["candidates"])
    assert not any(c["name"] == "global_http" for c in by_id["lhb"]["candidates"])
    assert any(c["name"] == "astock_http" for c in by_id["daily"]["candidates"])
    assert any(c["name"] == "replay" for c in by_id["daily"]["candidates"])
    assert any(c["name"] == "global_http" for c in by_id["daily"]["candidates"])
    assert not any(p["name"] == "global_http" for p in by_id["daily"]["pending"])


def test_unknown_dataset_rejected() -> None:
    reg = ProviderRegistry()
    try:
        reg.register(
            ProviderDeclaration(
                name="bad",
                display="Bad",
                kind="plugin",
                datasets=frozenset({"not_a_cap"}),
            )
        )
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "not_a_cap" in str(exc)


def test_prefer_unavailable_falls_back() -> None:
    reg = ProviderRegistry()
    reg.register(
        ProviderDeclaration(
            name="replay",
            display="Replay",
            kind="builtin",
            datasets=frozenset({"daily"}),
            available=True,
        )
    )
    reg.register(
        ProviderDeclaration(
            name="astock_http",
            display="HTTP",
            kind="builtin",
            datasets=frozenset({"daily"}),
            available=False,
            pending_reason="not ready",
        )
    )
    matrix = build_capability_matrix(
        preferences={"daily": "astock_http"},
        providers=reg.list(),
    )
    daily = matrix[0]
    assert daily["id"] == "daily"
    # preferred not in candidates → fall back to first available
    assert daily["effective"] == "replay"
    assert daily["usable"] is True
