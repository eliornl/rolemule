"""Unit tests for provider generate_stream + LLMClient.generate_stream."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.llm.client import LLMClient
from utils.llm.errors import LLMError
from utils.llm.providers.anthropic import AnthropicProvider
from utils.llm.providers.gemini import GeminiProvider
from utils.llm.providers.ollama import OllamaProvider
from utils.llm.providers.openai import OpenAIProvider


def _settings(**overrides: Any) -> MagicMock:
    base = dict(
        openai_api_key="sk-test",
        openai_model="gpt-test",
        anthropic_api_key="sk-ant-test",
        anthropic_model="claude-test",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen3",
        gemini_api_key="Gsk_test_dummy_key_shape_123456789012345678901234567890",
        gemini_model="gemini-test",
        use_vertex_ai=False,
        vertex_ai_project=None,
        vertex_ai_location="us-central1",
        llm_provider="gemini",
    )
    base.update(overrides)
    return MagicMock(**base)


class _FakeStreamResponse:
    def __init__(self, lines: List[str], status_code: int = 200, error_body: bytes = b"err"):
        self.status_code = status_code
        self._lines = lines
        self._error_body = error_body

    async def aiter_lines(self) -> AsyncIterator[str]:
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return self._error_body

    async def __aenter__(self) -> "_FakeStreamResponse":
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False


def _mock_async_client_with_stream(stream_resp: _FakeStreamResponse) -> AsyncMock:
    client = AsyncMock()
    client.stream = MagicMock(return_value=stream_resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.mark.asyncio
async def test_openai_generate_stream_deltas() -> None:
    lines = [
        'data: {"choices":[{"delta":{"content":"Hel"}}]}',
        'data: {"choices":[{"delta":{"content":"lo"}}]}',
        "data: [DONE]",
    ]
    client = _mock_async_client_with_stream(_FakeStreamResponse(lines))
    with patch(
        "utils.llm.providers.openai.get_settings", return_value=_settings()
    ), patch(
        "utils.llm.providers.openai.httpx.AsyncClient", return_value=client
    ):
        provider = OpenAIProvider()
        chunks = [c async for c in provider.generate_stream(prompt="hi", system="sys")]
    assert "".join(chunks) == "Hello"


@pytest.mark.asyncio
async def test_openai_generate_stream_http_error() -> None:
    client = _mock_async_client_with_stream(
        _FakeStreamResponse([], status_code=500, error_body=b"boom")
    )
    with patch(
        "utils.llm.providers.openai.get_settings", return_value=_settings()
    ), patch(
        "utils.llm.providers.openai.httpx.AsyncClient", return_value=client
    ):
        provider = OpenAIProvider()
        with pytest.raises(LLMError, match="500"):
            async for _ in provider.generate_stream(prompt="hi"):
                pass


@pytest.mark.asyncio
async def test_openai_generate_stream_grounding_fallback() -> None:
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.api_key = "sk-test"
    provider.default_model = "gpt-test"
    provider.timeout = 30
    provider.generate = AsyncMock(return_value={"response": "full", "model": "gpt-test"})
    chunks = [
        c
        async for c in provider.generate_stream(
            prompt="hi", use_google_search_grounding=True
        )
    ]
    assert chunks == ["full"]
    provider.generate.assert_awaited()


@pytest.mark.asyncio
async def test_anthropic_generate_stream_deltas() -> None:
    lines = [
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hi"}}',
        'data: {"type":"message_stop"}',
    ]
    client = _mock_async_client_with_stream(_FakeStreamResponse(lines))
    with patch(
        "utils.llm.providers.anthropic.get_settings", return_value=_settings()
    ), patch(
        "utils.llm.providers.anthropic.httpx.AsyncClient", return_value=client
    ):
        provider = AnthropicProvider()
        chunks = [c async for c in provider.generate_stream(prompt="hi", system="sys")]
    assert "".join(chunks) == "Hi"


@pytest.mark.asyncio
async def test_anthropic_generate_stream_http_error() -> None:
    client = _mock_async_client_with_stream(
        _FakeStreamResponse([], status_code=429, error_body=b"rate")
    )
    with patch(
        "utils.llm.providers.anthropic.get_settings", return_value=_settings()
    ), patch(
        "utils.llm.providers.anthropic.httpx.AsyncClient", return_value=client
    ):
        provider = AnthropicProvider()
        with pytest.raises(LLMError, match="429"):
            async for _ in provider.generate_stream(prompt="hi"):
                pass


@pytest.mark.asyncio
async def test_anthropic_generate_stream_grounding_fallback() -> None:
    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.api_key = "sk-ant-test"
    provider.default_model = "claude-test"
    provider.timeout = 30
    provider.generate = AsyncMock(return_value={"response": "grounded", "model": "claude-test"})
    chunks = [
        c
        async for c in provider.generate_stream(
            prompt="hi", use_google_search_grounding=True
        )
    ]
    assert chunks == ["grounded"]


@pytest.mark.asyncio
async def test_ollama_generate_stream_deltas() -> None:
    lines = [
        json.dumps({"message": {"content": "a"}, "done": False}),
        json.dumps({"message": {"content": "b"}, "done": True}),
    ]
    client = _mock_async_client_with_stream(_FakeStreamResponse(lines))
    with patch(
        "utils.llm.providers.ollama.get_settings", return_value=_settings()
    ), patch(
        "utils.llm.providers.ollama.httpx.AsyncClient", return_value=client
    ):
        provider = OllamaProvider()
        chunks = [c async for c in provider.generate_stream(prompt="hi", system="sys")]
    assert "".join(chunks) == "ab"


@pytest.mark.asyncio
async def test_ollama_generate_stream_http_error() -> None:
    client = _mock_async_client_with_stream(
        _FakeStreamResponse([], status_code=502, error_body=b"bad gateway")
    )
    with patch(
        "utils.llm.providers.ollama.get_settings", return_value=_settings()
    ), patch(
        "utils.llm.providers.ollama.httpx.AsyncClient", return_value=client
    ):
        provider = OllamaProvider()
        with pytest.raises(LLMError, match="502"):
            async for _ in provider.generate_stream(prompt="hi"):
                pass


@pytest.mark.asyncio
async def test_gemini_generate_stream_google_ai() -> None:
    with patch(
        "utils.llm.providers.gemini.get_settings", return_value=_settings()
    ):
        provider = GeminiProvider()

    async def _fake_stream(**_kwargs: Any) -> AsyncIterator[str]:
        yield "one"
        yield "two"

    with patch.object(provider, "_stream_google_ai", _fake_stream):
        chunks = [c async for c in provider.generate_stream(prompt="hi", system="sys")]
    assert chunks == ["one", "two"]


@pytest.mark.asyncio
async def test_gemini_stream_sync_iterator() -> None:
    with patch(
        "utils.llm.providers.gemini.get_settings", return_value=_settings()
    ):
        provider = GeminiProvider()

    class _Chunk:
        def __init__(self, text: str) -> None:
            self.text = text

    def _factory():
        return iter([_Chunk("A"), _Chunk("B")])

    chunks = [
        c
        async for c in provider._stream_sync_iterator(
            iterator_factory=_factory,
            service="gemini",
            model_to_use="m",
        )
    ]
    assert chunks == ["A", "B"]


@pytest.mark.asyncio
async def test_gemini_stream_sync_iterator_raises() -> None:
    with patch(
        "utils.llm.providers.gemini.get_settings", return_value=_settings()
    ):
        provider = GeminiProvider()

    def _factory():
        raise RuntimeError("stream boom")
        yield  # pragma: no cover

    with pytest.raises(LLMError, match="stream"):
        async for _ in provider._stream_sync_iterator(
            iterator_factory=_factory,
            service="gemini",
            model_to_use="m",
        ):
            pass


@pytest.mark.asyncio
async def test_llm_client_generate_stream_routes() -> None:
    fake_provider = MagicMock()

    async def _gen_stream(*_args: Any, **_kwargs: Any) -> AsyncIterator[str]:
        yield "x"

    fake_provider.generate_stream = _gen_stream
    fake_provider.name = "openai"

    with patch(
        "utils.llm.client.get_settings",
        return_value=_settings(llm_provider="openai"),
    ), patch(
        "utils.llm.client.create_provider", return_value=fake_provider
    ):
        client = LLMClient()
        chunks = [c async for c in client.generate_stream(prompt="hi", provider="openai")]
    assert chunks == ["x"]
