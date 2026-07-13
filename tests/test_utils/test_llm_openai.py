"""Unit tests for OpenAI provider adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.llm.errors import LLMError
from utils.llm.providers.openai import OpenAIProvider


def _settings(**overrides):
    base = dict(
        openai_api_key="sk-test-key",
        openai_model="gpt-4o-mini",
    )
    base.update(overrides)
    return MagicMock(**base)


@pytest.mark.asyncio
async def test_openai_generate_success() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(
        return_value={
            "choices": [{"message": {"content": "hello from openai"}}],
        }
    )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "utils.llm.providers.openai.get_settings", return_value=_settings()
    ), patch("utils.llm.providers.openai.httpx.AsyncClient", return_value=mock_client):
        provider = OpenAIProvider()
        result = await provider.generate(prompt="hi", system="sys")
        assert result["response"] == "hello from openai"
        assert result["done"] is True
        assert result["model"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_openai_missing_key_raises() -> None:
    with patch(
        "utils.llm.providers.openai.get_settings",
        return_value=_settings(openai_api_key=None),
    ):
        provider = OpenAIProvider()
        with pytest.raises(LLMError, match="No API key"):
            await provider.generate(prompt="hi")


@pytest.mark.asyncio
async def test_openai_http_error_raises() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.text = "rate_limit exceeded openai"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "utils.llm.providers.openai.get_settings", return_value=_settings()
    ), patch("utils.llm.providers.openai.httpx.AsyncClient", return_value=mock_client):
        provider = OpenAIProvider()
        with pytest.raises(LLMError, match="429"):
            await provider.generate(prompt="hi")


@pytest.mark.asyncio
async def test_openai_health_check_no_key() -> None:
    with patch(
        "utils.llm.providers.openai.get_settings",
        return_value=_settings(openai_api_key=None),
    ):
        provider = OpenAIProvider()
        assert await provider.health_check() is True
