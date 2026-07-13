"""Tests for utils.llm.availability helpers."""

from unittest.mock import MagicMock, patch

from utils.llm.availability import (
    active_llm_provider,
    effective_user_api_key,
    llm_credentials_available,
    server_has_llm_credentials,
)


def test_server_has_llm_gemini_vertex() -> None:
    s = MagicMock(
        llm_provider="gemini",
        gemini_api_key=None,
        use_vertex_ai=True,
    )
    assert server_has_llm_credentials(s) is True


def test_server_has_llm_openai() -> None:
    s = MagicMock(llm_provider="openai", openai_api_key="sk-x")
    assert server_has_llm_credentials(s) is True
    s2 = MagicMock(llm_provider="openai", openai_api_key=None)
    assert server_has_llm_credentials(s2) is False


def test_effective_user_api_key_gemini_only() -> None:
    with patch(
        "utils.llm.availability.active_llm_provider", return_value="openai"
    ):
        assert effective_user_api_key("gemini-key") is None
    with patch(
        "utils.llm.availability.active_llm_provider", return_value="gemini"
    ):
        assert effective_user_api_key("gemini-key") == "gemini-key"


def test_llm_credentials_available_byok_gemini() -> None:
    s = MagicMock(
        llm_provider="gemini",
        gemini_api_key=None,
        use_vertex_ai=False,
    )
    assert llm_credentials_available("user-key", settings=s) is True
    assert llm_credentials_available(None, settings=s) is False


def test_active_llm_provider() -> None:
    s = MagicMock(llm_provider="Anthropic")
    assert active_llm_provider(s) == "anthropic"


def test_ollama_always_server_ready() -> None:
    s = MagicMock(llm_provider="ollama", ollama_base_url="http://127.0.0.1:11434")
    assert server_has_llm_credentials(s) is True
