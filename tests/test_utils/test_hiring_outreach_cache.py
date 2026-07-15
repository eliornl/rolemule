"""
Unit tests for hiring outreach Redis helpers in utils.cache.
"""

from unittest.mock import AsyncMock, patch

import pytest

from utils.cache import (
    CACHE_VERSION,
    CACHE_PREFIX_HIRING_OUTREACH,
    CACHE_PREFIX_HIRING_OUTREACH_GENERATING,
    TTL_HIRING_OUTREACH,
    TTL_HIRING_OUTREACH_GENERATING,
    cache_hiring_outreach,
    clear_hiring_outreach_generating,
    get_cached_hiring_outreach,
    invalidate_hiring_outreach,
    is_hiring_outreach_generating,
    set_hiring_outreach_generating,
)


SESSION_ID = "sess-hiring-outreach-001"


def _generating_key(session_id: str) -> str:
    return f"{CACHE_VERSION}:{CACHE_PREFIX_HIRING_OUTREACH_GENERATING}:{session_id}"


def _cache_key(session_id: str) -> str:
    return f"{CACHE_VERSION}:{CACHE_PREFIX_HIRING_OUTREACH}:{session_id}"


# ---------------------------------------------------------------------------
# Generating lock — set / clear / is
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_generating_claims_lock(mock_redis) -> None:
    mock_redis.set = AsyncMock(return_value=True)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await set_hiring_outreach_generating(SESSION_ID) is True
    mock_redis.set.assert_awaited_once_with(
        _generating_key(SESSION_ID),
        "1",
        nx=True,
        ex=TTL_HIRING_OUTREACH_GENERATING,
    )


@pytest.mark.asyncio
async def test_second_set_generating_returns_false_when_lock_held(mock_redis) -> None:
    mock_redis.set = AsyncMock(return_value=None)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await set_hiring_outreach_generating(SESSION_ID) is False


@pytest.mark.asyncio
async def test_clear_then_reclaim_generating(mock_redis) -> None:
    mock_redis.set = AsyncMock(side_effect=[True, True])
    mock_redis.delete = AsyncMock(return_value=1)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await set_hiring_outreach_generating(SESSION_ID) is True
        assert await clear_hiring_outreach_generating(SESSION_ID) is True
        assert await set_hiring_outreach_generating(SESSION_ID) is True
    mock_redis.delete.assert_awaited_once_with(_generating_key(SESSION_ID))
    assert mock_redis.set.await_count == 2


@pytest.mark.asyncio
async def test_is_generating_true_when_key_present(mock_redis) -> None:
    mock_redis.get = AsyncMock(return_value="1")
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await is_hiring_outreach_generating(SESSION_ID) is True
    mock_redis.get.assert_awaited_once_with(_generating_key(SESSION_ID))


@pytest.mark.asyncio
async def test_is_generating_false_when_key_absent(mock_redis) -> None:
    mock_redis.get = AsyncMock(return_value=None)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await is_hiring_outreach_generating(SESSION_ID) is False


@pytest.mark.asyncio
async def test_generating_paths_without_redis() -> None:
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=None)):
        assert await set_hiring_outreach_generating(SESSION_ID) is True
        assert await clear_hiring_outreach_generating(SESSION_ID) is False
        assert await is_hiring_outreach_generating(SESSION_ID) is False


@pytest.mark.asyncio
async def test_set_generating_redis_error_returns_true(mock_redis) -> None:
    mock_redis.set = AsyncMock(side_effect=RuntimeError("redis down"))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await set_hiring_outreach_generating(SESSION_ID) is True


@pytest.mark.asyncio
async def test_clear_and_is_generating_redis_errors_return_false(mock_redis) -> None:
    mock_redis.delete = AsyncMock(side_effect=RuntimeError("fail"))
    mock_redis.get = AsyncMock(side_effect=RuntimeError("fail"))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await clear_hiring_outreach_generating(SESSION_ID) is False
        assert await is_hiring_outreach_generating(SESSION_ID) is False


# ---------------------------------------------------------------------------
# Result cache — get / cache / invalidate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_cached_returns_none_when_no_data() -> None:
    with patch("utils.cache.cache_get", AsyncMock(return_value=None)):
        assert await get_cached_hiring_outreach(SESSION_ID) is None


@pytest.mark.asyncio
async def test_get_cached_returns_none_when_missing_data_key() -> None:
    with patch("utils.cache.cache_get", AsyncMock(return_value={"cached_at": "t"})):
        assert await get_cached_hiring_outreach(SESSION_ID) is None


@pytest.mark.asyncio
async def test_get_cached_returns_wrapped_payload() -> None:
    wrapped = {
        "data": {"version": "1.0", "contacts": [], "fallback": {}},
        "cached_at": "2026-01-01T00:00:00+00:00",
    }
    with patch("utils.cache.cache_get", AsyncMock(return_value=wrapped)):
        result = await get_cached_hiring_outreach(SESSION_ID)
    assert result == wrapped


@pytest.mark.asyncio
async def test_cache_hiring_outreach_calls_cache_set() -> None:
    payload = {"version": "1.0", "contacts": [], "fallback": {}}
    with patch("utils.cache.cache_set", AsyncMock(return_value=True)) as cache_set:
        ok = await cache_hiring_outreach(SESSION_ID, payload)
    assert ok is True
    cache_set.assert_awaited_once_with(
        _cache_key(SESSION_ID),
        payload,
        TTL_HIRING_OUTREACH,
    )


@pytest.mark.asyncio
async def test_invalidate_hiring_outreach_calls_cache_delete() -> None:
    with patch("utils.cache.cache_delete", AsyncMock(return_value=True)) as cache_delete:
        ok = await invalidate_hiring_outreach(SESSION_ID)
    assert ok is True
    cache_delete.assert_awaited_once_with(_cache_key(SESSION_ID))
