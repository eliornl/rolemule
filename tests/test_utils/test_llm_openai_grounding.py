"""Unit tests for OpenAI Responses web_search grounding path."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.llm.providers.openai import OpenAIProvider, _extract_responses_text


def _settings(**overrides):
    base = dict(
        openai_api_key="sk-test-key",
        openai_model="gpt-5.6-luna",
    )
    base.update(overrides)
    return MagicMock(**base)


def test_extract_responses_text_direct() -> None:
    assert _extract_responses_text({"output_text": "hello"}) == "hello"


def test_extract_responses_text_from_output_blocks() -> None:
    data = {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "part1"}, {"type": "text", "text": "part2"}],
            }
        ]
    }
    assert _extract_responses_text(data) == "part1part2"


@pytest.mark.asyncio
async def test_openai_grounding_uses_responses_api() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"output_text": "grounded answer"})

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "utils.llm.providers.openai.get_settings", return_value=_settings()
    ), patch("utils.llm.providers.openai.httpx.AsyncClient", return_value=mock_client):
        provider = OpenAIProvider()
        result = await provider.generate(
            prompt="research Acme",
            system="sys",
            use_google_search_grounding=True,
            user_api_key="sk-user-key-1234567890",
        )

    assert result["response"] == "grounded answer"
    assert result["done"] is True
    call_kwargs = mock_client.post.call_args
    url = call_kwargs[0][0]
    payload = call_kwargs[1]["json"]
    assert url.endswith("/v1/responses")
    assert payload["tools"] == [{"type": "web_search"}]
    assert call_kwargs[1]["headers"]["Authorization"] == "Bearer sk-user-key-1234567890"


@pytest.mark.asyncio
async def test_openai_grounding_http_error() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "fail"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "utils.llm.providers.openai.get_settings", return_value=_settings()
    ), patch("utils.llm.providers.openai.httpx.AsyncClient", return_value=mock_client):
        from utils.llm.errors import LLMError

        provider = OpenAIProvider()
        with pytest.raises(LLMError, match="Responses failed"):
            await provider.generate(prompt="hi", use_google_search_grounding=True)


@pytest.mark.asyncio
async def test_openai_grounding_empty_text() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"output_text": ""})

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "utils.llm.providers.openai.get_settings", return_value=_settings()
    ), patch("utils.llm.providers.openai.httpx.AsyncClient", return_value=mock_client):
        from utils.llm.errors import LLMError

        provider = OpenAIProvider()
        with pytest.raises(LLMError, match="empty"):
            await provider.generate(prompt="hi", use_google_search_grounding=True)


@pytest.mark.asyncio
async def test_openai_grounding_transport_error() -> None:
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=RuntimeError("net"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "utils.llm.providers.openai.get_settings", return_value=_settings()
    ), patch("utils.llm.providers.openai.httpx.AsyncClient", return_value=mock_client):
        from utils.llm.errors import LLMError

        provider = OpenAIProvider()
        with pytest.raises(LLMError, match="net"):
            await provider.generate(prompt="hi", use_google_search_grounding=True)
