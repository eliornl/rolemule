"""Tests for LLM provider registry and error mapping."""

from unittest.mock import MagicMock, patch

import pytest

from utils.llm.errors import (
    LLMError,
    is_llm_quota_or_rate_limit_exception,
    user_facing_message_from_llm_exception,
)
from utils.llm.providers.anthropic import AnthropicProvider
from utils.llm.providers.gemini import GeminiProvider
from utils.llm.providers.ollama import OllamaProvider
from utils.llm.providers.openai import OpenAIProvider
from utils.llm.registry import create_provider, normalize_provider_name


def test_normalize_provider_name_default() -> None:
    assert normalize_provider_name(None) == "gemini"
    assert normalize_provider_name("") == "gemini"
    assert normalize_provider_name("OpenAI") == "openai"


def test_normalize_provider_name_invalid() -> None:
    with pytest.raises(LLMError, match="Unsupported"):
        normalize_provider_name("cohere")


def test_create_provider_openai() -> None:
    settings = MagicMock(
        openai_api_key=None,
        openai_model="gpt-5.6-luna",
    )
    with patch("utils.llm.providers.openai.get_settings", return_value=settings):
        provider = create_provider("openai")
        assert isinstance(provider, OpenAIProvider)
        assert provider.name == "openai"


def test_create_provider_anthropic() -> None:
    settings = MagicMock(
        anthropic_api_key=None,
        anthropic_model="claude-sonnet-5",
    )
    with patch("utils.llm.providers.anthropic.get_settings", return_value=settings):
        provider = create_provider("anthropic")
        assert isinstance(provider, AnthropicProvider)


def test_create_provider_ollama() -> None:
    settings = MagicMock(
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen3",
    )
    with patch("utils.llm.providers.ollama.get_settings", return_value=settings):
        provider = create_provider("ollama")
        assert isinstance(provider, OllamaProvider)


def test_create_provider_gemini() -> None:
    settings = MagicMock(
        use_vertex_ai=False,
        vertex_ai_project=None,
        vertex_ai_location="us-central1",
        gemini_model="gemini-3.5-flash",
        gemini_api_key=None,
    )
    with patch("utils.llm.providers.gemini.get_settings", return_value=settings):
        provider = create_provider("gemini")
        assert isinstance(provider, GeminiProvider)


def test_openai_quota_user_message() -> None:
    msg = user_facing_message_from_llm_exception(
        RuntimeError("Error code: 429 - insufficient_quota")
    )
    assert "OpenAI" in msg


def test_anthropic_quota_detection() -> None:
    assert is_llm_quota_or_rate_limit_exception(
        RuntimeError("429 rate_limit anthropic")
    )
