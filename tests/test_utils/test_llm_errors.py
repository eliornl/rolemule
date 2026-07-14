"""Unit tests for utils.llm.errors."""

from utils.llm.errors import (
    LLMError,
    is_llm_quota_or_rate_limit_exception,
    user_facing_message_from_llm_exception,
)


def test_llm_error_repr_includes_provider_and_original() -> None:
    original = RuntimeError("upstream")
    err = LLMError("quota hit", status_code=429, original_error=original, provider="openai")
    text = repr(err)
    assert "openai" in text
    assert "upstream" in text
    assert "429" in text


def test_user_facing_openai_quota_message() -> None:
    exc = LLMError("insufficient_quota for openai", provider="openai")
    msg = user_facing_message_from_llm_exception(exc)
    assert "OpenAI quota" in msg


def test_user_facing_anthropic_quota_message() -> None:
    exc = LLMError("rate_limit exceeded for anthropic", provider="anthropic")
    msg = user_facing_message_from_llm_exception(exc)
    assert "Anthropic quota" in msg


def test_is_llm_quota_detects_gemini_resource_exhausted() -> None:
    exc = LLMError("RESOURCE_EXHAUSTED", provider="gemini")
    assert is_llm_quota_or_rate_limit_exception(exc) is True


def test_user_facing_non_quota_returns_str() -> None:
    exc = ValueError("plain validation error")
    assert user_facing_message_from_llm_exception(exc) == "plain validation error"


def test_user_facing_gemini_quota_message() -> None:
    exc = LLMError("RESOURCE_EXHAUSTED", provider="gemini")
    msg = user_facing_message_from_llm_exception(exc)
    assert "Gemini" in msg or "quota" in msg.lower()


def test_is_llm_quota_detects_openai_insufficient_quota() -> None:
    exc = LLMError("insufficient_quota", provider="openai")
    assert is_llm_quota_or_rate_limit_exception(exc) is True


def test_is_llm_quota_detects_anthropic_rate_limit() -> None:
    exc = LLMError("rate_limit exceeded anthropic", provider="anthropic")
    assert is_llm_quota_or_rate_limit_exception(exc) is True


def test_is_llm_quota_from_wrapped_openai_exception() -> None:
    inner = Exception("Error code: 429 - rate limit openai")
    exc = LLMError("wrapped", provider="openai", original_error=inner)
    assert is_llm_quota_or_rate_limit_exception(exc) is True


def test_is_llm_quota_from_wrapped_anthropic_overloaded() -> None:
    inner = Exception("anthropic overloaded_error 429")
    exc = LLMError("wrapped", provider="anthropic", original_error=inner)
    assert is_llm_quota_or_rate_limit_exception(exc) is True
