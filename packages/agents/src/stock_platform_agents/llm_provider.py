"""Single-point LLM HTTP provider resolution (ADR 0089).

``STOCK_PLATFORM_LLM_PROVIDER``:

- ``workbuddy`` (default) — in-process commercial LLM is **off**. Data is expected
  from the workbuddy cache / bridge; use WorkBuddy skills out-of-band for chat, or
  switch provider to ``deepseek`` / ``openai`` for in-process calls.
- ``deepseek`` — every in-process LLM call uses ``DEEPSEEK_*`` only.
- ``openai`` — OpenAI-compatible HTTP (``OPENAI_*`` / ``STOCK_PLATFORM_LLM_*``).

Opt-in gate ``STOCK_PLATFORM_LLM_DEBATE=1`` still required for debate / deep-graph.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

from .errors import AgentError

ENV_LLM_PROVIDER = "STOCK_PLATFORM_LLM_PROVIDER"
ENV_LLM_DEBATE = "STOCK_PLATFORM_LLM_DEBATE"

PROVIDER_WORKBUDDY = "workbuddy"
PROVIDER_DEEPSEEK = "deepseek"
PROVIDER_OPENAI = "openai"
KNOWN_PROVIDERS = frozenset(
    {PROVIDER_WORKBUDDY, PROVIDER_DEEPSEEK, PROVIDER_OPENAI}
)

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_DEEPSEEK_VISION_MODEL = "deepseek-vl"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


class LlmProviderError(AgentError):
    """Raised when the configured LLM provider cannot make an in-process call."""


@dataclass(frozen=True)
class LlmProviderConfig:
    """Resolved, ready-to-call (or explicitly not) provider snapshot."""

    name: str
    api_key: str
    base_url: str | None
    model: str
    vision_enabled: bool
    vision_model: str | None
    timeout_s: float | None
    max_tokens: int | None
    debate_opt_in: bool
    in_process: bool
    reasons: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.in_process and self.debate_opt_in and bool(self.api_key) and not self.reasons


def normalize_llm_provider(raw: str | None) -> str:
    name = (raw or PROVIDER_WORKBUDDY).strip().lower() or PROVIDER_WORKBUDDY
    aliases = {
        "wb": PROVIDER_WORKBUDDY,
        "workbuddy_mcp": PROVIDER_WORKBUDDY,
        "ds": PROVIDER_DEEPSEEK,
        "deep-seek": PROVIDER_DEEPSEEK,
        "oai": PROVIDER_OPENAI,
        "openai-compatible": PROVIDER_OPENAI,
    }
    name = aliases.get(name, name)
    if name not in KNOWN_PROVIDERS:
        raise LlmProviderError(
            f"unknown STOCK_PLATFORM_LLM_PROVIDER={raw!r}; "
            f"use one of: {', '.join(sorted(KNOWN_PROVIDERS))}"
        )
    return name


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _env(source: Mapping[str, str] | None, key: str, default: str = "") -> str:
    if source is None:
        return os.environ.get(key, default)
    if key in source:
        return str(source.get(key) or default)
    return default


def _optional_float(raw: str) -> float | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _optional_int(raw: str) -> int | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def resolve_llm_provider(
    *,
    env: Mapping[str, str] | None = None,
) -> LlmProviderConfig:
    """Resolve provider config from env. Never performs network I/O."""
    debate_opt_in = _truthy(_env(env, ENV_LLM_DEBATE))
    try:
        name = normalize_llm_provider(_env(env, ENV_LLM_PROVIDER, PROVIDER_WORKBUDDY))
    except LlmProviderError as exc:
        return LlmProviderConfig(
            name=PROVIDER_WORKBUDDY,
            api_key="",
            base_url=None,
            model="",
            vision_enabled=False,
            vision_model=None,
            timeout_s=None,
            max_tokens=None,
            debate_opt_in=debate_opt_in,
            in_process=False,
            reasons=(str(exc),),
        )

    if name == PROVIDER_WORKBUDDY:
        reasons = [
            "STOCK_PLATFORM_LLM_PROVIDER=workbuddy: in-process LLM disabled; "
            "data path should use --provider workbuddy / "
            "stock-platform-workbuddy-bridge. For in-process chat set "
            "STOCK_PLATFORM_LLM_PROVIDER=deepseek (DEEPSEEK_*) or openai."
        ]
        if not debate_opt_in:
            reasons.insert(0, f"set {ENV_LLM_DEBATE}=1 to opt in")
        return LlmProviderConfig(
            name=name,
            api_key="",
            base_url=None,
            model="",
            vision_enabled=False,
            vision_model=None,
            timeout_s=None,
            max_tokens=None,
            debate_opt_in=debate_opt_in,
            in_process=False,
            reasons=tuple(reasons),
        )

    reasons: list[str] = []
    if not debate_opt_in:
        reasons.append(f"set {ENV_LLM_DEBATE}=1 to opt in")

    if name == PROVIDER_DEEPSEEK:
        api_key = _env(env, "DEEPSEEK_API_KEY").strip()
        base_url = (
            _env(env, "DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL).strip()
            or DEFAULT_DEEPSEEK_BASE_URL
        )
        model = (
            _env(env, "DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL).strip()
            or DEFAULT_DEEPSEEK_MODEL
        )
        vision_enabled = _truthy(_env(env, "DEEPSEEK_VISION_ENABLED"))
        vision_model_raw = _env(
            env, "DEEPSEEK_VISION_MODEL", DEFAULT_DEEPSEEK_VISION_MODEL
        ).strip()
        vision_model = vision_model_raw or DEFAULT_DEEPSEEK_VISION_MODEL
        timeout_s = _optional_float(_env(env, "DEEPSEEK_TIMEOUT"))
        max_tokens = _optional_int(_env(env, "DEEPSEEK_MAX_TOKENS"))
        if not api_key:
            reasons.append("missing DEEPSEEK_API_KEY")
        return LlmProviderConfig(
            name=name,
            api_key=api_key,
            base_url=base_url,
            model=model,
            vision_enabled=vision_enabled,
            vision_model=vision_model if vision_enabled else None,
            timeout_s=timeout_s,
            max_tokens=max_tokens,
            debate_opt_in=debate_opt_in,
            in_process=True,
            reasons=tuple(reasons),
        )

    # openai
    api_key = (
        _env(env, "STOCK_PLATFORM_LLM_API_KEY").strip()
        or _env(env, "OPENAI_API_KEY").strip()
    )
    base_raw = _env(env, "OPENAI_BASE_URL").strip() or _env(
        env, "STOCK_PLATFORM_LLM_BASE_URL"
    ).strip()
    base_url = base_raw or None
    model = (
        _env(env, "STOCK_PLATFORM_LLM_MODEL", DEFAULT_OPENAI_MODEL).strip()
        or DEFAULT_OPENAI_MODEL
    )
    vision_enabled = _truthy(_env(env, "STOCK_PLATFORM_LLM_VISION_ENABLED"))
    vision_model = _env(env, "STOCK_PLATFORM_LLM_VISION_MODEL").strip() or None
    timeout_s = _optional_float(_env(env, "STOCK_PLATFORM_LLM_TIMEOUT"))
    max_tokens = _optional_int(_env(env, "STOCK_PLATFORM_LLM_COMPLETION_MAX_TOKENS"))
    if not api_key:
        reasons.append("missing STOCK_PLATFORM_LLM_API_KEY or OPENAI_API_KEY")
    return LlmProviderConfig(
        name=name,
        api_key=api_key,
        base_url=base_url,
        model=model,
        vision_enabled=vision_enabled,
        vision_model=vision_model if vision_enabled else None,
        timeout_s=timeout_s,
        max_tokens=max_tokens,
        debate_opt_in=debate_opt_in,
        in_process=True,
        reasons=tuple(reasons),
    )


def llm_provider_status(*, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """JSON-shaped status for Workbench / CLI diagnostics (no secrets)."""
    cfg = resolve_llm_provider(env=env)
    openai_ok = False
    openai_err: str | None = None
    try:
        import openai  # noqa: F401

        openai_ok = True
    except Exception as exc:  # noqa: BLE001
        openai_err = f"{type(exc).__name__}: {exc}"

    reasons = list(cfg.reasons)
    if cfg.in_process and not openai_ok:
        reasons.append(
            "openai package missing — pip install 'stock-platform-agents[llm]' "
            f"({openai_err})"
        )

    ready = bool(cfg.ready and openai_ok)
    return {
        "provider": cfg.name,
        "debateOptIn": cfg.debate_opt_in,
        "inProcess": cfg.in_process,
        "hasApiKey": bool(cfg.api_key),
        "baseUrl": cfg.base_url,
        "model": cfg.model or None,
        "visionEnabled": cfg.vision_enabled,
        "visionModel": cfg.vision_model,
        "timeoutSeconds": cfg.timeout_s,
        "completionMaxTokens": cfg.max_tokens,
        "openaiImportOk": openai_ok,
        "ready": ready,
        "reasons": reasons,
        "envProvider": ENV_LLM_PROVIDER,
        "knownProviders": sorted(KNOWN_PROVIDERS),
        "dataHint": (
            "use stock-platform-workbuddy-bridge + --provider workbuddy"
            if cfg.name == PROVIDER_WORKBUDDY
            else None
        ),
    }


def chat_completion(
    system: str,
    user: str,
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Chat Completions call; returns ``(content, response_meta)``.

    Caller applies truncation warnings (keeps this module free of llm_debate imports).
    """
    cfg = resolve_llm_provider(env=env)
    if not cfg.in_process:
        raise LlmProviderError(
            "LLM provider is workbuddy (default): in-process HTTP LLM is off. "
            "Set STOCK_PLATFORM_LLM_PROVIDER=deepseek and DEEPSEEK_API_KEY "
            "(plus STOCK_PLATFORM_LLM_DEBATE=1), or openai + OPENAI_API_KEY."
        )
    if not cfg.debate_opt_in:
        raise LlmProviderError(f"LLM debate disabled; set {ENV_LLM_DEBATE}=1")
    if not cfg.api_key:
        if cfg.name == PROVIDER_DEEPSEEK:
            raise LlmProviderError("missing DEEPSEEK_API_KEY (fail-closed)")
        raise LlmProviderError(
            "missing STOCK_PLATFORM_LLM_API_KEY or OPENAI_API_KEY (fail-closed)"
        )

    try:
        from openai import OpenAI
    except Exception as exc:  # noqa: BLE001
        raise LlmProviderError(
            "openai import failed (fail-closed); "
            "pip install 'stock-platform-agents[llm]'"
        ) from exc

    kwargs: dict[str, Any] = {"api_key": cfg.api_key}
    if cfg.base_url:
        kwargs["base_url"] = cfg.base_url
    if cfg.timeout_s is not None:
        kwargs["timeout"] = cfg.timeout_s
    client = OpenAI(**kwargs)

    create_kwargs: dict[str, Any] = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
    }
    if cfg.max_tokens is not None:
        create_kwargs["max_tokens"] = cfg.max_tokens

    resp = client.chat.completions.create(**create_kwargs)
    meta: dict[str, Any] = {"provider": cfg.name, "model": cfg.model}
    try:
        choice0 = resp.choices[0]
        fr = getattr(choice0, "finish_reason", None)
        if fr is not None:
            meta["finish_reason"] = fr
    except Exception:  # noqa: BLE001
        pass
    content = resp.choices[0].message.content or ""
    if not content.strip():
        raise LlmProviderError("empty LLM response (fail-closed)")
    return content, meta


def chat_text(
    system: str,
    user: str,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    """Chat Completions text-only helper (meta discarded)."""
    content, _meta = chat_completion(system, user, env=env)
    return content


__all__ = [
    "DEFAULT_DEEPSEEK_BASE_URL",
    "DEFAULT_DEEPSEEK_MODEL",
    "DEFAULT_DEEPSEEK_VISION_MODEL",
    "DEFAULT_OPENAI_MODEL",
    "ENV_LLM_DEBATE",
    "ENV_LLM_PROVIDER",
    "KNOWN_PROVIDERS",
    "LlmProviderConfig",
    "LlmProviderError",
    "PROVIDER_DEEPSEEK",
    "PROVIDER_OPENAI",
    "PROVIDER_WORKBUDDY",
    "chat_completion",
    "chat_text",
    "llm_provider_status",
    "normalize_llm_provider",
    "resolve_llm_provider",
]
