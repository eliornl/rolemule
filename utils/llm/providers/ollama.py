"""Ollama local / self-hosted chat provider (httpx async)."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Dict, Optional
from urllib.parse import urljoin

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


class OllamaProvider:
    """
    Ollama chat adapter using the native `/api/chat` endpoint.

    Designed for local or self-hosted instances. No API key required by default.
    """

    name: str = "ollama"

    def __init__(self) -> None:
        """Load Ollama base URL and default model."""
        settings = get_settings()
        base = getattr(settings, "ollama_base_url", None) or "http://127.0.0.1:11434"
        self.base_url: str = base.rstrip("/") + "/"
        self.default_model: str = getattr(settings, "ollama_model", "qwen3.6")
        self.timeout = DEFAULT_TIMEOUT
        logger.info(
            "[LLM] Ready  model=%s  backend=Ollama  base_url=%s",
            sanitize_log_value(self.default_model),
            sanitize_log_value(self.base_url),
        )

    def _url(self, path: str) -> str:
        return urljoin(self.base_url, path.lstrip("/"))

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
        """Call Ollama /api/chat (non-streaming)."""
        if use_google_search_grounding:
            logger.debug(
                "Google Search grounding requested but not supported by Ollama; ignoring"
            )
        _ = user_api_key  # unused — Ollama typically has no key

        model_to_use = model or self.default_model
        messages: list[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model_to_use,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        logger.info(
            "[LLM] Ollama  model=%s  prompt=%s chars  temp=%s",
            sanitize_log_value(model_to_use),
            sanitize_log_value(len(prompt) + (len(system) if system else 0)),
            sanitize_log_value(temperature),
        )

        api_start = perf_counter()
        try:
            timeout = httpx.Timeout(self.timeout, connect=HTTP_CONNECT_TIMEOUT)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(self._url("api/chat"), json=payload)
            api_duration_ms = (perf_counter() - api_start) * 1000

            if response.status_code >= 400:
                body = response.text[:500]
                raise LLMError(
                    f"Ollama generate failed ({response.status_code}): {body}",
                    status_code=response.status_code,
                    provider="ollama",
                )

            data = response.json()
            message = data.get("message") or {}
            text = message.get("content") or ""
            logger.info(
                "[LLM] Done  %sms  response=%s chars",
                sanitize_log_value(api_duration_ms),
                sanitize_log_value(len(text)),
            )
            structured_logger.log_external_api_call(
                service="ollama",
                operation="api/chat",
                duration_ms=api_duration_ms,
                success=True,
            )
            return as_generate_result(response=text, model=model_to_use)

        except LLMError:
            raise
        except Exception as e:
            structured_logger.log_external_api_call(
                service="ollama",
                operation="api/chat",
                duration_ms=0,
                success=False,
                error=str(e),
            )
            logger.error(
                "Error in Ollama generate: %s",
                sanitize_log_value(str(e)),
                exc_info=True,
            )
            raise LLMError(
                f"Ollama generate failed: {e}",
                original_error=e if isinstance(e, Exception) else None,
                provider="ollama",
            ) from e

    async def health_check(self) -> bool:
        """GET /api/tags — confirms the daemon is reachable."""
        try:
            timeout = httpx.Timeout(10.0, connect=HTTP_CONNECT_TIMEOUT)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(self._url("api/tags"))
            return response.status_code < 500
        except Exception as e:
            logger.warning(
                "Ollama health check failed: %s", sanitize_log_value(str(e))
            )
            return False
