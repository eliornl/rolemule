"""Unit tests for Ollama provider adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.llm.errors import LLMError
from utils.llm.providers.ollama import OllamaProvider


def _settings(**overrides):
    base = dict(
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen3.6",
    )
    base.update(overrides)
    return MagicMock(**base)


@pytest.mark.asyncio
async def test_ollama_generate_success() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(
        return_value={"message": {"content": "hello from ollama"}}
    )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "utils.llm.providers.ollama.get_settings", return_value=_settings()
    ), patch(
        "utils.llm.providers.ollama.httpx.AsyncClient", return_value=mock_client
    ):
        provider = OllamaProvider()
        result = await provider.generate(prompt="hi", system="sys")
        assert result["response"] == "hello from ollama"
        assert result["model"] == "qwen3.6"


@pytest.mark.asyncio
async def test_ollama_http_error_raises() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "daemon down"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "utils.llm.providers.ollama.get_settings", return_value=_settings()
    ), patch(
        "utils.llm.providers.ollama.httpx.AsyncClient", return_value=mock_client
    ):
        provider = OllamaProvider()
        with pytest.raises(LLMError, match="500"):
            await provider.generate(prompt="hi")


@pytest.mark.asyncio
async def test_ollama_health_check_failure() -> None:
    with patch(
        "utils.llm.providers.ollama.get_settings", return_value=_settings()
    ), patch(
        "utils.llm.providers.ollama.httpx.AsyncClient",
        side_effect=ConnectionError("refused"),
    ):
        provider = OllamaProvider()
        assert await provider.health_check() is False


@pytest.mark.asyncio
async def test_ollama_transport_error() -> None:
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=RuntimeError("daemon down"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "utils.llm.providers.ollama.get_settings", return_value=_settings()
    ), patch(
        "utils.llm.providers.ollama.httpx.AsyncClient", return_value=mock_client
    ):
        provider = OllamaProvider()
        with pytest.raises(LLMError, match="daemon down"):
            await provider.generate(prompt="hi")


@pytest.mark.asyncio
async def test_ollama_health_check_ok_and_fail() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "utils.llm.providers.ollama.get_settings", return_value=_settings()
    ), patch(
        "utils.llm.providers.ollama.httpx.AsyncClient", return_value=mock_client
    ):
        assert await OllamaProvider().health_check() is True

    mock_client.get = AsyncMock(side_effect=RuntimeError("down"))
    with patch(
        "utils.llm.providers.ollama.get_settings", return_value=_settings()
    ), patch(
        "utils.llm.providers.ollama.httpx.AsyncClient", return_value=mock_client
    ):
        assert await OllamaProvider().health_check() is False
