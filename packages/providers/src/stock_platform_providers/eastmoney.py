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

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_EASTMONEY_HOST_SUFFIXES = (
    "eastmoney.com",
    "eastmoney.com.cn",
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


class EastmoneyClient:
    """Serial throttle + Keep-Alive session for eastmoney.com.

    Parameters mirror TradingAgents / a-stock-data ``em_get`` behaviour:
    min interval (env ``EM_MIN_INTERVAL``, default 1.0s) + 0.1–0.5s jitter.
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
    ) -> None:
        self.min_interval = (
            _default_min_interval() if min_interval is None else float(min_interval)
        )
        self._sleeper = sleeper
        self._clock = clock
        self._rng = rng or random.Random()
        self._lock = threading.Lock()
        self._last_call = 0.0
        self._session = session
        self._transport = transport

    def _ensure_session(self) -> Any:
        if self._session is not None:
            return self._session
        try:
            import requests
        except ImportError as exc:  # pragma: no cover - exercised when deps missing
            raise ImportError(
                "eastmoney HTTP requires requests. "
                'Install with: pip install "stock-platform-providers[http]"'
            ) from exc
        session = requests.Session()
        session.headers.update({"User-Agent": DEFAULT_UA})
        self._session = session
        return session

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 15,
        **kwargs: Any,
    ) -> Any:
        assert_eastmoney_url(url)
        with self._lock:
            wait = self.min_interval - (self._clock() - self._last_call)
            if wait > 0:
                self._sleeper(wait + self._rng.uniform(0.1, 0.5))
            try:
                if self._transport is not None:
                    return self._transport(
                        url, params=params, headers=headers, timeout=timeout, **kwargs
                    )
                session = self._ensure_session()
                return session.get(
                    url, params=params, headers=headers, timeout=timeout, **kwargs
                )
            finally:
                self._last_call = self._clock()


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
