"""Unit tests for Anthropic web_search grounding path."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.llm.providers.anthropic import AnthropicProvider


def _settings(**overrides):
    base = dict(
        anthropic_api_key="sk-ant-test",
        anthropic_model="claude-sonnet-5",
    )
    base.update(overrides)
    return MagicMock(**base)


@pytest.mark.asyncio
async def test_anthropic_grounding_adds_web_search_tool() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(
        return_value={
            "content": [
                {"type": "text", "text": "verified company facts"},
            ]
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
        result = await provider.generate(
            prompt="research Acme",
            use_google_search_grounding=True,
            user_api_key="sk-ant-user-key-1234567890",
        )

    assert result["response"] == "verified company facts"
    payload = mock_client.post.call_args[1]["json"]
    assert payload["tools"][0]["type"] == "web_search_20250305"
    assert payload["tools"][0]["name"] == "web_search"


@pytest.mark.asyncio
async def test_anthropic_without_grounding_omits_tools() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(
        return_value={"content": [{"type": "text", "text": "plain"}]}
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
        await provider.generate(prompt="hi")

    payload = mock_client.post.call_args[1]["json"]
    assert "tools" not in payload
