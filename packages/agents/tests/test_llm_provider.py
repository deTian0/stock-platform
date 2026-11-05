"""LLM provider resolution — no network."""

from __future__ import annotations

import pytest

from stock_platform_agents.llm_provider import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    LlmProviderError,
    chat_completion,
    llm_provider_status,
    normalize_llm_provider,
    resolve_llm_provider,
)


def test_default_provider_is_workbuddy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STOCK_PLATFORM_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("STOCK_PLATFORM_LLM_DEBATE", raising=False)
    cfg = resolve_llm_provider()
    assert cfg.name == "workbuddy"
    assert cfg.in_process is False
    assert cfg.ready is False
    assert any("workbuddy" in r for r in cfg.reasons)


def test_normalize_aliases() -> None:
    assert normalize_llm_provider(None) == "workbuddy"
    assert normalize_llm_provider("ds") == "deepseek"
    assert normalize_llm_provider("oai") == "openai"
    with pytest.raises(LlmProviderError, match="unknown"):
        normalize_llm_provider("anthropic")


def test_deepseek_resolves_deepssek_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCK_PLATFORM_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("STOCK_PLATFORM_LLM_DEBATE", "1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-deepseek")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_VISION_ENABLED", "1")
    monkeypatch.setenv("DEEPSEEK_VISION_MODEL", "deepseek-vl")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("STOCK_PLATFORM_LLM_API_KEY", raising=False)

    cfg = resolve_llm_provider()
    assert cfg.name == "deepseek"
    assert cfg.in_process is True
    assert cfg.api_key == "sk-test-deepseek"
    assert cfg.base_url == "https://api.deepseek.com/v1"
    assert cfg.model == "deepseek-chat"
    assert cfg.vision_enabled is True
    assert cfg.vision_model == "deepseek-vl"
    assert cfg.ready is True

    st = llm_provider_status()
    assert st["provider"] == "deepseek"
    assert st["hasApiKey"] is True
    assert st["model"] == "deepseek-chat"
    assert "sk-test" not in str(st)  # status must not echo raw key material beyond bool


def test_deepseek_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCK_PLATFORM_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("STOCK_PLATFORM_LLM_DEBATE", "1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    cfg = resolve_llm_provider()
    assert cfg.base_url == DEFAULT_DEEPSEEK_BASE_URL
    assert cfg.model == DEFAULT_DEEPSEEK_MODEL


def test_deepseek_ignores_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCK_PLATFORM_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("STOCK_PLATFORM_LLM_DEBATE", "1")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-only")
    cfg = resolve_llm_provider()
    assert cfg.api_key == ""
    assert cfg.ready is False
    assert any("DEEPSEEK_API_KEY" in r for r in cfg.reasons)


def test_openai_provider_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCK_PLATFORM_LLM_PROVIDER", "openai")
    monkeypatch.setenv("STOCK_PLATFORM_LLM_DEBATE", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.openai.compat/v1")
    monkeypatch.setenv("STOCK_PLATFORM_LLM_MODEL", "gpt-test")
    cfg = resolve_llm_provider()
    assert cfg.name == "openai"
    assert cfg.base_url == "https://example.openai.compat/v1"
    assert cfg.model == "gpt-test"
    assert cfg.ready is True


def test_chat_completion_workbuddy_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCK_PLATFORM_LLM_PROVIDER", "workbuddy")
    monkeypatch.setenv("STOCK_PLATFORM_LLM_DEBATE", "1")
    with pytest.raises(LlmProviderError, match="workbuddy"):
        chat_completion("sys", "user")


def test_chat_completion_passes_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("openai")
    monkeypatch.setenv("STOCK_PLATFORM_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("STOCK_PLATFORM_LLM_DEBATE", "1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")

    captured: dict[str, object] = {}

    class _FakeCompletions:
        def create(self, **kwargs):  # noqa: ANN003
            captured["create"] = kwargs

            class _Msg:
                content = '{"ok":true}'

            class _Choice:
                message = _Msg()
                finish_reason = "stop"

            class _Resp:
                choices = [_Choice()]

            return _Resp()

    class _FakeClient:
        def __init__(self, **kwargs):  # noqa: ANN003
            captured["client"] = kwargs
            self.chat = type("C", (), {"completions": _FakeCompletions()})()

    import openai as openai_mod

    monkeypatch.setattr(openai_mod, "OpenAI", _FakeClient)

    content, meta = chat_completion("s", "u")
    assert content.startswith("{")
    assert captured["client"]["api_key"] == "sk-ds"
    assert captured["client"]["base_url"] == "https://api.deepseek.com"
    assert captured["create"]["model"] == "deepseek-chat"
    assert meta["provider"] == "deepseek"
    assert meta["finish_reason"] == "stop"
