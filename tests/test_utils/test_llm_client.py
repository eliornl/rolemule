"""Tests for utils/llm_client.py."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.llm_client import (
    GeminiClient,
    GeminiError,
    check_gemini_health,
    close_gemini_client,
    get_gemini_client,
    is_llm_quota_or_rate_limit_exception,
    reset_gemini_client,
    user_facing_message_from_llm_exception,
    _GEMINI_QUOTA_USER_MESSAGE,
    _exception_chain_text,
    _text_indicates_gemini_quota_exhausted,
)


@pytest.fixture(autouse=True)
def reset_client():
    reset_gemini_client()
    yield
    reset_gemini_client()


def test_gemini_error_repr() -> None:
    err = GeminiError("msg", status_code=429, original_error=ValueError("inner"))
    assert "429" in repr(err)


def test_text_indicates_gemini_quota_exhausted() -> None:
    assert _text_indicates_gemini_quota_exhausted("429 RESOURCE_EXHAUSTED")
    assert _text_indicates_gemini_quota_exhausted("You exceeded your current quota")
    assert not _text_indicates_gemini_quota_exhausted("connection reset")


def test_user_facing_message_quota() -> None:
    assert user_facing_message_from_llm_exception(RuntimeError("RESOURCE_EXHAUSTED")) == _GEMINI_QUOTA_USER_MESSAGE


def test_gemini_client_vertex_fallback_without_project() -> None:
    with patch("utils.llm_client.get_settings") as gs:
        gs.return_value = MagicMock(
            use_vertex_ai=True,
            vertex_ai_project=None,
            vertex_ai_location="us-central1",
            gemini_model="gemini-2.5-flash",
            gemini_api_key=None,
        )
        client = GeminiClient()
        assert client.use_vertex_ai is False


@pytest.mark.asyncio
async def test_generate_google_ai_no_api_key() -> None:
    with patch("utils.llm_client.get_settings") as gs:
        gs.return_value = MagicMock(
            use_vertex_ai=False,
            gemini_model="gemini-2.5-flash",
            gemini_api_key=None,
        )
        client = GeminiClient()
        with pytest.raises(GeminiError, match="No API key"):
            await client._generate_with_google_ai(prompt="hi")


@pytest.mark.asyncio
async def test_generate_google_ai_success() -> None:
    mock_response = MagicMock()
    mock_response.text = "Hello"
    mock_response.candidates = [MagicMock(finish_reason="FinishReason.STOP")]

    mock_models = MagicMock()
    mock_models.generate_content = MagicMock(return_value=mock_response)
    mock_client = MagicMock()
    mock_client.models = mock_models

    with patch("utils.llm_client.get_settings") as gs, \
         patch("google.genai.Client", return_value=mock_client), \
         patch("google.genai.types.GenerateContentConfig"), \
         patch("google.genai.types.ThinkingConfig"):
        gs.return_value = MagicMock(
            use_vertex_ai=False,
            gemini_model="gemini-2.5-flash",
            gemini_api_key="AIzaSyTestKey12345",
        )
        client = GeminiClient()
        result = await client._generate_with_google_ai(prompt="Say hi", user_api_key="AIzaSyUserKey12345")
        assert result["response"] == "Hello"
        assert result["done"] is True


@pytest.mark.asyncio
async def test_generate_google_ai_timeout() -> None:
    with patch("utils.llm_client.get_settings") as gs, \
         patch("google.genai.Client", return_value=MagicMock()), \
         patch("google.genai.types.GenerateContentConfig"), \
         patch("google.genai.types.ThinkingConfig"), \
         patch("asyncio.wait_for", side_effect=asyncio.TimeoutError("timed out")):
        gs.return_value = MagicMock(
            use_vertex_ai=False,
            gemini_model="gemini-2.5-flash",
            gemini_api_key="AIzaSyTestKey12345",
        )
        client = GeminiClient()
        with pytest.raises(GeminiError):
            await client._generate_with_google_ai(prompt="hi")


@pytest.mark.asyncio
async def test_generate_google_ai_filtered_response() -> None:
    mock_response = MagicMock()
    mock_response.text = "blocked"
    mock_response.candidates = [MagicMock(finish_reason="FinishReason.SAFETY")]

    mock_client = MagicMock()
    mock_client.models.generate_content = MagicMock(return_value=mock_response)

    with patch("utils.llm_client.get_settings") as gs, \
         patch("google.genai.Client", return_value=mock_client), \
         patch("google.genai.types.GenerateContentConfig"), \
         patch("google.genai.types.ThinkingConfig"):
        gs.return_value = MagicMock(
            use_vertex_ai=False,
            gemini_model="gemini-2.5-flash",
            gemini_api_key="AIzaSyTestKey12345",
        )
        client = GeminiClient()
        result = await client._generate_with_google_ai(prompt="bad")
        assert result.get("filtered") is True


@pytest.mark.asyncio
async def test_generate_with_cache_hit() -> None:
    cached = {"response": "cached", "model": "m"}
    with patch("utils.llm_client.get_settings") as gs, \
         patch("utils.cache.get_cached_llm_response", AsyncMock(return_value=cached)):
        gs.return_value = MagicMock(
            use_vertex_ai=False,
            gemini_model="gemini-2.5-flash",
            gemini_api_key="AIzaSyTestKey12345",
        )
        client = GeminiClient()
        result = await client.generate(prompt="p", use_cache=True)
        assert result["from_cache"] is True


@pytest.mark.asyncio
async def test_health_check_byok_only_returns_true() -> None:
    with patch("utils.llm_client.get_settings") as gs:
        gs.return_value = MagicMock(
            use_vertex_ai=False,
            gemini_model="gemini-2.5-flash",
            gemini_api_key=None,
        )
        client = GeminiClient()
        assert await client.health_check() is True


@pytest.mark.asyncio
async def test_health_check_429_is_healthy() -> None:
    with patch("utils.llm_client.get_settings") as gs, \
         patch("google.genai.Client", return_value=MagicMock()), \
         patch("asyncio.wait_for", side_effect=RuntimeError("429 RESOURCE_EXHAUSTED")):
        gs.return_value = MagicMock(
            use_vertex_ai=False,
            gemini_model="gemini-2.5-flash",
            gemini_api_key="AIzaSyTestKey12345",
        )
        client = GeminiClient()
        assert await client.health_check() is True


@pytest.mark.asyncio
async def test_get_gemini_client_singleton() -> None:
    with patch("utils.llm_client.get_settings") as gs:
        gs.return_value = MagicMock(
            use_vertex_ai=False,
            gemini_model="gemini-2.5-flash",
            gemini_api_key=None,
        )
        a = await get_gemini_client()
        b = await get_gemini_client()
        assert a is b


@pytest.mark.asyncio
async def test_check_gemini_health_failure() -> None:
    with patch("utils.llm_client.get_gemini_client", AsyncMock(side_effect=RuntimeError("fail"))):
        assert await check_gemini_health() is False


@pytest.mark.asyncio
async def test_close_gemini_client() -> None:
    with patch("utils.llm_client.get_settings") as gs:
        gs.return_value = MagicMock(
            use_vertex_ai=False,
            gemini_model="gemini-2.5-flash",
            gemini_api_key=None,
        )
        await get_gemini_client()
        await close_gemini_client()
        import utils.llm_client as llm_mod

        assert llm_mod._gemini_client is None


def test_text_indicates_gemini_quota_empty() -> None:
    assert not _text_indicates_gemini_quota_exhausted("")


def test_text_indicates_gemini_quota_free_tier() -> None:
    assert _text_indicates_gemini_quota_exhausted("free_tier_requests quota exceeded")


def test_text_indicates_gemini_quota_429_rate() -> None:
    assert _text_indicates_gemini_quota_exhausted("429 rate limit for generativelanguage")


def test_is_llm_quota_or_rate_limit_exception() -> None:
    assert is_llm_quota_or_rate_limit_exception(RuntimeError("RESOURCE_EXHAUSTED"))


def test_user_facing_message_non_quota() -> None:
    assert user_facing_message_from_llm_exception(ValueError("bad input")) == "bad input"


@pytest.mark.asyncio
async def test_generate_vertex_ai_success() -> None:
    mock_response = MagicMock()
    mock_response.text = "Vertex reply"

    mock_client = MagicMock()
    mock_client.models.generate_content = MagicMock(return_value=mock_response)

    with patch("utils.llm_client.get_settings") as gs, \
         patch("google.genai.Client", return_value=mock_client), \
         patch("google.genai.types.GenerateContentConfig"), \
         patch("google.genai.types.ThinkingConfig"):
        gs.return_value = MagicMock(
            use_vertex_ai=True,
            vertex_ai_project="proj",
            vertex_ai_location="us-central1",
            gemini_model="gemini-2.5-flash",
            gemini_api_key=None,
        )
        client = GeminiClient()
        client.use_vertex_ai = True
        client.vertex_project = "proj"
        result = await client._generate_with_vertex_ai(prompt="hi", system="sys")
        assert result["response"] == "Vertex reply"


@pytest.mark.asyncio
async def test_generate_vertex_ai_text_extract_error() -> None:
    mock_response = MagicMock()
    type(mock_response).text = property(lambda self: (_ for _ in ()).throw(RuntimeError("no text")))

    mock_client = MagicMock()
    mock_client.models.generate_content = MagicMock(return_value=mock_response)

    with patch("utils.llm_client.get_settings") as gs, \
         patch("google.genai.Client", return_value=mock_client), \
         patch("google.genai.types.GenerateContentConfig"), \
         patch("google.genai.types.ThinkingConfig"):
        gs.return_value = MagicMock(
            use_vertex_ai=True,
            vertex_ai_project="proj",
            vertex_ai_location="us-central1",
            gemini_model="gemini-2.5-flash",
        )
        client = GeminiClient()
        client.use_vertex_ai = True
        client.vertex_project = "proj"
        result = await client._generate_with_vertex_ai(prompt="hi")
        assert "Error retrieving response" in result["response"]


@pytest.mark.asyncio
async def test_generate_with_cache_lookup_failure() -> None:
    with patch("utils.llm_client.get_settings") as gs, \
         patch("utils.cache.get_cached_llm_response", AsyncMock(side_effect=RuntimeError("cache fail"))), \
         patch.object(GeminiClient, "_generate_with_retry", AsyncMock(return_value={"response": "ok"})):
        gs.return_value = MagicMock(
            use_vertex_ai=False,
            gemini_model="gemini-2.5-flash",
            gemini_api_key="AIzaSyTestKey12345",
        )
        client = GeminiClient()
        result = await client.generate(prompt="p", use_cache=True)
        assert result["response"] == "ok"


@pytest.mark.asyncio
async def test_generate_with_cache_store_failure() -> None:
    with patch("utils.llm_client.get_settings") as gs, \
         patch("utils.cache.get_cached_llm_response", AsyncMock(return_value=None)), \
         patch("utils.cache.cache_llm_response", AsyncMock(side_effect=RuntimeError("cache fail"))), \
         patch.object(GeminiClient, "_generate_with_retry", AsyncMock(return_value={"response": "ok"})):
        gs.return_value = MagicMock(
            use_vertex_ai=False,
            gemini_model="gemini-2.5-flash",
            gemini_api_key="AIzaSyTestKey12345",
        )
        client = GeminiClient()
        result = await client.generate(prompt="p", use_cache=True)
        assert result["response"] == "ok"


@pytest.mark.asyncio
async def test_generate_with_retry_routes_vertex() -> None:
    with patch("utils.llm_client.get_settings") as gs, \
         patch.object(GeminiClient, "_generate_with_vertex_ai", AsyncMock(return_value={"response": "v"})) as vtx, \
         patch.object(GeminiClient, "_generate_with_google_ai", AsyncMock()) as gai:
        gs.return_value = MagicMock(
            use_vertex_ai=True,
            vertex_ai_project="proj",
            vertex_ai_location="us-central1",
            gemini_model="gemini-2.5-flash",
        )
        client = GeminiClient()
        client.use_vertex_ai = True
        client.vertex_project = "proj"
        result = await client._generate_with_retry(prompt="p")
        assert result["response"] == "v"
        vtx.assert_awaited_once()
        gai.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_google_ai_text_extract_error() -> None:
    mock_response = MagicMock()
    type(mock_response).text = property(lambda self: (_ for _ in ()).throw(RuntimeError("no text")))
    mock_response.candidates = [MagicMock(finish_reason="FinishReason.STOP")]

    mock_client = MagicMock()
    mock_client.models.generate_content = MagicMock(return_value=mock_response)

    with patch("utils.llm_client.get_settings") as gs, \
         patch("google.genai.Client", return_value=mock_client), \
         patch("google.genai.types.GenerateContentConfig"), \
         patch("google.genai.types.ThinkingConfig"):
        gs.return_value = MagicMock(
            use_vertex_ai=False,
            gemini_model="gemini-2.5-flash",
            gemini_api_key="AIzaSyTestKey12345",
        )
        client = GeminiClient()
        result = await client._generate_with_google_ai(prompt="hi")
        assert "Error retrieving response" in result["response"]


@pytest.mark.asyncio
async def test_gemini_client_logs_vertex_on_init() -> None:
    with patch("utils.llm_client.get_settings") as gs:
        gs.return_value = MagicMock(
            use_vertex_ai=True,
            vertex_ai_project="my-proj",
            vertex_ai_location="us-central1",
            gemini_model="gemini-2.5-flash",
            gemini_api_key=None,
        )
        client = GeminiClient()
        assert client.use_vertex_ai is True


def test_text_indicates_gemini_quota_free_tier_and_quota() -> None:
    assert _text_indicates_gemini_quota_exhausted("free_tier daily quota reached")


@pytest.mark.asyncio
async def test_generate_with_retry_routes_google_ai() -> None:
    with patch("utils.llm_client.get_settings") as gs, \
         patch.object(GeminiClient, "_generate_with_google_ai", AsyncMock(return_value={"response": "g"})) as gai, \
         patch.object(GeminiClient, "_generate_with_vertex_ai", AsyncMock()) as vtx:
        gs.return_value = MagicMock(
            use_vertex_ai=False,
            gemini_model="gemini-2.5-flash",
            gemini_api_key="AIzaSyTestKey12345",
        )
        client = GeminiClient()
        result = await client._generate_with_retry(prompt="p")
        assert result["response"] == "g"
        gai.assert_awaited_once()
        vtx.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_vertex_ai_failure_raises_gemini_error() -> None:
    with patch("utils.llm_client.get_settings") as gs, \
         patch("google.genai.Client", side_effect=RuntimeError("vertex down")):
        gs.return_value = MagicMock(
            use_vertex_ai=True,
            vertex_ai_project="proj",
            vertex_ai_location="us-central1",
            gemini_model="gemini-2.5-flash",
        )
        client = GeminiClient()
        client.use_vertex_ai = True
        client.vertex_project = "proj"
        with pytest.raises(GeminiError, match="Vertex AI generate failed"):
            await client._generate_with_vertex_ai(prompt="hi")


@pytest.mark.asyncio
async def test_health_check_vertex_success() -> None:
    mock_client = MagicMock()
    mock_client.models.get = MagicMock(return_value=MagicMock())
    with patch("utils.llm_client.get_settings") as gs, \
         patch("google.genai.Client", return_value=mock_client), \
         patch("asyncio.wait_for", AsyncMock(return_value=MagicMock())):
        gs.return_value = MagicMock(
            use_vertex_ai=True,
            vertex_ai_project="proj",
            vertex_ai_location="us-central1",
            gemini_model="gemini-2.5-flash",
        )
        client = GeminiClient()
        client.use_vertex_ai = True
        client.vertex_project = "proj"
        assert await client.health_check() is True


@pytest.mark.asyncio
async def test_health_check_google_ai_list_success() -> None:
    mock_client = MagicMock()
    mock_client.models.list = MagicMock(return_value=[])
    with patch("utils.llm_client.get_settings") as gs, \
         patch("google.genai.Client", return_value=mock_client), \
         patch("asyncio.wait_for", AsyncMock(return_value=[])):
        gs.return_value = MagicMock(
            use_vertex_ai=False,
            gemini_model="gemini-2.5-flash",
            gemini_api_key="AIzaSyTestKey12345",
        )
        client = GeminiClient()
        assert await client.health_check() is True


@pytest.mark.asyncio
async def test_health_check_non_quota_failure() -> None:
    with patch("utils.llm_client.get_settings") as gs, \
         patch("google.genai.Client", side_effect=RuntimeError("connection refused")):
        gs.return_value = MagicMock(
            use_vertex_ai=False,
            gemini_model="gemini-2.5-flash",
            gemini_api_key="AIzaSyTestKey12345",
        )
        client = GeminiClient()
        assert await client.health_check() is False


@pytest.mark.asyncio
async def test_check_gemini_health_returns_false_when_unhealthy() -> None:
    mock_client = AsyncMock()
    mock_client.health_check = AsyncMock(return_value=False)
    with patch("utils.llm_client.get_gemini_client", AsyncMock(return_value=mock_client)):
        assert await check_gemini_health() is False


@pytest.mark.asyncio
async def test_generate_google_ai_with_system_prompt() -> None:
    mock_response = MagicMock()
    mock_response.text = "Hello"
    mock_response.candidates = [MagicMock(finish_reason="FinishReason.STOP")]

    mock_client = MagicMock()
    mock_client.models.generate_content = MagicMock(return_value=mock_response)

    with patch("utils.llm_client.get_settings") as gs, \
         patch("google.genai.Client", return_value=mock_client), \
         patch("google.genai.types.GenerateContentConfig"), \
         patch("google.genai.types.ThinkingConfig"):
        gs.return_value = MagicMock(
            use_vertex_ai=False,
            gemini_model="gemini-2.5-flash",
            gemini_api_key="AIzaSyTestKey12345",
        )
        client = GeminiClient()
        result = await client._generate_with_google_ai(
            prompt="Say hi",
            system="You are helpful",
            user_api_key="AIzaSyUserKey12345",
        )
        assert result["response"] == "Hello"


def test_exception_chain_includes_gemini_original_error() -> None:
    inner = RuntimeError("RESOURCE_EXHAUSTED")
    wrapped = GeminiError("outer", original_error=inner)
    text = _exception_chain_text(wrapped)
    assert "RESOURCE_EXHAUSTED" in text


@pytest.mark.asyncio
async def test_check_gemini_health_logs_success_for_server_key() -> None:
    mock_client = AsyncMock()
    mock_client.health_check = AsyncMock(return_value=True)
    mock_client.api_key = "AIzaSyTestKey12345"
    mock_client.use_vertex_ai = False
    with patch("utils.llm_client.get_gemini_client", AsyncMock(return_value=mock_client)):
        assert await check_gemini_health() is True
