"""LLM credential / availability helpers used by API gates."""

from __future__ import annotations

from typing import Any, Optional

from utils.llm.constants import DEFAULT_LLM_PROVIDER
from utils.llm.errors import LLMError
from utils.llm.registry import normalize_provider_name


def _settings(settings: Any = None) -> Any:
    """Return settings, resolving get_settings at call time so test patches apply."""
    if settings is not None:
        return settings
    from config.settings import get_settings

    return get_settings()


def active_llm_provider(settings: Any = None) -> str:
    """Return the configured provider name (always lowercased allowlist value)."""
    cfg = _settings(settings)
    raw = getattr(cfg, "llm_provider", None)
    # Tests often use MagicMock settings without llm_provider — treat non-str as default
    if not isinstance(raw, str):
        return DEFAULT_LLM_PROVIDER
    try:
        return normalize_provider_name(raw)
    except LLMError:
        return DEFAULT_LLM_PROVIDER


def server_has_llm_credentials(settings: Any = None) -> bool:
    """
    Return True when the server can serve LLM calls for the active provider
    without a user BYOK key.

    Args:
        settings: Optional Settings instance (defaults to get_settings())

    Returns:
        True when server credentials/URL for the active provider are present
    """
    cfg = _settings(settings)
    provider = active_llm_provider(cfg)

    if provider == "gemini":
        return bool(getattr(cfg, "gemini_api_key", None)) or bool(
            getattr(cfg, "use_vertex_ai", False)
        )
    if provider == "openai":
        return bool(getattr(cfg, "openai_api_key", None))
    if provider == "anthropic":
        return bool(getattr(cfg, "anthropic_api_key", None))
    if provider == "ollama":
        # Local daemon — base URL always has a default; treat as available
        return True
    return False


def effective_user_api_key(
    user_gemini_api_key: Optional[str],
    *,
    provider: Optional[str] = None,
    settings: Any = None,
) -> Optional[str]:
    """
    Return a BYOK key only when it is valid for the active provider.

    User-stored keys are Gemini-only today. Non-Gemini providers ignore the
    Gemini BYOK key so it is never sent to OpenAI/Anthropic as a bearer token.

    Args:
        user_gemini_api_key: Decrypted Gemini key from the user record, if any
        provider: Optional override; defaults to settings.llm_provider
        settings: Optional Settings instance

    Returns:
        Key to pass as ``user_api_key``, or None
    """
    if provider is not None:
        resolved = normalize_provider_name(provider) if isinstance(provider, str) else DEFAULT_LLM_PROVIDER
    else:
        resolved = active_llm_provider(settings)
    if resolved != "gemini":
        return None
    return user_gemini_api_key


def llm_credentials_available(
    user_gemini_api_key: Optional[str],
    *,
    settings: Any = None,
) -> bool:
    """
    Return True when either effective BYOK or server credentials can run LLM calls.

    Args:
        user_gemini_api_key: Decrypted Gemini BYOK key if any
        settings: Optional Settings instance

    Returns:
        True when generate() can proceed for the active provider
    """
    if effective_user_api_key(user_gemini_api_key, settings=settings):
        return True
    return server_has_llm_credentials(settings)
