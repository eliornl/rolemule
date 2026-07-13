"""LLMClient facade — cache, retry, and provider routing."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config.settings import get_settings
from utils.llm.base import LLMProvider
from utils.llm.constants import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT,
    MAX_RETRIES,
    RETRY_MAX_WAIT,
    RETRY_MIN_WAIT,
)
from utils.llm.errors import LLMError
from utils.llm.providers.gemini import GeminiProvider
from utils.llm.registry import create_provider, normalize_provider_name
from utils.logging_config import sanitize_log_value

logger = logging.getLogger(__name__)

# Module-level singleton (also mirrored on utils.llm_client for tests)
_llm_client: Optional["LLMClient"] = None


class LLMClient:
    """
    Unified async LLM client.

    Wraps a single LLMProvider with Redis response caching and tenacity retries.
    Gemini-specific private helpers remain for backward-compatible unit tests.
    """

    def __init__(self, provider: Optional[LLMProvider] = None) -> None:
        """
        Initialize the client with a provider (or settings.llm_provider default).

        Args:
            provider: Optional pre-built provider; otherwise created from settings
        """
        settings = get_settings()
        provider_name = normalize_provider_name(
            getattr(settings, "llm_provider", None)
        )
        self._provider: LLMProvider = provider or create_provider(provider_name)
        self.timeout = DEFAULT_TIMEOUT

        # Gemini compat attributes (used by health helpers / older tests)
        if isinstance(self._provider, GeminiProvider):
            self.use_vertex_ai = self._provider.use_vertex_ai
            self.vertex_project = self._provider.vertex_project
            self.vertex_location = self._provider.vertex_location
            self.api_key = self._provider.api_key
        else:
            self.use_vertex_ai = False
            self.vertex_project = None
            self.vertex_location = None
            self.api_key = getattr(self._provider, "api_key", None)

    @property
    def provider_name(self) -> str:
        """Active provider name."""
        return getattr(self._provider, "name", "unknown")

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        use_cache: bool = False,
        user_api_key: Optional[str] = None,
        user_id: Optional[str] = None,
        use_google_search_grounding: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate a response with optional caching.

        Args:
            prompt: User prompt
            model: Optional model override
            system: Optional system instruction
            temperature: Sampling temperature
            max_tokens: Max output tokens
            use_cache: When True, use Redis LLM response cache
            user_api_key: Optional BYOK key
            user_id: Scopes cache key for personal prompts
            use_google_search_grounding: Gemini-only Google Search tool

        Returns:
            Normalized generate result dict

        Raises:
            LLMError: On upstream failure after retries
        """
        if use_cache:
            try:
                from utils.cache import get_cached_llm_response

                cached_response = await get_cached_llm_response(
                    prompt, system, user_id
                )
                if cached_response:
                    logger.info("LLM response served from cache")
                    cached_response["from_cache"] = True
                    return cached_response
            except Exception as cache_error:
                logger.warning(
                    "Cache lookup failed, proceeding with API call: %s",
                    sanitize_log_value(str(cache_error)),
                )

        result = await self._generate_with_retry(
            prompt=prompt,
            model=model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            user_api_key=user_api_key,
            use_google_search_grounding=use_google_search_grounding,
        )

        if use_cache and result:
            try:
                from utils.cache import cache_llm_response

                await cache_llm_response(prompt, result, system, user_id)
            except Exception as cache_error:
                logger.warning(
                    "Failed to cache LLM response: %s",
                    sanitize_log_value(str(cache_error)),
                )

        return result

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=RETRY_MIN_WAIT, max=RETRY_MAX_WAIT),
        retry=retry_if_exception_type((LLMError, ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _generate_with_retry(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        user_api_key: Optional[str] = None,
        use_google_search_grounding: bool = False,
    ) -> Dict[str, Any]:
        """Retry wrapper around the active provider."""
        # Gemini: keep Vertex vs AI Studio routing inside the provider.
        # Tests patch LLMClient._generate_with_vertex_ai / _generate_with_google_ai.
        if isinstance(self._provider, GeminiProvider):
            if self.use_vertex_ai:
                return await self._generate_with_vertex_ai(
                    prompt=prompt,
                    model=model,
                    system=system,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    use_google_search_grounding=use_google_search_grounding,
                )
            return await self._generate_with_google_ai(
                prompt=prompt,
                model=model,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                user_api_key=user_api_key,
                use_google_search_grounding=use_google_search_grounding,
            )

        return await self._provider.generate(
            prompt,
            model=model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            user_api_key=user_api_key,
            use_google_search_grounding=use_google_search_grounding,
        )

    # -------------------------------------------------------------------------
    # Gemini-compatible helpers (delegate to GeminiProvider for unit tests)
    # -------------------------------------------------------------------------

    @staticmethod
    def _build_generate_config(
        *,
        temperature: float,
        max_tokens: int,
        use_google_search_grounding: bool,
    ) -> Any:
        return GeminiProvider._build_generate_config(
            temperature=temperature,
            max_tokens=max_tokens,
            use_google_search_grounding=use_google_search_grounding,
        )

    async def _generate_with_vertex_ai(self, **kwargs: Any) -> Dict[str, Any]:
        assert isinstance(self._provider, GeminiProvider)
        return await self._provider._generate_with_vertex_ai(**kwargs)

    async def _generate_with_google_ai(self, **kwargs: Any) -> Dict[str, Any]:
        assert isinstance(self._provider, GeminiProvider)
        return await self._provider._generate_with_google_ai(**kwargs)

    async def health_check(self) -> bool:
        """Delegate health check to the active provider."""
        return await self._provider.health_check()


# Backward-compatible class name
GeminiClient = LLMClient


def reset_llm_client() -> None:
    """Reset the global LLM client singleton."""
    global _llm_client
    _llm_client = None
    logger.info("Reset LLM client")


def reset_gemini_client() -> None:
    """Alias for reset_llm_client (backward compatible)."""
    reset_llm_client()


async def get_llm_client() -> LLMClient:
    """
    Get or create the global LLM client singleton.

    Returns:
        Shared LLMClient instance
    """
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
        logger.info(
            "Initialized LLM client provider=%s",
            sanitize_log_value(_llm_client.provider_name),
        )
    return _llm_client


async def get_gemini_client() -> LLMClient:
    """Alias for get_llm_client (backward compatible)."""
    return await get_llm_client()


async def check_llm_health() -> bool:
    """
    Check whether the configured LLM provider is healthy.

    Returns:
        True when healthy / reachable (including quota 429)
    """
    try:
        client = await get_llm_client()
        response = await client.health_check()
        if not response:
            logger.warning("LLM health check failed: Service not responsive")
            return False
        server_has_key = bool(client.api_key) or client.use_vertex_ai
        if client.provider_name == "ollama":
            server_has_key = True
        if server_has_key:
            logger.info(
                "LLM health check successful provider=%s",
                sanitize_log_value(client.provider_name),
            )
        return True
    except Exception as e:
        logger.error(
            "LLM health check failed: %s",
            sanitize_log_value(str(e)),
            exc_info=True,
        )
        return False


async def check_gemini_health() -> bool:
    """Alias for check_llm_health (backward compatible)."""
    return await check_llm_health()


async def close_llm_client() -> None:
    """Drop the singleton reference (no open sockets held at facade level)."""
    global _llm_client
    if _llm_client:
        _llm_client = None
        logger.info("LLM client connection closed")


async def close_gemini_client() -> None:
    """Alias for close_llm_client (backward compatible)."""
    await close_llm_client()
