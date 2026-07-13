"""Gemini provider — Google AI Studio (BYOK) and optional Vertex AI."""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Any, Dict, Optional

from config.settings import get_settings
from utils.llm.constants import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT,
    DEFAULT_TOP_K,
    DEFAULT_TOP_P,
)
from utils.llm.errors import LLMError
from utils.llm.types import as_generate_result
from utils.logging_config import get_structured_logger, sanitize_log_value

logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)


class GeminiProvider:
    """
    Gemini backend adapter.

    Supports:
    1. Vertex AI (USE_VERTEX_AI=true) — ADC auth, higher rate limits
    2. Google AI Studio — API key / BYOK
    """

    name: str = "gemini"

    def __init__(self) -> None:
        """Load Gemini / Vertex settings and select the active backend."""
        settings = get_settings()
        self.timeout = DEFAULT_TIMEOUT
        self.use_vertex_ai = bool(getattr(settings, "use_vertex_ai", False))
        self.vertex_project = getattr(settings, "vertex_ai_project", None)
        self.vertex_location = getattr(settings, "vertex_ai_location", "us-central1")
        self.api_key = getattr(settings, "gemini_api_key", None)

        if self.use_vertex_ai and not self.vertex_project:
            logger.warning(
                "USE_VERTEX_AI=true but VERTEX_AI_PROJECT not set. "
                "Falling back to Google AI Studio."
            )
            self.use_vertex_ai = False

        if self.use_vertex_ai:
            logger.info(
                "[LLM] Ready  model=%s  backend=Vertex AI  project=%s  location=%s",
                sanitize_log_value(settings.gemini_model),
                sanitize_log_value(self.vertex_project),
                sanitize_log_value(self.vertex_location),
            )
        else:
            logger.info(
                "[LLM] Ready  model=%s  backend=Google AI Studio  BYOK=%s",
                sanitize_log_value(settings.gemini_model),
                sanitize_log_value(
                    "enabled (server key set)" if self.api_key else "user-key only"
                ),
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
        """Route to Vertex AI or Google AI Studio."""
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

    @staticmethod
    def _build_generate_config(
        *,
        temperature: float,
        max_tokens: int,
        use_google_search_grounding: bool,
    ) -> Any:
        """Build GenerateContentConfig with thinking disabled and optional Search."""
        from google.genai import types

        config_kwargs: Dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
            "top_p": DEFAULT_TOP_P,
            "top_k": DEFAULT_TOP_K,
            "thinking_config": types.ThinkingConfig(thinking_budget=0),
        }
        if use_google_search_grounding:
            config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
        return types.GenerateContentConfig(**config_kwargs)

    async def _generate_with_vertex_ai(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        use_google_search_grounding: bool = False,
    ) -> Dict[str, Any]:
        """Generate using Vertex AI with ADC authentication."""
        try:
            from google import genai as google_genai

            current_settings = get_settings()
            model_to_use = model or current_settings.gemini_model
            client = google_genai.Client(
                vertexai=True,
                project=self.vertex_project,
                location=self.vertex_location,
            )
            combined_prompt = f"{system}\n\n{prompt}" if system else prompt
            config = self._build_generate_config(
                temperature=temperature,
                max_tokens=max_tokens,
                use_google_search_grounding=use_google_search_grounding,
            )
            prompt_chars = len(combined_prompt)
            logger.info(
                "[LLM] Vertex AI  model=%s  prompt=%s chars  temp=%s  grounding=%s",
                sanitize_log_value(model_to_use),
                sanitize_log_value(prompt_chars),
                sanitize_log_value(temperature),
                sanitize_log_value(use_google_search_grounding),
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
                response_text = response.text
            except Exception as text_error:
                logger.error(
                    "[LLM] Failed to extract response text: %s",
                    sanitize_log_value(str(text_error)),
                    exc_info=True,
                )
                response_text = "Error retrieving response. Please try again."

            logger.info(
                "[LLM] Done  %sms  response=%s chars",
                sanitize_log_value(api_duration_ms),
                sanitize_log_value(len(response_text)),
            )
            structured_logger.log_external_api_call(
                service="vertex_ai",
                operation="generate_content",
                duration_ms=api_duration_ms,
                success=True,
            )
            return as_generate_result(response=response_text, model=model_to_use)

        except Exception as e:
            structured_logger.log_external_api_call(
                service="vertex_ai",
                operation="generate_content",
                duration_ms=0,
                success=False,
                error=str(e),
            )
            logger.error(
                "Error in Vertex AI generate: %s",
                sanitize_log_value(str(e)),
                exc_info=True,
            )
            raise LLMError(
                f"Vertex AI generate failed: {str(e)}",
                original_error=e,
                provider="gemini",
            ) from e

    async def _generate_with_google_ai(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        user_api_key: Optional[str] = None,
        use_google_search_grounding: bool = False,
    ) -> Dict[str, Any]:
        """Generate using Google AI Studio (BYOK / server key)."""
        try:
            from google import genai as google_genai

            current_settings = get_settings()
            effective_api_key = user_api_key or self.api_key
            if not effective_api_key:
                raise LLMError(
                    "No API key available. Please configure your Gemini API key in Settings.",
                    provider="gemini",
                )

            client = google_genai.Client(api_key=effective_api_key)
            model_to_use = model or current_settings.gemini_model
            combined_prompt = f"{system}\n\n{prompt}" if system else prompt
            config = self._build_generate_config(
                temperature=temperature,
                max_tokens=max_tokens,
                use_google_search_grounding=use_google_search_grounding,
            )
            prompt_chars = len(combined_prompt)
            byok_label = "  byok=user-key" if user_api_key else ""
            logger.info(
                "[LLM] Google AI Studio  model=%s  prompt=%s chars  temp=%s  grounding=%s%s",
                sanitize_log_value(model_to_use),
                sanitize_log_value(prompt_chars),
                sanitize_log_value(temperature),
                sanitize_log_value(use_google_search_grounding),
                sanitize_log_value(byok_label),
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
                logger.error(
                    "[LLM] Failed to extract response text: %s",
                    sanitize_log_value(str(text_error)),
                    exc_info=True,
                )
                response_text = (
                    "Error retrieving response from Gemini API. Please try again."
                )

            filtered = False
            if hasattr(response, "candidates") and response.candidates:
                finish_reason = getattr(response.candidates[0], "finish_reason", None)
                if finish_reason and str(finish_reason) not in (
                    "FinishReason.STOP",
                    "FinishReason.MAX_TOKENS",
                    "1",
                    "2",
                ):
                    filtered = True

            logger.info(
                "[LLM] Done  %sms  response=%s chars",
                sanitize_log_value(api_duration_ms),
                sanitize_log_value(len(response_text)),
            )
            structured_logger.log_external_api_call(
                service="gemini",
                operation="generate_content",
                duration_ms=api_duration_ms,
                success=True,
            )

            if filtered:
                logger.warning(
                    "[LLM] Content filtered by safety settings  model=%s",
                    sanitize_log_value(str(model_to_use)),
                )
                return as_generate_result(
                    response=(
                        "The content generation was blocked by safety filters. "
                        "Please try with different input or contact support."
                    ),
                    model=model_to_use,
                    filtered=True,
                )

            return as_generate_result(response=response_text, model=model_to_use)

        except LLMError:
            raise
        except Exception as e:
            structured_logger.log_external_api_call(
                service="gemini",
                operation="generate_content",
                duration_ms=0,
                success=False,
                error=str(e),
            )
            logger.error(
                "Error in Gemini generate: %s",
                sanitize_log_value(str(e)),
                exc_info=True,
            )
            raise LLMError(
                f"Generate failed: {str(e)}",
                original_error=e,
                provider="gemini",
            ) from e

    async def health_check(self) -> bool:
        """Quota-free metadata check; 429 counts as healthy."""
        try:
            if self.use_vertex_ai:
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
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                logger.info(
                    "Gemini health check: quota limit hit but service is reachable"
                )
                return True
            logger.warning(
                "Gemini health check failed: %s", sanitize_log_value(str(e))
            )
            return False
