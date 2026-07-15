"""LLMClient facade — cache, retry, and provider routing."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict, Optional

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

    Caches provider instances by name and routes each generate() call.
    Gemini-specific private helpers remain for backward-compatible unit tests.
    """

    def __init__(self, provider: Optional[LLMProvider] = None) -> None:
        """
        Initialize the client with an optional default provider.

        Args:
            provider: Optional pre-built default provider; otherwise created
                from settings.llm_provider (health/admin fallback)
        """
        settings = get_settings()
        provider_name = normalize_provider_name(
            getattr(settings, "llm_provider", None)
        )
        self._providers: Dict[str, LLMProvider] = {}
        self._provider: LLMProvider = provider or create_provider(provider_name)
        self._providers[getattr(self._provider, "name", provider_name)] = (
            self._provider
        )
        self.timeout = DEFAULT_TIMEOUT
        self._sync_compat_attrs(self._provider)

    def _sync_compat_attrs(self, provider: LLMProvider) -> None:
        """Update Gemini-compat attributes from the given provider."""
        if isinstance(provider, GeminiProvider):
            self.use_vertex_ai = provider.use_vertex_ai
            self.vertex_project = provider.vertex_project
            self.vertex_location = provider.vertex_location
            self.api_key = provider.api_key
        else:
            self.use_vertex_ai = False
            self.vertex_project = None
            self.vertex_location = None
            self.api_key = getattr(provider, "api_key", None)

    def _get_provider(self, provider: Optional[str] = None) -> LLMProvider:
        """
        Resolve a provider instance by name (cached).

        Args:
            provider: Explicit provider name; None → default ``self._provider``

        Returns:
            LLMProvider instance
        """
        if not provider:
            return self._provider
        name = normalize_provider_name(provider)
        existing = self._providers.get(name)
        if existing is not None:
            return existing
        created = create_provider(name)
        self._providers[name] = created
        return created

    @property
    def provider_name(self) -> str:
        """Default (admin/health) provider name."""
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
        provider: Optional[str] = None,
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
            use_google_search_grounding: Web-search / Google grounding flag
            provider: Explicit provider name (required for per-user routing)

        Returns:
            Normalized generate result dict

        Raises:
            LLMError: On upstream failure after retries
        """
        cache_provider = None
        if provider:
            cache_provider = normalize_provider_name(provider)

        if use_cache:
            try:
                from utils.cache import get_cached_llm_response

                cached_response = await get_cached_llm_response(
                    prompt, system, user_id, provider=cache_provider
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
            provider=provider,
        )

        if use_cache and result:
            try:
                from utils.cache import cache_llm_response

                await cache_llm_response(
                    prompt, result, system, user_id, provider=cache_provider
                )
            except Exception as cache_error:
                logger.warning(
                    "Failed to cache LLM response: %s",
                    sanitize_log_value(str(cache_error)),
                )

        return result

    async def generate_stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        user_api_key: Optional[str] = None,
        use_google_search_grounding: bool = False,
        provider: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        Stream text deltas from the selected provider (no Redis cache, no retry).

        Args:
            prompt: User prompt
            model: Optional model override
            system: Optional system instruction
            temperature: Sampling temperature
            max_tokens: Max output tokens
            user_api_key: Optional BYOK key
            use_google_search_grounding: When True, providers may fall back to
                a single full-text yield
            provider: Explicit provider name for per-user routing

        Yields:
            Text deltas as they arrive from the model
        """
        selected = self._get_provider(provider)
        async for delta in selected.generate_stream(
            prompt,
            model=model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            user_api_key=user_api_key,
            use_google_search_grounding=use_google_search_grounding,
        ):
            yield delta

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
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retry wrapper around the selected provider."""
        selected = self._get_provider(provider)

        # Gemini: keep Vertex vs AI Studio routing; tests patch facade helpers.
        if isinstance(selected, GeminiProvider):
            # Temporarily sync compat attrs so patched helpers see Vertex flags
            prev = self._provider
            self._provider = selected
            self._sync_compat_attrs(selected)
            try:
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
            finally:
                self._provider = prev
                self._sync_compat_attrs(prev)

        return await selected.generate(
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
        """Delegate health check to the default provider."""
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
