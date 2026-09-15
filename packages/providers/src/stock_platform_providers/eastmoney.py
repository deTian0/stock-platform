"""East Money (eastmoney.com) throttled HTTP entry — the only allowed EM path.

All eastmoney.com traffic in this package MUST go through ``em_get`` /
``EastmoneyClient.get``. Do not call ``requests.get`` / ``urllib`` against
eastmoney hosts directly.
"""

from __future__ import annotations

import os
import random
import threading
import time
from typing import Any, Callable
from urllib.parse import urlparse


class CircuitOpenError(RuntimeError):
    """Raised when EastmoneyClient is in open-circuit cooldown."""

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_EASTMONEY_HOST_SUFFIXES = (
    "eastmoney.com",
    "eastmoney.com.cn",
)

# Substring markers for connection-reset / abort style failures (eastmoney + proxy).
_TRANSIENT_MARKERS = (
    "remotedisconnected",
    "connection aborted",
    "connection reset",
    "broken pipe",
    "temporarily unavailable",
    "timed out",
    "read timed out",
    "max retries exceeded",
)


def is_eastmoney_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == s or host.endswith("." + s) for s in _EASTMONEY_HOST_SUFFIXES)


def assert_eastmoney_url(url: str) -> None:
    if not is_eastmoney_url(url):
        raise ValueError(
            f"em_get only accepts eastmoney.com hosts; got {url!r}. "
            "Non-EM sources must use their own client (not this throttle)."
        )


def _default_min_interval() -> float:
    return float(os.environ.get("EM_MIN_INTERVAL", "1.0"))


def _default_failure_threshold() -> int:
    return int(os.environ.get("EM_CIRCUIT_FAILURES", "5"))


def _default_cooldown_sec() -> float:
    return float(os.environ.get("EM_CIRCUIT_COOLDOWN", "60"))


def _default_http_retries() -> int:
    """Total attempts per GET (1 = no retry). Env ``EM_HTTP_RETRIES`` default 3."""
    return max(1, int(os.environ.get("EM_HTTP_RETRIES", "3")))


def _default_retry_backoff() -> float:
    """Base backoff seconds; attempt n sleeps base * 2**(n-1) + jitter."""
    return float(os.environ.get("EM_HTTP_RETRY_BACKOFF", "0.5"))


def http_trust_env() -> bool:
    """Whether requests should honor HTTP(S)_PROXY env / system proxy.

    Default **False** so a broken local proxy does not silently break live EM calls.
    Set ``STOCK_PLATFORM_HTTP_TRUST_ENV=1`` when an explicit proxy is required.
    """
    raw = str(os.environ.get("STOCK_PLATFORM_HTTP_TRUST_ENV", "0") or "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def is_transient_http_error(exc: BaseException) -> bool:
    """True for connection reset / abort / timeout style errors worth retrying."""
    try:
        from requests.exceptions import (
            ChunkedEncodingError,
            ConnectionError as ReqConnectionError,
            Timeout,
        )
    except ImportError:  # pragma: no cover
        ReqConnectionError = ()  # type: ignore[assignment,misc]
        ChunkedEncodingError = ()  # type: ignore[assignment,misc]
        Timeout = ()  # type: ignore[assignment,misc]

    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    if ReqConnectionError and isinstance(exc, ReqConnectionError):
        return True
    if ChunkedEncodingError and isinstance(exc, ChunkedEncodingError):
        return True
    if Timeout and isinstance(exc, Timeout):
        return True

    name = type(exc).__name__.lower()
    if name in {
        "connectionerror",
        "remotedisconnected",
        "protocolerror",
        "chunkedencodingerror",
        "readtimeout",
        "connecttimeout",
        "timeout",
    }:
        return True

    text = f"{type(exc).__name__}: {exc}".lower()
    return any(m in text for m in _TRANSIENT_MARKERS)


class EastmoneyClient:
    """Serial throttle + Keep-Alive session for eastmoney.com.

    Parameters mirror TradingAgents / a-stock-data ``em_get`` behaviour:
    min interval (env ``EM_MIN_INTERVAL``, default 1.0s) + 0.1–0.5s jitter.

    Transient transport failures (RemoteDisconnected / ConnectionError) are
    retried with backoff (``EM_HTTP_RETRIES`` default 3, ``EM_HTTP_RETRY_BACKOFF``
    default 0.5s). Circuit counts only after all attempts for one GET fail.

    Consecutive transport failures open a cooldown circuit
    (``EM_CIRCUIT_FAILURES`` default 5, ``EM_CIRCUIT_COOLDOWN`` default 60s).
    """

    def __init__(
        self,
        *,
        min_interval: float | None = None,
        session: Any | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
        rng: random.Random | None = None,
        transport: Callable[..., Any] | None = None,
        failure_threshold: int | None = None,
        cooldown_sec: float | None = None,
        http_retries: int | None = None,
        retry_backoff: float | None = None,
    ) -> None:
        self.min_interval = (
            _default_min_interval() if min_interval is None else float(min_interval)
        )
        self.failure_threshold = (
            _default_failure_threshold()
            if failure_threshold is None
            else int(failure_threshold)
        )
        self.cooldown_sec = (
            _default_cooldown_sec() if cooldown_sec is None else float(cooldown_sec)
        )
        self.http_retries = (
            _default_http_retries() if http_retries is None else max(1, int(http_retries))
        )
        self.retry_backoff = (
            _default_retry_backoff()
            if retry_backoff is None
            else max(0.0, float(retry_backoff))
        )
        self._sleeper = sleeper
        self._clock = clock
        self._rng = rng or random.Random()
        self._lock = threading.Lock()
        self._last_call = 0.0
        self._session = session
        self._transport = transport
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0
        self._last_error: str | None = None

    def _ensure_session(self) -> Any:
        if self._session is not None:
            # Re-apply trust_env so env changes after construction still apply.
            try:
                self._session.trust_env = http_trust_env()
            except Exception:  # noqa: BLE001 — custom session stubs may lack attribute
                pass
            return self._session
        try:
            import requests
        except ImportError as exc:  # pragma: no cover - exercised when deps missing
            raise ImportError(
                "eastmoney HTTP requires requests. "
                'Install with: pip install "stock-platform-providers[http]"'
            ) from exc
        session = requests.Session()
        session.trust_env = http_trust_env()
        session.headers.update({"User-Agent": DEFAULT_UA})
        self._session = session
        return session

    def _record_failure(self, exc: BaseException) -> None:
        self._consecutive_failures += 1
        self._last_error = f"{type(exc).__name__}: {exc}"
        if (
            self.failure_threshold > 0
            and self._consecutive_failures >= self.failure_threshold
        ):
            self._circuit_open_until = self._clock() + self.cooldown_sec

    def _one_attempt(
        self,
        url: str,
        *,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
        timeout: float,
        kwargs: dict[str, Any],
    ) -> Any:
        """Throttle + single transport call. Caller owns retry loop."""
        with self._lock:
            now = self._clock()
            if self.failure_threshold > 0 and now < self._circuit_open_until:
                raise CircuitOpenError(
                    "eastmoney circuit open until "
                    f"{self._circuit_open_until:.3f} (last error: {self._last_error})"
                )
            wait = self.min_interval - (now - self._last_call)
            if wait > 0:
                self._sleeper(wait + self._rng.uniform(0.1, 0.5))
            try:
                if self._transport is not None:
                    result = self._transport(
                        url, params=params, headers=headers, timeout=timeout, **kwargs
                    )
                else:
                    session = self._ensure_session()
                    result = session.get(
                        url, params=params, headers=headers, timeout=timeout, **kwargs
                    )
                self._consecutive_failures = 0
                self._circuit_open_until = 0.0
                self._last_error = None
                return result
            except CircuitOpenError:
                raise
            except Exception:
                # Circuit accounting deferred to get() after retries exhaust.
                raise
            finally:
                self._last_call = self._clock()

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 15,
        **kwargs: Any,
    ) -> Any:
        assert_eastmoney_url(url)
        last_exc: BaseException | None = None
        attempts = self.http_retries
        for attempt in range(1, attempts + 1):
            try:
                return self._one_attempt(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout,
                    kwargs=kwargs,
                )
            except CircuitOpenError:
                raise
            except Exception as exc:
                last_exc = exc
                transient = is_transient_http_error(exc)
                if transient and attempt < attempts:
                    # Backoff outside the throttle lock so other callers can proceed.
                    delay = self.retry_backoff * (2 ** (attempt - 1))
                    delay += self._rng.uniform(0.05, 0.25)
                    if delay > 0:
                        self._sleeper(delay)
                    continue
                self._record_failure(exc)
                raise
        assert last_exc is not None
        self._record_failure(last_exc)
        raise last_exc

    def snapshot(self) -> dict[str, Any]:
        """Ops-facing throttle / circuit snapshot (no network)."""
        now = self._clock()
        open_until = self._circuit_open_until
        circuit_open = self.failure_threshold > 0 and now < open_until
        return {
            "minInterval": self.min_interval,
            "failureThreshold": self.failure_threshold,
            "cooldownSec": self.cooldown_sec,
            "httpRetries": self.http_retries,
            "retryBackoff": self.retry_backoff,
            "consecutiveFailures": self._consecutive_failures,
            "circuitOpen": circuit_open,
            "circuitOpenUntil": open_until if circuit_open else None,
            "lastError": self._last_error,
            "httpTrustEnv": http_trust_env(),
        }


_default_client = EastmoneyClient()


def get_default_client() -> EastmoneyClient:
    return _default_client


def reset_default_client(**kwargs: Any) -> EastmoneyClient:
    """Replace the process-wide client (tests / custom interval)."""
    global _default_client
    _default_client = EastmoneyClient(**kwargs)
    return _default_client


def em_get(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 15,
    **kwargs: Any,
) -> Any:
    """Process-wide eastmoney GET — the single throttle entry point."""
    return _default_client.get(
        url, params=params, headers=headers, timeout=timeout, **kwargs
    )
