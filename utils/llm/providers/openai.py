"""OpenAI Chat Completions provider (httpx async)."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Dict, Optional

import httpx

from config.settings import get_settings
from utils.llm.constants import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT,
    HTTP_CONNECT_TIMEOUT,
)
from utils.llm.errors import LLMError
from utils.llm.types import as_generate_result
from utils.logging_config import get_structured_logger, sanitize_log_value

logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)

_OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIProvider:
    """OpenAI Chat Completions adapter."""

    name: str = "openai"

    def __init__(self) -> None:
        """Load OpenAI settings."""
        settings = get_settings()
        self.api_key: Optional[str] = getattr(settings, "openai_api_key", None)
        self.default_model: str = getattr(settings, "openai_model", "gpt-4o-mini")
        self.timeout = DEFAULT_TIMEOUT
        logger.info(
            "[LLM] Ready  model=%s  backend=OpenAI  key=%s",
            sanitize_log_value(self.default_model),
            sanitize_log_value("set" if self.api_key else "missing"),
        )

    async def generate(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        user_api_key: Optional[str] = None,
        use_google_search_grounding: bool = False,
    ) -> Dict[str, Any]:
        """Call OpenAI chat completions."""
        if use_google_search_grounding:
            logger.debug(
                "Google Search grounding requested but not supported by OpenAI; ignoring"
            )

        effective_key = user_api_key or self.api_key
        if not effective_key:
            raise LLMError(
                "No API key available. Configure OPENAI_API_KEY or provide a user key.",
                provider="openai",
            )

        model_to_use = model or self.default_model
        messages: list[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model_to_use,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {effective_key}",
            "Content-Type": "application/json",
        }

        logger.info(
            "[LLM] OpenAI  model=%s  prompt=%s chars  temp=%s",
            sanitize_log_value(model_to_use),
            sanitize_log_value(len(prompt) + (len(system) if system else 0)),
            sanitize_log_value(temperature),
        )

        api_start = perf_counter()
        try:
            timeout = httpx.Timeout(self.timeout, connect=HTTP_CONNECT_TIMEOUT)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    _OPENAI_CHAT_URL, json=payload, headers=headers
                )
            api_duration_ms = (perf_counter() - api_start) * 1000

            if response.status_code >= 400:
                body = response.text[:500]
                raise LLMError(
                    f"OpenAI generate failed ({response.status_code}): {body}",
                    status_code=response.status_code,
                    provider="openai",
                )

            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                raise LLMError(
                    "OpenAI generate failed: empty choices",
                    provider="openai",
                )
            text = (choices[0].get("message") or {}).get("content") or ""
            logger.info(
                "[LLM] Done  %sms  response=%s chars",
                sanitize_log_value(api_duration_ms),
                sanitize_log_value(len(text)),
            )
            structured_logger.log_external_api_call(
                service="openai",
                operation="chat.completions",
                duration_ms=api_duration_ms,
                success=True,
            )
            return as_generate_result(response=text, model=model_to_use)

        except LLMError:
            raise
        except Exception as e:
            structured_logger.log_external_api_call(
                service="openai",
                operation="chat.completions",
                duration_ms=0,
                success=False,
                error=str(e),
            )
            logger.error(
                "Error in OpenAI generate: %s",
                sanitize_log_value(str(e)),
                exc_info=True,
            )
            raise LLMError(
                f"OpenAI generate failed: {e}",
                original_error=e if isinstance(e, Exception) else None,
                provider="openai",
            ) from e

    async def health_check(self) -> bool:
        """List models with the server key; missing key is a no-op success."""
        if not self.api_key:
            return True
        try:
            timeout = httpx.Timeout(10.0, connect=HTTP_CONNECT_TIMEOUT)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            if response.status_code == 429:
                logger.info("OpenAI health check: rate limited but reachable")
                return True
            return response.status_code < 500
        except Exception as e:
            logger.warning(
                "OpenAI health check failed: %s", sanitize_log_value(str(e))
            )
            return False
