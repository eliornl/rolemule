"""Extended tests for utils/cache.py — stampede locks, invalidation, edge cases."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.cache import (
    _fallback_limiter,
    RateLimitResult,
    acquire_compute_lock,
    cache_get,
    cache_set,
    check_rate_limit,
    check_rate_limit_with_headers,
    get_cache_stats,
    get_cached_cv_optimization,
    get_cached_interview_prep,
    get_login_attempts,
    get_rate_limit_remaining,
    invalidate_all_user_profile_caches_sync,
    invalidate_cv_optimization,
    invalidate_interview_prep,
    invalidate_user_llm_cache,
    release_compute_lock,
)


@pytest.fixture(autouse=True)
def reset_fallback_limiter():
    _fallback_limiter._store.clear()
    yield
    _fallback_limiter._store.clear()


@pytest.mark.asyncio
async def test_acquire_compute_lock_no_redis_fail_open() -> None:
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=None)):
        assert await acquire_compute_lock("job-key") is True


@pytest.mark.asyncio
async def test_acquire_compute_lock_already_locked(mock_redis) -> None:
    mock_redis.set = AsyncMock(return_value=None)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await acquire_compute_lock("busy-key") is False


@pytest.mark.asyncio
async def test_acquire_compute_lock_redis_error_fail_open(mock_redis) -> None:
    mock_redis.set = AsyncMock(side_effect=RuntimeError("redis down"))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await acquire_compute_lock("err-key") is True


@pytest.mark.asyncio
async def test_release_compute_lock_no_redis() -> None:
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=None)):
        assert await release_compute_lock("k") is False


@pytest.mark.asyncio
async def test_release_compute_lock_error(mock_redis) -> None:
    mock_redis.delete = AsyncMock(side_effect=RuntimeError("fail"))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await release_compute_lock("k") is False


@pytest.mark.asyncio
async def test_cache_set_redis_error(mock_redis) -> None:
    mock_redis.set = AsyncMock(side_effect=RuntimeError("fail"))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await cache_set("k", {"a": 1}, ttl=60) is False


@pytest.mark.asyncio
async def test_cache_get_invalid_json(mock_redis) -> None:
    mock_redis.get = AsyncMock(return_value="not-json{")
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await cache_get("k") is None


@pytest.mark.asyncio
async def test_get_cached_interview_prep_hit(mock_redis) -> None:
    wrapped = {"cached_at": "t", "data": {"questions": []}}
    mock_redis.get = AsyncMock(return_value=json.dumps(wrapped))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        result = await get_cached_interview_prep("sid-1")
        assert result["data"]["questions"] == []


@pytest.mark.asyncio
async def test_get_cached_interview_prep_miss(mock_redis) -> None:
    mock_redis.get = AsyncMock(return_value=None)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await get_cached_interview_prep("sid-miss") is None


@pytest.mark.asyncio
async def test_interview_prep_cache_roundtrip(mock_redis) -> None:
    from utils.cache import cache_interview_prep

    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=1)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await cache_interview_prep("sid", {"q": 1}) is True
        assert await invalidate_interview_prep("sid") is True


@pytest.mark.asyncio
async def test_get_cached_cv_optimization_unwraps_data(mock_redis) -> None:
    wrapped = {"cached_at": "t", "data": {"score": 90}}
    mock_redis.get = AsyncMock(return_value=json.dumps(wrapped))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await get_cached_cv_optimization("cv-sid") == {"score": 90}


@pytest.mark.asyncio
async def test_cv_optimization_cache_invalidate(mock_redis) -> None:
    from utils.cache import cache_cv_optimization

    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=1)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await cache_cv_optimization("cv-sid", {"iterations": []}) is True
        assert await invalidate_cv_optimization("cv-sid") is True


@pytest.mark.asyncio
async def test_invalidate_user_llm_cache_scans_and_deletes() -> None:
    mock_redis = AsyncMock()
    mock_redis.scan = AsyncMock(side_effect=[(0, ["v1:llm_response:u1:abc"])])
    mock_redis.delete = AsyncMock(return_value=1)
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_redis)):
        deleted = await invalidate_user_llm_cache("u1")
        assert deleted == 1


@pytest.mark.asyncio
async def test_invalidate_user_llm_cache_no_redis() -> None:
    with patch("utils.cache.get_redis_client", AsyncMock(return_value=None)):
        assert await invalidate_user_llm_cache("u1") == 0


def test_invalidate_all_user_profile_caches_sync_import_error() -> None:
    with patch.dict("sys.modules", {"redis": None}):
        assert invalidate_all_user_profile_caches_sync() == 0


def test_invalidate_all_user_profile_caches_sync_deletes_keys() -> None:
    mock_client = MagicMock()
    mock_client.scan_iter.return_value = iter(["v1:user_profile:1", "v1:user_profile:2"])
    mock_client.delete.return_value = 2
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_client)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("redis.Redis.from_url", return_value=mock_ctx):
        deleted = invalidate_all_user_profile_caches_sync()
        assert deleted == 2


@pytest.mark.asyncio
async def test_check_rate_limit_redis_exception_uses_fallback() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=redis)):
        allowed, remaining = await check_rate_limit("exc:1", limit=5, window_seconds=60)
        assert allowed is True
        assert remaining >= 0


@pytest.mark.asyncio
async def test_check_rate_limit_with_headers_exceeded(mock_redis) -> None:
    mock_redis.get = AsyncMock(return_value="10")
    pipe = MagicMock()
    pipe.get = MagicMock(return_value=pipe)
    pipe.ttl = MagicMock(return_value=pipe)
    pipe.execute = AsyncMock(return_value=["10", 45])
    mock_redis.pipeline = MagicMock(return_value=pipe)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        result = await check_rate_limit_with_headers("u:blocked", limit=5, window_seconds=60)
        assert result.allowed is False
        assert result.remaining == 0


@pytest.mark.asyncio
async def test_check_rate_limit_with_headers_exception_fallback() -> None:
    redis = AsyncMock()
    redis.pipeline = MagicMock(side_effect=RuntimeError("pipe fail"))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=redis)):
        result = await check_rate_limit_with_headers("fb:hdr", limit=3, window_seconds=60)
        assert isinstance(result, RateLimitResult)
        assert result.allowed is True


@pytest.mark.asyncio
async def test_get_rate_limit_remaining_no_redis() -> None:
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=None)):
        assert await get_rate_limit_remaining("id", limit=10) == 10


@pytest.mark.asyncio
async def test_get_rate_limit_remaining_error() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=RuntimeError("fail"))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=redis)):
        assert await get_rate_limit_remaining("id", limit=10) == 10


@pytest.mark.asyncio
async def test_get_login_attempts(mock_redis) -> None:
    mock_redis.get = AsyncMock(return_value="3")
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await get_login_attempts("user@example.com") == 3


@pytest.mark.asyncio
async def test_get_login_attempts_no_redis() -> None:
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=None)):
        assert await get_login_attempts("user@example.com") == 0


@pytest.mark.asyncio
async def test_get_cache_stats_connected(mock_redis) -> None:
    mock_redis.info = AsyncMock(
        side_effect=[
            {"used_memory_human": "1M", "used_memory_peak_human": "2M"},
            {"keyspace_hits": 10, "keyspace_misses": 5, "evicted_keys": 0},
        ]
    )

    async def _scan(*args, **kwargs):
        if False:
            yield None

    mock_redis.scan_iter = _scan
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        stats = await get_cache_stats()
        assert stats["status"] == "connected"
        assert stats["fallback_rate_limiter"] == "standby"
        assert "key_counts" in stats


@pytest.mark.asyncio
async def test_get_cache_stats_error() -> None:
    redis = AsyncMock()
    redis.info = AsyncMock(side_effect=RuntimeError("stats fail"))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=redis)):
        stats = await get_cache_stats()
        assert stats["status"] == "error"


@pytest.mark.asyncio
async def test_get_cached_tool_result_non_dict_evicted(mock_redis) -> None:
    from utils.cache import get_cached_tool_result

    mock_redis.get = AsyncMock(return_value=json.dumps(["not", "a", "dict"]))
    mock_redis.delete = AsyncMock(return_value=1)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await get_cached_tool_result("thank_you", {"x": 1}) is None
        mock_redis.delete.assert_awaited()


@pytest.mark.asyncio
async def test_set_interview_prep_generating_lock_not_acquired(mock_redis) -> None:
    from utils.cache import set_interview_prep_generating

    mock_redis.set = AsyncMock(return_value=None)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await set_interview_prep_generating("s-lock") is False
