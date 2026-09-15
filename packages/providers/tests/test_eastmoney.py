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


def test_http_trust_env_default_false(monkeypatch: pytest.MonkeyPatch) -> None:
    from stock_platform_providers.eastmoney import http_trust_env

    monkeypatch.delenv("STOCK_PLATFORM_HTTP_TRUST_ENV", raising=False)
    assert http_trust_env() is False
    monkeypatch.setenv("STOCK_PLATFORM_HTTP_TRUST_ENV", "1")
    assert http_trust_env() is True
    client = reset_default_client(min_interval=0.0, sleeper=lambda _s: None)
    session = client._ensure_session()
    assert session.trust_env is True


def test_transient_connection_abort_retries_then_succeeds() -> None:
    """RemoteDisconnected / ConnectionError: retry with backoff, then succeed."""
    from http.client import RemoteDisconnected

    import requests

    calls: list[int] = []
    sleeps: list[float] = []

    def transport(url, **kwargs):
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            raise requests.exceptions.ConnectionError(
                "Connection aborted.",
                RemoteDisconnected("Remote end closed connection without response"),
            )
        return {"ok": True, "attempt": len(calls)}

    client = EastmoneyClient(
        min_interval=0.0,
        sleeper=lambda s: sleeps.append(s),
        clock=lambda: 1.0,
        rng=__import__("random").Random(0),
        transport=transport,
        http_retries=3,
        retry_backoff=0.1,
        failure_threshold=5,
    )
    out = client.get("https://push2.eastmoney.com/a")
    assert out["ok"] is True
    assert out["attempt"] == 2
    assert len(calls) == 2
    assert any(s >= 0.1 for s in sleeps)  # backoff between attempts
    assert client.snapshot()["consecutiveFailures"] == 0


def test_transient_exhausted_records_circuit_failure() -> None:
    import requests

    def transport(url, **kwargs):
        raise requests.exceptions.ConnectionError("Connection aborted.")

    client = EastmoneyClient(
        min_interval=0.0,
        sleeper=lambda _s: None,
        clock=lambda: 1.0,
        rng=__import__("random").Random(0),
        transport=transport,
        http_retries=2,
        retry_backoff=0.0,
        failure_threshold=1,
        cooldown_sec=30.0,
    )
    with pytest.raises(requests.exceptions.ConnectionError):
        client.get("https://push2.eastmoney.com/a")
    snap = client.snapshot()
    assert snap["consecutiveFailures"] == 1
    assert snap["circuitOpen"] is True
    assert snap["httpTrustEnv"] is False


def test_is_transient_http_error_markers() -> None:
    from http.client import RemoteDisconnected

    from stock_platform_providers.eastmoney import is_transient_http_error

    assert is_transient_http_error(
        ConnectionError(
            (
                "Connection aborted.",
                RemoteDisconnected("Remote end closed connection without response"),
            )
        )
    )
    assert not is_transient_http_error(ValueError("bad json"))


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
        http_retries=1,  # non-transient: one attempt per get
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
