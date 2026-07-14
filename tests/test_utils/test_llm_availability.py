"""Tests for utils.llm.availability helpers (per-user BYOK model)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from utils.llm.availability import (
    active_llm_provider,
    decrypt_user_key_for_provider,
    effective_user_api_key,
    encrypted_key_attr_for_provider,
    is_valid_provider_name,
    llm_credentials_available,
    provider_requires_api_key,
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


def test_active_llm_provider_invalid_and_non_string() -> None:
    assert active_llm_provider(MagicMock(llm_provider=None)) == "gemini"
    assert active_llm_provider(MagicMock(llm_provider=123)) == "gemini"
    assert active_llm_provider(MagicMock(llm_provider="not-a-provider")) == "gemini"


def test_encrypted_key_attr_for_provider() -> None:
    assert encrypted_key_attr_for_provider("gemini") == "gemini_api_key_encrypted"
    assert encrypted_key_attr_for_provider("openai") == "openai_api_key_encrypted"
    assert encrypted_key_attr_for_provider("anthropic") == "anthropic_api_key_encrypted"
    assert encrypted_key_attr_for_provider("ollama") is None
    assert encrypted_key_attr_for_provider("unknown") is None


def test_decrypt_user_key_for_provider_paths() -> None:
    user = SimpleNamespace(
        gemini_api_key_encrypted="enc",
        openai_api_key_encrypted=None,
        anthropic_api_key_encrypted=None,
    )
    assert decrypt_user_key_for_provider(user, "ollama") is None
    assert decrypt_user_key_for_provider(user, "openai") is None
    assert decrypt_user_key_for_provider(user, "unknown") is None
    with patch("utils.encryption.decrypt_api_key", return_value="sk-gemini"):
        assert decrypt_user_key_for_provider(user, "gemini") == "sk-gemini"
    with patch("utils.encryption.decrypt_api_key", side_effect=RuntimeError("bad")):
        assert decrypt_user_key_for_provider(user, "gemini") is None


def test_resolve_requires_provider() -> None:
    user = SimpleNamespace(
        gemini_api_key_encrypted=None,
        openai_api_key_encrypted=None,
        anthropic_api_key_encrypted=None,
    )
    ctx = resolve_user_llm_context(user, prefs=None, settings=MagicMock(use_vertex_ai=False))
    assert ctx.ready is False
    assert ctx.reason == "no_provider"


def test_resolve_invalid_provider() -> None:
    user = SimpleNamespace(
        gemini_api_key_encrypted=None,
        openai_api_key_encrypted=None,
        anthropic_api_key_encrypted=None,
    )
    prefs = SimpleNamespace(preferred_provider="nope", preferred_model=None)
    ctx = resolve_user_llm_context(user, prefs, settings=MagicMock(use_vertex_ai=False))
    assert ctx.ready is False
    assert ctx.reason == "invalid_provider"


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


def test_resolve_prefs_dict() -> None:
    user = SimpleNamespace(
        gemini_api_key_encrypted=None,
        openai_api_key_encrypted=None,
        anthropic_api_key_encrypted=None,
    )
    ctx = resolve_user_llm_context(
        user,
        {"preferred_provider": "ollama", "preferred_model": None},
        settings=MagicMock(use_vertex_ai=False),
    )
    assert ctx.ready is True
    assert ctx.provider == "ollama"


def test_user_has_key_for_provider() -> None:
    user = SimpleNamespace(
        gemini_api_key_encrypted="x",
        openai_api_key_encrypted=None,
        anthropic_api_key_encrypted=None,
    )
    assert user_has_key_for_provider(user, "gemini") is True
    assert user_has_key_for_provider(user, "openai") is False
    assert user_has_key_for_provider(user, "ollama") is True
    assert user_has_key_for_provider(user, "unknown") is False


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


def test_llm_credentials_available_legacy() -> None:
    assert llm_credentials_available(
        None, settings=MagicMock(use_vertex_ai=True)
    ) is True
    assert llm_credentials_available(
        "sk", settings=MagicMock(use_vertex_ai=False)
    ) is True
    assert llm_credentials_available(
        None, settings=MagicMock(use_vertex_ai=False)
    ) is False


def test_effective_user_api_key() -> None:
    assert effective_user_api_key("sk") == "sk"
    assert effective_user_api_key("sk", provider="gemini") == "sk"
    assert effective_user_api_key("sk", provider="openai") is None
    assert effective_user_api_key("sk", provider="BAD") == "sk"
    assert effective_user_api_key("sk", provider=123) == "sk"  # type: ignore[arg-type]


def test_provider_requires_api_key_and_valid_name() -> None:
    assert provider_requires_api_key("gemini") is True
    assert provider_requires_api_key("ollama") is False
    assert is_valid_provider_name("gemini") is True
    assert is_valid_provider_name("GEMINI") is True
    assert is_valid_provider_name("") is False
    assert is_valid_provider_name(None) is False
    assert is_valid_provider_name("nope") is False
