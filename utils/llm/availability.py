"""LLM credential / availability helpers used by API gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from utils.llm.constants import DEFAULT_LLM_PROVIDER, VALID_LLM_PROVIDERS
from utils.llm.errors import LLMError
from utils.llm.registry import normalize_provider_name
from utils.logging_config import sanitize_log_value

import logging

logger = logging.getLogger(__name__)


def _settings(settings: Any = None) -> Any:
    """Return settings, resolving get_settings at call time so test patches apply."""
    if settings is not None:
        return settings
    from config.settings import get_settings

    return get_settings()


def active_llm_provider(settings: Any = None) -> str:
    """
    Return the server-admin configured provider (health / admin fallback).

    User-facing generate paths must use ``resolve_user_llm_context`` instead.
    """
    cfg = _settings(settings)
    raw = getattr(cfg, "llm_provider", None)
    if not isinstance(raw, str):
        return DEFAULT_LLM_PROVIDER
    try:
        return normalize_provider_name(raw)
    except LLMError:
        return DEFAULT_LLM_PROVIDER


def server_has_llm_credentials(settings: Any = None) -> bool:
    """
    Return True when the server can serve LLM calls without user BYOK.

    Only Vertex AI counts for user-facing gates. Other server env keys are
    health/admin only under the per-user BYOK product model.
    """
    cfg = _settings(settings)
    return bool(getattr(cfg, "use_vertex_ai", False))


def encrypted_key_attr_for_provider(provider: str) -> Optional[str]:
    """Return the User model column name for a provider's encrypted key."""
    return {
        "gemini": "gemini_api_key_encrypted",
        "openai": "openai_api_key_encrypted",
        "anthropic": "anthropic_api_key_encrypted",
    }.get(provider)


def decrypt_user_key_for_provider(user: Any, provider: str) -> Optional[str]:
    """
    Decrypt the BYOK key stored for ``provider`` on the user row.

    Args:
        user: User ORM object (or duck-typed with encrypted columns)
        provider: Canonical provider name

    Returns:
        Decrypted key, or None when missing / Ollama / decrypt failure
    """
    if provider == "ollama":
        return None
    attr = encrypted_key_attr_for_provider(provider)
    if not attr:
        return None
    encrypted = getattr(user, attr, None)
    if not encrypted:
        return None
    try:
        from utils.encryption import decrypt_api_key

        return decrypt_api_key(encrypted)
    except Exception as exc:
        logger.warning(
            "Failed to decrypt %s API key for user: %s",
            sanitize_log_value(provider),
            sanitize_log_value(str(exc)),
        )
        return None


def user_has_key_for_provider(user: Any, provider: str) -> bool:
    """Return True when the user has a stored encrypted key for the provider."""
    if provider == "ollama":
        return True
    attr = encrypted_key_attr_for_provider(provider)
    if not attr:
        return False
    return bool(getattr(user, attr, None))


@dataclass(frozen=True)
class UserLLMContext:
    """Resolved per-user LLM routing context for generate() calls."""

    provider: str
    user_api_key: Optional[str]
    preferred_model: Optional[str]
    ready: bool
    reason: Optional[str] = None


def resolve_user_llm_context(
    user: Any,
    prefs: Any = None,
    *,
    settings: Any = None,
) -> UserLLMContext:
    """
    Resolve provider + BYOK key + preferred model for a user.

    Product rules:
    - User must have chosen ``preferred_provider`` (no implicit default).
    - Cloud providers require a BYOK key for that provider.
    - Ollama requires provider pick only (no key).
    - ``USE_VERTEX_AI=true`` forces Gemini without a user key.

    Args:
        user: User ORM object with encrypted key columns
        prefs: UserWorkflowPreferences row or dict with preferred_* fields
        settings: Optional Settings instance

    Returns:
        UserLLMContext (ready=False when CFG_6001 should be raised)
    """
    cfg = _settings(settings)

    # Vertex admin escape hatch — Gemini, no BYOK required
    if bool(getattr(cfg, "use_vertex_ai", False)):
        return UserLLMContext(
            provider="gemini",
            user_api_key=None,
            preferred_model=None,  # Vertex always uses server model
            ready=True,
            reason=None,
        )

    preferred_provider = _prefs_get(prefs, "preferred_provider")
    if not preferred_provider or not str(preferred_provider).strip():
        return UserLLMContext(
            provider="",
            user_api_key=None,
            preferred_model=None,
            ready=False,
            reason="no_provider",
        )

    try:
        provider = normalize_provider_name(str(preferred_provider))
    except LLMError:
        return UserLLMContext(
            provider="",
            user_api_key=None,
            preferred_model=None,
            ready=False,
            reason="invalid_provider",
        )

    preferred_model_raw = _prefs_get(prefs, "preferred_model")
    preferred_model = (
        preferred_model_raw.strip()
        if isinstance(preferred_model_raw, str) and preferred_model_raw.strip()
        else None
    )
    # Drop stale models left over after a provider switch
    if preferred_model:
        from utils.llm.models import is_valid_model_for_provider

        if not is_valid_model_for_provider(provider, preferred_model):
            preferred_model = None

    if provider == "ollama":
        return UserLLMContext(
            provider=provider,
            user_api_key=None,
            preferred_model=preferred_model,
            ready=True,
        )

    key = decrypt_user_key_for_provider(user, provider)
    if not key:
        return UserLLMContext(
            provider=provider,
            user_api_key=None,
            preferred_model=preferred_model,
            ready=False,
            reason="no_api_key",
        )

    return UserLLMContext(
        provider=provider,
        user_api_key=key,
        preferred_model=preferred_model,
        ready=True,
    )


def _prefs_get(prefs: Any, field: str) -> Any:
    """Read a preference from an ORM row or dict."""
    if prefs is None:
        return None
    if isinstance(prefs, dict):
        return prefs.get(field)
    return getattr(prefs, field, None)


def effective_user_api_key(
    user_gemini_api_key: Optional[str],
    *,
    provider: Optional[str] = None,
    settings: Any = None,
) -> Optional[str]:
    """
    Backward-compatible helper: return Gemini BYOK only when provider is gemini.

    Prefer ``resolve_user_llm_context`` for new code.
    """
    if provider is not None:
        try:
            resolved = (
                normalize_provider_name(provider)
                if isinstance(provider, str)
                else DEFAULT_LLM_PROVIDER
            )
        except LLMError:
            resolved = DEFAULT_LLM_PROVIDER
    else:
        # Legacy callers without preferred_provider — only Gemini keys apply
        resolved = "gemini"
    if resolved != "gemini":
        return None
    return user_gemini_api_key


def llm_credentials_available(
    user_gemini_api_key: Optional[str] = None,
    *,
    settings: Any = None,
    context: Optional[UserLLMContext] = None,
) -> bool:
    """
    Return True when LLM calls can proceed.

    Prefer passing ``context=resolve_user_llm_context(...)``. The legacy
    ``user_gemini_api_key`` path only covers Gemini BYOK + Vertex.
    """
    if context is not None:
        return context.ready
    cfg = _settings(settings)
    if bool(getattr(cfg, "use_vertex_ai", False)):
        return True
    return bool(user_gemini_api_key)


def provider_requires_api_key(provider: str) -> bool:
    """Return True when the provider needs a user BYOK key."""
    return provider in ("gemini", "openai", "anthropic")


def is_valid_provider_name(name: Optional[str]) -> bool:
    """Return True when name is in the provider allowlist."""
    if not name or not str(name).strip():
        return False
    return str(name).strip().lower() in VALID_LLM_PROVIDERS
