"""
LLM Client utility for Gemini integration.
Provides async Gemini API client with singleton pattern for text generation and health monitoring.
Includes optional caching for identical prompts to reduce API costs.

Supports two backends:
1. Google AI Studio (google-genai SDK, api_key) - BYOK / free tier with rate limits
2. Vertex AI (google-genai SDK, vertexai=True) - Higher rate limits, pay-per-use
"""

import logging
from time import perf_counter
from typing import Any, Dict, Optional, List
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
from config.settings import get_settings
from utils.logging_config import get_structured_logger, sanitize_log_value
import asyncio

# Both backends use google-genai (imported lazily inside methods)

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

# Default generation parameters
DEFAULT_TEMPERATURE: float = 0.7
DEFAULT_MAX_TOKENS: int = 16000

# Timeout and connection constants
DEFAULT_TIMEOUT: int = 180  # 3 minutes for larger prompts

# Generation parameters
DEFAULT_TOP_P: float = 0.95
DEFAULT_TOP_K: int = 40

# Retry configuration
MAX_RETRIES: int = 3
RETRY_MIN_WAIT: int = 2  # seconds
RETRY_MAX_WAIT: int = 10  # seconds

# Configure module loggers
logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)

# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================


class GeminiError(Exception):
    """
    Custom exception for Gemini-related errors.

    This exception is raised when API calls fail due to connection issues,
    HTTP errors, or other Gemini-specific problems.

    Attributes:
        message: Human-readable description of the error.
        status_code: HTTP status code from the upstream API response, if available.
        original_error: The underlying exception that caused this error, if any.
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.original_error = original_error

    def __repr__(self) -> str:
        parts = [f"GeminiError({self.message!r}"]
        if self.status_code is not None:
            parts.append(f", status_code={self.status_code}")
        if self.original_error is not None:
            parts.append(f", original_error={self.original_error!r}")
        return "".join(parts) + ")"


# =============================================================================
# USER-FACING ERROR STRINGS (workflow / dashboard)
# =============================================================================

_GEMINI_QUOTA_USER_MESSAGE: str = (
    "The AI quota or rate limit for the configured API key was reached. "
    "Try again in a little while, review your plan and quotas for that key, "
    "or update your key under Settings → AI Setup."
)


def _text_indicates_gemini_quota_exhausted(text: str) -> bool:
    """
    Return True if exception text looks like a Gemini / Google AI quota or
    rate-limit response (429 RESOURCE_EXHAUSTED, free-tier caps, etc.).
    """
    if not text:
        return False
    upper = text.upper()
    if "RESOURCE_EXHAUSTED" in upper:
        return True
    lower = text.lower()
    if "exceeded your current quota" in lower or "quota exceeded" in lower:
        return True
    if "free_tier" in lower and "quota" in lower:
        return True
    if "429" in text and (
        "quota" in lower
        or "rate" in lower
        or "resource_exhausted" in lower
        or "generativelanguage" in lower
    ):
        return True
    return False


def _exception_chain_text(exc: BaseException) -> str:
    """Join str() of exc, GeminiError.original_error, and __cause__/__context__."""
    parts: List[str] = []
    seen: set[int] = set()
    cur: Optional[BaseException] = exc
    depth = 0
    while cur is not None and id(cur) not in seen and depth < 8:
        seen.add(id(cur))
        parts.append(str(cur))
        if isinstance(cur, GeminiError) and cur.original_error is not None:
            inner = cur.original_error
            if id(inner) not in seen:
                parts.append(str(inner))
        nxt = cur.__cause__ if cur.__cause__ is not None else cur.__context__
        cur = nxt
        depth += 1
    return " ".join(parts)


def user_facing_message_from_llm_exception(exc: BaseException) -> str:
    """
    Map an LLM/SDK exception to text safe to store in workflow error_messages
    and show on the dashboard. Quota / rate-limit errors become a short,
    actionable message; everything else returns str(exc).
    """
    combined = _exception_chain_text(exc)
    if _text_indicates_gemini_quota_exhausted(combined):
        return _GEMINI_QUOTA_USER_MESSAGE
    return str(exc)


def is_llm_quota_or_rate_limit_exception(exc: BaseException) -> bool:
    """Return True when an exception looks like Gemini / Google AI quota or rate limiting."""
    return _text_indicates_gemini_quota_exhausted(_exception_chain_text(exc))


# =============================================================================
# SINGLETON CLIENT CLASS
# =============================================================================

# Global client instance for singleton pattern
_gemini_client = None


class GeminiClient:
    """
    Async client for interacting with Google Gemini API with singleton pattern.

    This class provides access to the Gemini API with proper error handling,
    connection management, and async support. It implements a singleton pattern
    to ensure efficient resource usage across the application.

    Supports two backends:
    1. Vertex AI (USE_VERTEX_AI=true) - Higher rate limits, requires ADC auth
    2. Google AI Studio (default) - Free tier with rate limits, uses API key

    Supports per-user API keys (BYOK) when user_api_key is provided to generate().

    Attributes:
        api_key (str): Default API key for Gemini API (from environment)
        default_model (str): Default model to use for requests (gemini-flash-2.5)
        timeout (int): Request timeout in seconds
        use_vertex_ai (bool): Whether to use Vertex AI backend
    """

    def __init__(self):
        """
        Initialize Gemini client with settings from configuration.
        This constructor should not be called directly - use get_gemini_client() instead.
        
        Backend selection:
        - USE_VERTEX_AI=true + VERTEX_AI_PROJECT → Vertex AI (ADC auth, no rate limits)
        - Otherwise → Google AI Studio (API key auth, has rate limits)
        """
        settings = get_settings()
        self.timeout = DEFAULT_TIMEOUT
        
        # Vertex AI settings
        self.use_vertex_ai = getattr(settings, 'use_vertex_ai', False)
        self.vertex_project = getattr(settings, 'vertex_ai_project', None)
        self.vertex_location = getattr(settings, 'vertex_ai_location', 'us-central1')
        
        # Google AI Studio API key
        self.api_key = getattr(settings, 'gemini_api_key', None)
        
        # Validate Vertex AI config
        if self.use_vertex_ai and not self.vertex_project:
            logger.warning("USE_VERTEX_AI=true but VERTEX_AI_PROJECT not set. Falling back to Google AI Studio.")
            self.use_vertex_ai = False

        # Log the backend
        if self.use_vertex_ai:
            logger.info(
                f"[LLM] Ready  model={settings.gemini_model}  backend=Vertex AI"
                f"  project={self.vertex_project}  location={self.vertex_location}"
            )
        else:
            logger.info(
                f"[LLM] Ready  model={settings.gemini_model}  backend=Google AI Studio"
                f"  BYOK={'enabled (server key set)' if self.api_key else 'user-key only'}"
            )

        # google-genai uses Client(api_key=...) per-call — no global configure needed.

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
    ) -> Dict[str, Any]:
        """
        Generate a response from the Gemini model with optional caching.

        Args:
            prompt: The prompt to generate a response for
            model: Name of the model to use (optional, uses default if not specified)
            system: System message to set context
            temperature: Sampling temperature (0.0-1.0, default: 0.7)
            max_tokens: Maximum tokens to generate (default: 16000)
            use_cache: Whether to use Redis cache for this request (default: False)
                      Enable for deterministic prompts that don't need fresh responses.
            user_api_key: Optional user-provided API key (BYOK mode).
                         If provided, uses this key instead of the default.
            user_id: User UUID string. When provided, scopes the cache key per user
                     to prevent cross-user hits on prompts that contain personal content
                     (resumes, cover letters, etc.). Omit only for fully public prompts.

        Returns:
            Dict[str, Any]: Response from the model containing generated text

        Raises:
            GeminiError: If the generation fails or returns an error
        """
        # Check cache if enabled
        if use_cache:
            try:
                from utils.cache import get_cached_llm_response
                cached_response = await get_cached_llm_response(prompt, system, user_id)
                if cached_response:
                    logger.info("LLM response served from cache")
                    cached_response["from_cache"] = True
                    return cached_response
            except Exception as cache_error:
                logger.warning("Cache lookup failed, proceeding with API call: %s", sanitize_log_value(str(cache_error)))

        # Call the internal method with retry logic
        result = await self._generate_with_retry(
            prompt=prompt,
            model=model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            user_api_key=user_api_key,
        )

        # Cache the response if caching is enabled
        if use_cache and result:
            try:
                from utils.cache import cache_llm_response
                await cache_llm_response(prompt, result, system, user_id)
            except Exception as cache_error:
                logger.warning("Failed to cache LLM response: %s", sanitize_log_value(str(cache_error)))

        return result

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=RETRY_MIN_WAIT, max=RETRY_MAX_WAIT),
        retry=retry_if_exception_type((GeminiError, ConnectionError, TimeoutError)),
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
    ) -> Dict[str, Any]:
        """
        Internal generate method with retry logic.

        Uses tenacity for automatic retries with exponential backoff
        on transient failures (connection errors, timeouts).

        Args:
            prompt: The prompt to generate a response for
            model: Name of the model to use
            system: System message to set context
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            user_api_key: Optional user-provided API key (BYOK mode)

        Returns:
            Dict[str, Any]: Response from the model

        Raises:
            GeminiError: If all retries fail
        """
        # Route to appropriate backend
        if self.use_vertex_ai:
            return await self._generate_with_vertex_ai(
                prompt=prompt,
                model=model,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            return await self._generate_with_google_ai(
                prompt=prompt,
                model=model,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                user_api_key=user_api_key,
            )

    async def _generate_with_vertex_ai(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> Dict[str, Any]:
        """Generate using Vertex AI backend with ADC authentication (higher rate limits)."""
        try:
            from google import genai as google_genai
            from google.genai import types
            
            current_settings = get_settings()
            model_to_use = model or current_settings.gemini_model
            
            # Create client with Vertex AI using ADC (Application Default Credentials)
            # Requires: gcloud auth application-default login
            client = google_genai.Client(
                vertexai=True,
                project=self.vertex_project,
                location=self.vertex_location,
            )
            
            # Combine system and user prompts
            if system:
                combined_prompt = f"{system}\n\n{prompt}"
            else:
                combined_prompt = prompt
            
            # Create generation config
            # Disable thinking mode — on flash models it consumes the output token
            # budget for internal reasoning, leaving too little for actual output
            config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                top_p=DEFAULT_TOP_P,
                top_k=DEFAULT_TOP_K,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            )
            
            prompt_chars = len(combined_prompt)
            logger.info(
                f"[LLM] Vertex AI  model={model_to_use}"
                f"  prompt={prompt_chars:,} chars"
                f"  temp={temperature}"
            )

            # Generate response (bounded by DEFAULT_TIMEOUT to prevent indefinite hangs)
            api_start_time = perf_counter()
            response = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: client.models.generate_content(
                        model=model_to_use,
                        contents=combined_prompt,
                        config=config,
                    )
                ),
                timeout=self.timeout,
            )
            api_duration_ms = (perf_counter() - api_start_time) * 1000

            # Extract response text
            try:
                response_text = response.text
            except Exception as text_error:
                logger.error("[LLM] Failed to extract response text: %s", sanitize_log_value(str(text_error)), exc_info=True)
                response_text = "Error retrieving response. Please try again."

            logger.info(
                f"[LLM] Done  {api_duration_ms:.0f}ms"
                f"  response={len(response_text):,} chars"
            )

            # Log API call performance
            structured_logger.log_external_api_call(
                service="vertex_ai",
                operation="generate_content",
                duration_ms=api_duration_ms,
                success=True,
            )

            return {"model": model_to_use, "response": response_text, "done": True}
            
        except Exception as e:
            structured_logger.log_external_api_call(
                service="vertex_ai",
                operation="generate_content",
                duration_ms=0,
                success=False,
                error=str(e),
            )
            logger.error("Error in Vertex AI generate: %s", sanitize_log_value(str(e)), exc_info=True)
            raise GeminiError(f"Vertex AI generate failed: {str(e)}", original_error=e)

    async def _generate_with_google_ai(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        user_api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate using Google AI Studio backend (BYOK / free tier)."""
        try:
            from google import genai as google_genai
            from google.genai import types

            current_settings = get_settings()

            effective_api_key = user_api_key or self.api_key
            if not effective_api_key:
                raise GeminiError(
                    "No API key available. Please configure your Gemini API key in Settings."
                )

            client = google_genai.Client(api_key=effective_api_key)
            model_to_use = model or current_settings.gemini_model

            if system:
                combined_prompt = f"{system}\n\n{prompt}"
            else:
                combined_prompt = prompt

            config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                top_p=DEFAULT_TOP_P,
                top_k=DEFAULT_TOP_K,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            )

            prompt_chars = len(combined_prompt)
            byok_label = "  byok=user-key" if user_api_key else ""
            logger.info(
                f"[LLM] Google AI Studio  model={model_to_use}"
                f"  prompt={prompt_chars:,} chars"
                f"  temp={temperature}"
                f"{byok_label}"
            )

            api_start_time = perf_counter()
            response = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: client.models.generate_content(
                        model=model_to_use,
                        contents=combined_prompt,
                        config=config,
                    ),
                ),
                timeout=self.timeout,
            )
            api_duration_ms = (perf_counter() - api_start_time) * 1000

            try:
                response_text: str = response.text
            except Exception as text_error:
                logger.error("[LLM] Failed to extract response text: %s", sanitize_log_value(str(text_error)), exc_info=True)
                response_text = "Error retrieving response from Gemini API. Please try again."

            # Check for safety filter (finish_reason OTHER than STOP/MAX_TOKENS)
            filtered = False
            if hasattr(response, "candidates") and response.candidates:
                finish_reason = getattr(response.candidates[0], "finish_reason", None)
                if finish_reason and str(finish_reason) not in ("FinishReason.STOP", "FinishReason.MAX_TOKENS", "1", "2"):
                    filtered = True

            logger.info(
                f"[LLM] Done  {api_duration_ms:.0f}ms"
                f"  response={len(response_text):,} chars"
            )

            structured_logger.log_external_api_call(
                service="gemini",
                operation="generate_content",
                duration_ms=api_duration_ms,
                success=True,
            )

            if filtered:
                logger.warning("[LLM] Content filtered by safety settings  model=%s", sanitize_log_value(str(model_to_use)))
                return {"model": model_to_use, "response": "The content generation was blocked by safety filters. Please try with different input or contact support.", "done": True, "filtered": True}

            return {"model": model_to_use, "response": response_text, "done": True}

        except Exception as e:
            structured_logger.log_external_api_call(
                service="gemini",
                operation="generate_content",
                duration_ms=0,
                success=False,
                error=str(e),
            )
            logger.error("Error in Gemini generate: %s", sanitize_log_value(str(e)), exc_info=True)
            raise GeminiError(f"Generate failed: {str(e)}", original_error=e)

    async def health_check(self) -> bool:
        """
        Check if Gemini service is healthy by making a simple API call.

        Returns:
            bool: True if service is healthy and accessible, False otherwise
        """
        try:
            if self.use_vertex_ai:
                # Use a quota-free model metadata fetch instead of generate_content
                # so health checks don't burn tokens or trigger rate limits.
                from google import genai as google_genai
                client = google_genai.Client(
                    vertexai=True,
                    project=self.vertex_project,
                    location=self.vertex_location,
                )
                settings = get_settings()
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: client.models.get(model=settings.gemini_model),
                    ),
                    timeout=10.0,
                )
            else:
                # BYOK-only mode: no server key to verify, nothing to check.
                if not self.api_key:
                    return True
                from google import genai as google_genai
                _hc_client = google_genai.Client(api_key=self.api_key)
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, lambda: list(_hc_client.models.list())
                    ),
                    timeout=10.0,
                )
            return True
        except Exception as e:
            # 429 RESOURCE_EXHAUSTED means the service is reachable and responding
            # correctly — it is simply enforcing quota. Treat as healthy.
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                logger.info("Gemini health check: quota limit hit but service is reachable")
                return True
            logger.warning("Gemini health check failed: %s", sanitize_log_value(str(e)))
            return False


# =============================================================================
# GLOBAL FUNCTIONS
# =============================================================================


def reset_gemini_client() -> None:
    """
    Reset the global Gemini client instance.
    This forces a new client to be created with the latest settings.
    """
    global _gemini_client
    _gemini_client = None
    logger.info("Reset Gemini client")


async def get_gemini_client() -> GeminiClient:
    """
    Get or create the global Gemini client instance.

    This function implements the singleton pattern to ensure only one
    client instance is used across the application.

    Returns:
        GeminiClient: Shared Gemini client instance
    """
    global _gemini_client

    if _gemini_client is None:
        _gemini_client = GeminiClient()
        logger.info("Initialized Gemini client")

    return _gemini_client


async def check_gemini_health() -> bool:
    """
    Check if Gemini service is running and accessible.

    This function performs a health check by attempting to connect to
    the Gemini service and verify its accessibility. It's useful for
    startup checks and monitoring.

    Returns:
        bool: True if service is healthy and accessible, False otherwise
    """
    try:
        # Get client instance (this will create it if needed)
        client = await get_gemini_client()

        # Perform health check using the client
        response = await client.health_check()
        if not response:
            logger.warning("Gemini health check failed: Service not responsive")
            return False

        # Only log when a real server-key check was performed (not BYOK-only no-op).
        server_has_key = bool(client.api_key) or client.use_vertex_ai
        if server_has_key:
            logger.info("Gemini health check successful")
        return True
    except Exception as e:
        logger.error("Gemini health check failed: %s", sanitize_log_value(str(e)), exc_info=True)
        return False


async def close_gemini_client() -> None:
    """
    Close Gemini client connection and clean up resources.

    This function should be called during application shutdown to ensure
    proper cleanup of resources.
    """
    global _gemini_client

    if _gemini_client:
        _gemini_client = None
        logger.info("Gemini client connection closed")
