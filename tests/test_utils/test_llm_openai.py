"""Unit tests for OpenAI provider adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.llm.errors import LLMError
from utils.llm.providers.openai import OpenAIProvider


def _settings(**overrides):
    base = dict(
        openai_api_key="sk-test-key",
        openai_model="gpt-5.6-luna",
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
        assert result["model"] == "gpt-5.6-luna"
        payload = mock_client.post.call_args[1]["json"]
        assert "max_tokens" not in payload
        assert payload["max_completion_tokens"] == 16000
        assert "temperature" not in payload


@pytest.mark.asyncio
async def test_openai_legacy_model_keeps_temperature() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(
        return_value={"choices": [{"message": {"content": "ok"}}]}
    )
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "utils.llm.providers.openai.get_settings",
        return_value=_settings(openai_model="gpt-4o"),
    ), patch("utils.llm.providers.openai.httpx.AsyncClient", return_value=mock_client):
        provider = OpenAIProvider()
        await provider.generate(prompt="hi", temperature=0.3, max_tokens=500)
        payload = mock_client.post.call_args[1]["json"]
        assert payload["temperature"] == 0.3
        assert payload["max_completion_tokens"] == 500
        assert "max_tokens" not in payload


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


@pytest.mark.asyncio
async def test_openai_transport_error_raises() -> None:
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=RuntimeError("network down"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "utils.llm.providers.openai.get_settings", return_value=_settings()
    ), patch("utils.llm.providers.openai.httpx.AsyncClient", return_value=mock_client):
        provider = OpenAIProvider()
        with pytest.raises(LLMError, match="network down"):
            await provider.generate(prompt="hi")


@pytest.mark.asyncio
async def test_openai_health_check_paths() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "utils.llm.providers.openai.get_settings", return_value=_settings()
    ), patch("utils.llm.providers.openai.httpx.AsyncClient", return_value=mock_client):
        assert await OpenAIProvider().health_check() is True

    mock_response.status_code = 429
    with patch(
        "utils.llm.providers.openai.get_settings", return_value=_settings()
    ), patch("utils.llm.providers.openai.httpx.AsyncClient", return_value=mock_client):
        assert await OpenAIProvider().health_check() is True

    mock_client.get = AsyncMock(side_effect=RuntimeError("down"))
    with patch(
        "utils.llm.providers.openai.get_settings", return_value=_settings()
    ), patch("utils.llm.providers.openai.httpx.AsyncClient", return_value=mock_client):
        assert await OpenAIProvider().health_check() is False
