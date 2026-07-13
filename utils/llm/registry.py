"""Provider registry — map name → factory."""

from __future__ import annotations

import logging
from typing import Callable, Dict

from utils.llm.base import LLMProvider
from utils.llm.constants import DEFAULT_LLM_PROVIDER, VALID_LLM_PROVIDERS
from utils.llm.errors import LLMError
from utils.llm.providers.anthropic import AnthropicProvider
from utils.llm.providers.gemini import GeminiProvider
from utils.llm.providers.ollama import OllamaProvider
from utils.llm.providers.openai import OpenAIProvider
from utils.logging_config import sanitize_log_value

logger = logging.getLogger(__name__)

_PROVIDER_FACTORIES: Dict[str, Callable[[], LLMProvider]] = {
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "ollama": OllamaProvider,
}


def normalize_provider_name(name: str | None) -> str:
    """
    Normalize and validate a provider name.

    Args:
        name: Raw provider string (case-insensitive)

    Returns:
        Canonical provider name

    Raises:
        LLMError: If the name is not in the allowlist
    """
    if not name or not str(name).strip():
        return DEFAULT_LLM_PROVIDER
    normalized = str(name).strip().lower()
    if normalized not in VALID_LLM_PROVIDERS:
        raise LLMError(
            f"Unsupported LLM provider {normalized!r}. "
            f"Allowed: {', '.join(sorted(VALID_LLM_PROVIDERS))}",
            provider=normalized,
        )
    return normalized


def create_provider(name: str | None = None) -> LLMProvider:
    """
    Instantiate a provider by name.

    Args:
        name: Provider name; defaults to gemini when None/empty

    Returns:
        Configured LLMProvider instance
    """
    resolved = normalize_provider_name(name)
    factory = _PROVIDER_FACTORIES[resolved]
    logger.debug("Creating LLM provider=%s", sanitize_log_value(resolved))
    return factory()
