"""
Multi-provider LLM package.

Prefer ``get_llm_client()`` for new code. ``get_gemini_client`` remains as a
backward-compatible alias.
"""

from utils.llm.client import (
    GeminiClient,
    LLMClient,
    check_gemini_health,
    check_llm_health,
    close_gemini_client,
    close_llm_client,
    get_gemini_client,
    get_llm_client,
    reset_gemini_client,
    reset_llm_client,
)
from utils.llm.constants import (
    DEFAULT_LLM_PROVIDER,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT,
    DEFAULT_TOP_K,
    DEFAULT_TOP_P,
    MAX_RETRIES,
    RETRY_MAX_WAIT,
    RETRY_MIN_WAIT,
    VALID_LLM_PROVIDERS,
)
from utils.llm.errors import (
    GeminiError,
    LLMError,
    _GEMINI_QUOTA_USER_MESSAGE,
    _exception_chain_text,
    _text_indicates_gemini_quota_exhausted,
    is_llm_quota_or_rate_limit_exception,
    user_facing_message_from_llm_exception,
)

__all__ = [
    "DEFAULT_LLM_PROVIDER",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_TEMPERATURE",
    "DEFAULT_TIMEOUT",
    "DEFAULT_TOP_K",
    "DEFAULT_TOP_P",
    "GeminiClient",
    "GeminiError",
    "LLMClient",
    "LLMError",
    "MAX_RETRIES",
    "RETRY_MAX_WAIT",
    "RETRY_MIN_WAIT",
    "VALID_LLM_PROVIDERS",
    "_GEMINI_QUOTA_USER_MESSAGE",
    "_exception_chain_text",
    "_text_indicates_gemini_quota_exhausted",
    "check_gemini_health",
    "check_llm_health",
    "close_gemini_client",
    "close_llm_client",
    "get_gemini_client",
    "get_llm_client",
    "is_llm_quota_or_rate_limit_exception",
    "reset_gemini_client",
    "reset_llm_client",
    "user_facing_message_from_llm_exception",
]
