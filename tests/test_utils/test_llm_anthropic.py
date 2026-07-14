"""Unit tests for Anthropic provider adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.llm.errors import LLMError
from utils.llm.providers.anthropic import AnthropicProvider


def _settings(**overrides):
    base = dict(
        anthropic_api_key="sk-ant-test",
        anthropic_model="claude-sonnet-5",
    )
    base.update(overrides)
    return MagicMock(**base)


@pytest.mark.asyncio
async def test_anthropic_generate_success() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(
        return_value={
            "content": [{"type": "text", "text": "hello from claude"}],
        }
    )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "utils.llm.providers.anthropic.get_settings", return_value=_settings()
    ), patch(
        "utils.llm.providers.anthropic.httpx.AsyncClient", return_value=mock_client
    ):
        provider = AnthropicProvider()
        result = await provider.generate(prompt="hi", system="sys")
        assert result["response"] == "hello from claude"
        assert result["model"] == "claude-sonnet-5"


@pytest.mark.asyncio
async def test_anthropic_missing_key_raises() -> None:
    with patch(
        "utils.llm.providers.anthropic.get_settings",
        return_value=_settings(anthropic_api_key=None),
    ):
        provider = AnthropicProvider()
        with pytest.raises(LLMError, match="No API key"):
            await provider.generate(prompt="hi")


@pytest.mark.asyncio
async def test_anthropic_health_check_no_key() -> None:
    with patch(
        "utils.llm.providers.anthropic.get_settings",
        return_value=_settings(anthropic_api_key=None),
    ):
        provider = AnthropicProvider()
        assert await provider.health_check() is True
