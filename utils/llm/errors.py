"""LLM error types and user-facing exception mapping."""

from __future__ import annotations

from typing import List, Optional

# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================


class LLMError(Exception):
    """
    Provider-agnostic LLM failure.

    Attributes:
        message: Human-readable description of the error.
        status_code: HTTP status from the upstream API, if available.
        original_error: Underlying exception, if any.
        provider: Provider name when known (gemini, openai, anthropic, ollama).
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        original_error: Optional[Exception] = None,
        provider: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.original_error = original_error
        self.provider = provider

    def __repr__(self) -> str:
        parts = [f"LLMError({self.message!r}"]
        if self.status_code is not None:
            parts.append(f", status_code={self.status_code}")
        if self.provider is not None:
            parts.append(f", provider={self.provider!r}")
        if self.original_error is not None:
            parts.append(f", original_error={self.original_error!r}")
        return "".join(parts) + ")"


# Backward-compatible alias — existing agents and tests import GeminiError
GeminiError = LLMError


# =============================================================================
# USER-FACING ERROR STRINGS
# =============================================================================

_GEMINI_QUOTA_USER_MESSAGE: str = (
    "The AI quota or rate limit for the configured API key was reached. "
    "Try again in a little while, review your plan and quotas for that key, "
    "or update your key under Settings → AI Setup."
)

_OPENAI_QUOTA_USER_MESSAGE: str = (
    "The OpenAI quota or rate limit for the configured API key was reached. "
    "Try again later, check your OpenAI plan and usage, or update the key."
)

_ANTHROPIC_QUOTA_USER_MESSAGE: str = (
    "The Anthropic quota or rate limit for the configured API key was reached. "
    "Try again later, check your Anthropic plan and usage, or update the key."
)

def _text_indicates_gemini_quota_exhausted(text: str) -> bool:
    """Return True if text looks like a Gemini / Google AI quota or rate-limit response."""
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


def _text_indicates_openai_quota(text: str) -> bool:
    """Return True if text looks like an OpenAI rate-limit / quota error."""
    if not text:
        return False
    lower = text.lower()
    if "insufficient_quota" in lower:
        return True
    if "rate_limit" in lower and ("openai" in lower or "tokens" in lower):
        return True
    if "429" in text and ("openai" in lower or "rate limit" in lower):
        return True
    return False


def _text_indicates_anthropic_quota(text: str) -> bool:
    """Return True if text looks like an Anthropic rate-limit / quota error."""
    if not text:
        return False
    lower = text.lower()
    if "rate_limit" in lower and "anthropic" in lower:
        return True
    if "429" in text and ("anthropic" in lower or "claude" in lower):
        return True
    if "overloaded" in lower and "anthropic" in lower:
        return True
    return False


def _exception_chain_text(exc: BaseException) -> str:
    """Join str() of exc, LLMError.original_error, and __cause__/__context__."""
    parts: List[str] = []
    seen: set[int] = set()
    cur: Optional[BaseException] = exc
    depth = 0
    while cur is not None and id(cur) not in seen and depth < 8:
        seen.add(id(cur))
        parts.append(str(cur))
        if isinstance(cur, LLMError) and cur.original_error is not None:
            inner = cur.original_error
            if id(inner) not in seen:
                parts.append(str(inner))
        nxt = cur.__cause__ if cur.__cause__ is not None else cur.__context__
        cur = nxt
        depth += 1
    return " ".join(parts)


def user_facing_message_from_llm_exception(exc: BaseException) -> str:
    """
    Map an LLM/SDK exception to text safe for workflow error_messages and the dashboard.

    Quota / rate-limit errors become a short, actionable message; everything else
    returns str(exc).
    """
    combined = _exception_chain_text(exc)
    # Provider-specific markers first (avoid Gemini false positives on shared "429"+"quota")
    if _text_indicates_openai_quota(combined):
        return _OPENAI_QUOTA_USER_MESSAGE
    if _text_indicates_anthropic_quota(combined):
        return _ANTHROPIC_QUOTA_USER_MESSAGE
    if _text_indicates_gemini_quota_exhausted(combined):
        return _GEMINI_QUOTA_USER_MESSAGE
    return str(exc)


def is_llm_quota_or_rate_limit_exception(exc: BaseException) -> bool:
    """Return True when an exception looks like any supported provider quota/rate limit."""
    combined = _exception_chain_text(exc)
    return (
        _text_indicates_gemini_quota_exhausted(combined)
        or _text_indicates_openai_quota(combined)
        or _text_indicates_anthropic_quota(combined)
    )
