"""Facade routing: generate(..., provider=) selects the right adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.llm.client import LLMClient
from utils.llm.types import as_generate_result


@pytest.mark.asyncio
async def test_generate_routes_to_explicit_provider() -> None:
    openai_provider = MagicMock()
    openai_provider.name = "openai"
    openai_provider.generate = AsyncMock(
        return_value=as_generate_result(response="from-openai", model="gpt-5.6-luna")
    )

    gemini_provider = MagicMock()
    gemini_provider.name = "gemini"
    gemini_provider.generate = AsyncMock(
        return_value=as_generate_result(response="from-gemini", model="gemini-3.5-flash")
    )

    settings = MagicMock(llm_provider="gemini")
    with patch("utils.llm.client.get_settings", return_value=settings), patch(
        "utils.llm.client.create_provider",
        side_effect=lambda name: gemini_provider if name == "gemini" else openai_provider,
    ):
        client = LLMClient(provider=gemini_provider)
        result = await client.generate(
            prompt="hi",
            provider="openai",
            user_api_key="sk-test",
        )

    assert result["response"] == "from-openai"
    openai_provider.generate.assert_awaited_once()
    gemini_provider.generate.assert_not_awaited()
