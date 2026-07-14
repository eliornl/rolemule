"""Tests for utils.llm.availability helpers (per-user BYOK model)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from utils.llm.availability import (
    active_llm_provider,
    llm_credentials_available,
    resolve_user_llm_context,
    server_has_llm_credentials,
    user_has_key_for_provider,
)


def test_server_has_llm_only_vertex() -> None:
    assert server_has_llm_credentials(MagicMock(use_vertex_ai=True)) is True
    assert server_has_llm_credentials(MagicMock(use_vertex_ai=False)) is False


def test_active_llm_provider() -> None:
    s = MagicMock(llm_provider="Anthropic")
    assert active_llm_provider(s) == "anthropic"


def test_resolve_requires_provider() -> None:
    user = SimpleNamespace(
        gemini_api_key_encrypted=None,
        openai_api_key_encrypted=None,
        anthropic_api_key_encrypted=None,
    )
    ctx = resolve_user_llm_context(user, prefs=None, settings=MagicMock(use_vertex_ai=False))
    assert ctx.ready is False
    assert ctx.reason == "no_provider"


def test_resolve_gemini_key_alone_not_ready_without_provider() -> None:
    """Product rule: preferred_provider is required (migration backfills existing rows)."""
    user = SimpleNamespace(
        gemini_api_key_encrypted="enc:v1:fake",
        openai_api_key_encrypted=None,
        anthropic_api_key_encrypted=None,
    )
    ctx = resolve_user_llm_context(
        user, prefs=None, settings=MagicMock(use_vertex_ai=False)
    )
    assert ctx.ready is False
    assert ctx.reason == "no_provider"


def test_resolve_drops_stale_preferred_model() -> None:
    user = SimpleNamespace(
        gemini_api_key_encrypted=None,
        openai_api_key_encrypted="enc:v1:fake",
        anthropic_api_key_encrypted=None,
    )
    prefs = SimpleNamespace(
        preferred_provider="openai",
        preferred_model="gemini-3.5-flash",  # wrong provider
    )
    with patch(
        "utils.encryption.decrypt_api_key", return_value="sk-test-openai-key-1234567890"
    ):
        ctx = resolve_user_llm_context(
            user, prefs, settings=MagicMock(use_vertex_ai=False)
        )
    assert ctx.ready is True
    assert ctx.provider == "openai"
    assert ctx.preferred_model is None



def test_resolve_ollama_ready_without_key() -> None:
    user = SimpleNamespace(
        gemini_api_key_encrypted=None,
        openai_api_key_encrypted=None,
        anthropic_api_key_encrypted=None,
    )
    prefs = SimpleNamespace(preferred_provider="ollama", preferred_model="qwen3")
    ctx = resolve_user_llm_context(user, prefs, settings=MagicMock(use_vertex_ai=False))
    assert ctx.ready is True
    assert ctx.provider == "ollama"
    assert ctx.user_api_key is None
    assert ctx.preferred_model == "qwen3"


def test_resolve_vertex_forces_gemini() -> None:
    user = SimpleNamespace(
        gemini_api_key_encrypted=None,
        openai_api_key_encrypted=None,
        anthropic_api_key_encrypted=None,
    )
    prefs = SimpleNamespace(preferred_provider="openai", preferred_model=None)
    ctx = resolve_user_llm_context(user, prefs, settings=MagicMock(use_vertex_ai=True))
    assert ctx.ready is True
    assert ctx.provider == "gemini"
    assert ctx.user_api_key is None


def test_resolve_openai_needs_key() -> None:
    user = SimpleNamespace(
        gemini_api_key_encrypted=None,
        openai_api_key_encrypted=None,
        anthropic_api_key_encrypted=None,
    )
    prefs = SimpleNamespace(preferred_provider="openai", preferred_model=None)
    ctx = resolve_user_llm_context(user, prefs, settings=MagicMock(use_vertex_ai=False))
    assert ctx.ready is False
    assert ctx.reason == "no_api_key"


def test_resolve_openai_with_key() -> None:
    user = SimpleNamespace(
        gemini_api_key_encrypted=None,
        openai_api_key_encrypted="enc:v1:fake",
        anthropic_api_key_encrypted=None,
    )
    prefs = SimpleNamespace(preferred_provider="openai", preferred_model="gpt-5.6-luna")
    with patch(
        "utils.encryption.decrypt_api_key", return_value="sk-test-openai-key-1234567890"
    ):
        ctx = resolve_user_llm_context(
            user, prefs, settings=MagicMock(use_vertex_ai=False)
        )
    assert ctx.ready is True
    assert ctx.provider == "openai"
    assert ctx.user_api_key == "sk-test-openai-key-1234567890"


def test_user_has_key_for_provider() -> None:
    user = SimpleNamespace(
        gemini_api_key_encrypted="x",
        openai_api_key_encrypted=None,
        anthropic_api_key_encrypted=None,
    )
    assert user_has_key_for_provider(user, "gemini") is True
    assert user_has_key_for_provider(user, "openai") is False
    assert user_has_key_for_provider(user, "ollama") is True


def test_llm_credentials_available_context() -> None:
    ctx = resolve_user_llm_context(
        SimpleNamespace(
            gemini_api_key_encrypted=None,
            openai_api_key_encrypted=None,
            anthropic_api_key_encrypted=None,
        ),
        SimpleNamespace(preferred_provider="ollama", preferred_model=None),
        settings=MagicMock(use_vertex_ai=False),
    )
    assert llm_credentials_available(context=ctx) is True
