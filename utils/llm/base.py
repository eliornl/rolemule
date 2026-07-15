"""LLM provider protocol — implement for each backend."""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """
    Async provider adapter.

    Implementations must return the stable generate shape and raise LLMError
    (or GeminiError alias) on failure. Sync SDKs must use asyncio.wait_for.
    """

    name: str

    async def generate(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 16000,
        user_api_key: Optional[str] = None,
        use_google_search_grounding: bool = False,
    ) -> Dict[str, Any]:
        """Generate text from the underlying model API."""

    async def generate_stream(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 16000,
        user_api_key: Optional[str] = None,
        use_google_search_grounding: bool = False,
    ) -> AsyncIterator[str]:
        """Yield text deltas as the model generates (no Redis cache)."""

    async def health_check(self) -> bool:
        """Return True when the provider is reachable (quota 429 counts as healthy)."""
