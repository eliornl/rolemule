"""OpenAI Chat Completions + Responses (web_search) provider (httpx async)."""

from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Any, AsyncIterator, Dict, List, Optional

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
_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


def _is_openai_new_param_family(model: str) -> bool:
    """
    Return True for models that reject legacy Chat Completions params.

    GPT-5 / o-series require ``max_completion_tokens`` (not ``max_tokens``)
    and typically reject non-default ``temperature``.
    """
    m = (model or "").strip().lower()
    return m.startswith(("gpt-5", "o1", "o3", "o4"))


def _chat_completions_body(
    *,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> Dict[str, Any]:
    """Build a Chat Completions JSON body compatible with the target model."""
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if _is_openai_new_param_family(model):
        # GPT-5 / reasoning: max_tokens → 400; custom temperature often → 400
        payload["max_completion_tokens"] = max_tokens
        if temperature == 1.0:
            payload["temperature"] = temperature
    else:
        payload["temperature"] = temperature
        payload["max_completion_tokens"] = max_tokens
    return payload


def _extract_responses_text(data: Dict[str, Any]) -> str:
    """Pull assistant text from a Responses API payload."""
    direct = data.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct

    parts: List[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message":
            for block in item.get("content") or []:
                if isinstance(block, dict) and block.get("type") in (
                    "output_text",
                    "text",
                ):
                    text = block.get("text") or ""
                    if text:
                        parts.append(text)
    return "".join(parts)


class OpenAIProvider:
    """OpenAI Chat Completions adapter with optional Responses web_search."""

    name: str = "openai"

    def __init__(self) -> None:
        """Load OpenAI settings."""
        settings = get_settings()
        self.api_key: Optional[str] = getattr(settings, "openai_api_key", None)
        self.default_model: str = getattr(settings, "openai_model", "gpt-5.6-luna")
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
        """Call OpenAI chat completions, or Responses + web_search when grounded."""
        effective_key = user_api_key or self.api_key
        if not effective_key:
            raise LLMError(
                "No API key available. Configure OPENAI_API_KEY or provide a user key.",
                provider="openai",
            )

        model_to_use = model or self.default_model
        if use_google_search_grounding:
            return await self._generate_with_web_search(
                prompt=prompt,
                model=model_to_use,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=effective_key,
            )

        messages: list[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = _chat_completions_body(
            model=model_to_use,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
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

    async def generate_stream(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        user_api_key: Optional[str] = None,
        use_google_search_grounding: bool = False,
    ) -> AsyncIterator[str]:
        """Stream Chat Completions deltas (grounding falls back to non-stream)."""
        if use_google_search_grounding:
            # Responses+web_search streaming is out of scope; emit full text once
            full = await self.generate(
                prompt,
                model=model,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                user_api_key=user_api_key,
                use_google_search_grounding=True,
            )
            text = full.get("response") or ""
            if text:
                yield text
            return

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
        payload = _chat_completions_body(
            model=model_to_use,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        payload["stream"] = True
        headers = {
            "Authorization": f"Bearer {effective_key}",
            "Content-Type": "application/json",
        }
        logger.info(
            "[LLM] OpenAI stream  model=%s  prompt=%s chars",
            sanitize_log_value(model_to_use),
            sanitize_log_value(len(prompt) + (len(system) if system else 0)),
        )
        api_start = perf_counter()
        total_chars = 0
        try:
            timeout = httpx.Timeout(self.timeout, connect=HTTP_CONNECT_TIMEOUT)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST", _OPENAI_CHAT_URL, json=payload, headers=headers
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")[
                            :500
                        ]
                        raise LLMError(
                            f"OpenAI stream failed ({response.status_code}): {body}",
                            status_code=response.status_code,
                            provider="openai",
                        )
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            logger.debug(
                                "OpenAI stream skip bad JSON: %s",
                                sanitize_log_value(data_str[:80]),
                            )
                            continue
                        choices = data.get("choices") or []
                        if not choices:
                            continue
                        delta = (choices[0].get("delta") or {}).get("content") or ""
                        if delta:
                            total_chars += len(delta)
                            yield delta
            api_duration_ms = (perf_counter() - api_start) * 1000
            logger.info(
                "[LLM] Done stream  %sms  response=%s chars",
                sanitize_log_value(api_duration_ms),
                sanitize_log_value(total_chars),
            )
            structured_logger.log_external_api_call(
                service="openai",
                operation="chat.completions.stream",
                duration_ms=api_duration_ms,
                success=True,
            )
        except LLMError:
            raise
        except Exception as e:
            structured_logger.log_external_api_call(
                service="openai",
                operation="chat.completions.stream",
                duration_ms=0,
                success=False,
                error=str(e),
            )
            logger.error(
                "Error in OpenAI stream: %s",
                sanitize_log_value(str(e)),
                exc_info=True,
            )
            raise LLMError(
                f"OpenAI stream failed: {e}",
                original_error=e if isinstance(e, Exception) else None,
                provider="openai",
            ) from e

    async def _generate_with_web_search(
        self,
        *,
        prompt: str,
        model: str,
        system: Optional[str],
        temperature: float,
        max_tokens: int,
        api_key: str,
    ) -> Dict[str, Any]:
        """Use Responses API with hosted web_search tool."""
        input_items: List[Dict[str, Any]] = []
        if system:
            input_items.append({"role": "system", "content": system})
        input_items.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": model,
            "input": input_items,
            "tools": [{"type": "web_search"}],
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        logger.info(
            "[LLM] OpenAI Responses+web_search  model=%s  prompt=%s chars",
            sanitize_log_value(model),
            sanitize_log_value(len(prompt) + (len(system) if system else 0)),
        )

        api_start = perf_counter()
        try:
            timeout = httpx.Timeout(self.timeout, connect=HTTP_CONNECT_TIMEOUT)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    _OPENAI_RESPONSES_URL, json=payload, headers=headers
                )
            api_duration_ms = (perf_counter() - api_start) * 1000

            if response.status_code >= 400:
                body = response.text[:500]
                raise LLMError(
                    f"OpenAI Responses failed ({response.status_code}): {body}",
                    status_code=response.status_code,
                    provider="openai",
                )

            data = response.json()
            text = _extract_responses_text(data)
            if not text:
                raise LLMError(
                    "OpenAI Responses failed: empty output_text",
                    provider="openai",
                )
            logger.info(
                "[LLM] Done  %sms  response=%s chars",
                sanitize_log_value(api_duration_ms),
                sanitize_log_value(len(text)),
            )
            structured_logger.log_external_api_call(
                service="openai",
                operation="responses.web_search",
                duration_ms=api_duration_ms,
                success=True,
            )
            return as_generate_result(response=text, model=model)

        except LLMError:
            raise
        except Exception as e:
            structured_logger.log_external_api_call(
                service="openai",
                operation="responses.web_search",
                duration_ms=0,
                success=False,
                error=str(e),
            )
            logger.error(
                "Error in OpenAI Responses generate: %s",
                sanitize_log_value(str(e)),
                exc_info=True,
            )
            raise LLMError(
                f"OpenAI Responses generate failed: {e}",
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
