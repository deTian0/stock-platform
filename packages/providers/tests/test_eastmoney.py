"""Tests for eastmoney throttle client."""

from __future__ import annotations

import pytest

from stock_platform_providers.eastmoney import (
    EastmoneyClient,
    assert_eastmoney_url,
    em_get,
    is_eastmoney_url,
    reset_default_client,
)


def test_is_eastmoney_url() -> None:
    assert is_eastmoney_url("https://push2.eastmoney.com/api/qt/stock/get")
    assert is_eastmoney_url("https://datacenter-web.eastmoney.com/api/data/v1/get")
    assert not is_eastmoney_url("https://qt.gtimg.cn/q=sh600519")
    assert not is_eastmoney_url("https://evil.com/?q=eastmoney.com")


def test_assert_rejects_non_em() -> None:
    with pytest.raises(ValueError, match="eastmoney.com"):
        assert_eastmoney_url("https://qt.gtimg.cn/q=sh600519")


def test_throttle_sleeps_between_calls() -> None:
    sleeps: list[float] = []
    clock = {"t": 100.0}
    calls: list[str] = []

    def transport(url, **kwargs):
        calls.append(url)
        return {"ok": True, "url": url}

    client = EastmoneyClient(
        min_interval=1.0,
        sleeper=lambda s: sleeps.append(s),
        clock=lambda: clock["t"],
        rng=__import__("random").Random(0),
        transport=transport,
    )

    client.get("https://push2.eastmoney.com/a")
    clock["t"] = 100.2  # only 0.2s later → must sleep ~0.8 + jitter
    client.get("https://push2.eastmoney.com/b")

    assert len(calls) == 2
    assert len(sleeps) == 1
    assert sleeps[0] >= 0.9  # 0.8 remaining + >=0.1 jitter


def test_em_get_uses_default_client() -> None:
    reset_default_client(
        min_interval=0.0,
        sleeper=lambda _s: None,
        transport=lambda url, **kw: {"url": url},
        rng=__import__("random").Random(1),
    )
    out = em_get("https://push2.eastmoney.com/api/qt/stock/get")
    assert out["url"].startswith("https://push2.eastmoney.com")
    with pytest.raises(ValueError):
        em_get("https://example.com/")


def test_circuit_opens_after_consecutive_failures() -> None:
    from stock_platform_providers.eastmoney import CircuitOpenError

    calls: list[str] = []
    clock = {"t": 1.0}

    def transport(url, **kwargs):
        calls.append(url)
        raise RuntimeError("429")

    client = EastmoneyClient(
        min_interval=0.0,
        sleeper=lambda _s: None,
        clock=lambda: clock["t"],
        rng=__import__("random").Random(0),
        transport=transport,
        failure_threshold=2,
        cooldown_sec=30.0,
    )
    with pytest.raises(RuntimeError, match="429"):
        client.get("https://push2.eastmoney.com/a")
    with pytest.raises(RuntimeError, match="429"):
        client.get("https://push2.eastmoney.com/b")
    snap = client.snapshot()
    assert snap["circuitOpen"] is True
    assert snap["consecutiveFailures"] == 2
    with pytest.raises(CircuitOpenError, match="circuit open"):
        client.get("https://push2.eastmoney.com/c")
    assert len(calls) == 2
    clock["t"] = 40.0
    with pytest.raises(RuntimeError, match="429"):
        client.get("https://push2.eastmoney.com/d")
    assert len(calls) == 3
