"""Tests for utils/cache.py."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import utils.cache as cache_mod


@pytest.fixture(autouse=True)
def reset_fallback_limiter():
    cache_mod._fallback_limiter._store.clear()
    yield
    cache_mod._fallback_limiter._store.clear()


def test_generate_hash() -> None:
    assert len(cache_mod.generate_hash("hello")) == 64


def test_get_job_cache_key_includes_version() -> None:
    key = cache_mod._get_job_cache_key("https://jobs.example.com/123", "job body text")
    assert cache_mod.CACHE_VERSION in key
    assert "job_analysis" in key


def test_validate_cache_data() -> None:
    assert cache_mod._validate_cache_data("job_analysis", {"company_name": "A", "job_title": "B"})
    assert not cache_mod._validate_cache_data("job_analysis", {"company_name": "A"})


@pytest.mark.asyncio
async def test_cache_get_miss(mock_redis) -> None:
    mock_redis.get = AsyncMock(return_value=None)
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await cache_mod.cache_get("k") is None


@pytest.mark.asyncio
async def test_cache_get_hit(mock_redis) -> None:
    payload = {"cached_at": "now", "data": {"x": 1}}
    mock_redis.get = AsyncMock(return_value=json.dumps(payload))
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await cache_mod.cache_get("k") == payload


@pytest.mark.asyncio
async def test_cache_get_no_redis() -> None:
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=None)):
        assert await cache_mod.cache_get("k") is None


@pytest.mark.asyncio
async def test_cache_get_error() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=RuntimeError("fail"))
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=redis)):
        assert await cache_mod.cache_get("k") is None


@pytest.mark.asyncio
async def test_cache_set_success(mock_redis) -> None:
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await cache_mod.cache_set("k", {"a": 1}, ttl=60) is True
        mock_redis.set.assert_awaited()


@pytest.mark.asyncio
async def test_cache_set_no_redis() -> None:
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=None)):
        assert await cache_mod.cache_set("k", {"a": 1}, ttl=60) is False


@pytest.mark.asyncio
async def test_cache_delete(mock_redis) -> None:
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await cache_mod.cache_delete("k") is True


@pytest.mark.asyncio
async def test_cache_delete_pattern(mock_redis) -> None:
    async def _scan(*args, **kwargs):
        for k in ["a:1", "a:2"]:
            yield k

    mock_redis.scan_iter = _scan
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=mock_redis)):
        count = await cache_mod.cache_delete_pattern("a:*")
        assert count == 2


@pytest.mark.asyncio
async def test_get_cached_job_analysis_hit(mock_redis) -> None:
    data = {"company_name": "Acme", "job_title": "Eng", "extra": "x"}
    wrapped = {"cached_at": "t", "data": data}
    mock_redis.get = AsyncMock(return_value=json.dumps(wrapped))
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=mock_redis)):
        result = await cache_mod.get_cached_job_analysis(job_url="https://x.com", job_content="body")
        assert result is not None
        assert result["company_name"] == "Acme"


@pytest.mark.asyncio
async def test_get_cached_job_analysis_invalid_schema_evicted(mock_redis) -> None:
    wrapped = {"cached_at": "t", "data": {"company_name": "only"}}
    mock_redis.get = AsyncMock(return_value=json.dumps(wrapped))
    mock_redis.delete = AsyncMock()
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await cache_mod.get_cached_job_analysis(job_content="x") is None
        mock_redis.delete.assert_awaited()


@pytest.mark.asyncio
async def test_acquire_and_release_compute_lock(mock_redis) -> None:
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=1)
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await cache_mod.acquire_compute_lock("hash123") is True
        assert await cache_mod.release_compute_lock("hash123") is True


@pytest.mark.asyncio
async def test_check_rate_limit_redis_allowed(mock_redis) -> None:
    mock_redis.get = AsyncMock(return_value="0")
    pipe = MagicMock()
    pipe.incr = MagicMock(return_value=pipe)
    pipe.expire = MagicMock(return_value=pipe)
    pipe.execute = AsyncMock(return_value=[1])
    mock_redis.pipeline = MagicMock(return_value=pipe)
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=mock_redis)):
        allowed, remaining = await cache_mod.check_rate_limit("user:1", limit=5, window_seconds=60)
        assert allowed is True
        assert remaining == 4


@pytest.mark.asyncio
async def test_check_rate_limit_redis_exceeded(mock_redis) -> None:
    mock_redis.get = AsyncMock(return_value="5")
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=mock_redis)):
        allowed, remaining = await cache_mod.check_rate_limit("user:1", limit=5, window_seconds=60)
        assert allowed is False
        assert remaining == 0


@pytest.mark.asyncio
async def test_check_rate_limit_fallback_when_redis_down() -> None:
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=None)):
        allowed, remaining = await cache_mod.check_rate_limit("fb:1", limit=2, window_seconds=60)
        assert allowed is True
        allowed2, _ = await cache_mod.check_rate_limit("fb:1", limit=2, window_seconds=60)
        assert allowed2 is True
        allowed3, rem3 = await cache_mod.check_rate_limit("fb:1", limit=2, window_seconds=60)
        assert allowed3 is False
        assert rem3 == 0


@pytest.mark.asyncio
async def test_check_rate_limit_with_headers(mock_redis) -> None:
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.ttl = AsyncMock(return_value=30)
    pipe = MagicMock()
    pipe.get = MagicMock(return_value=pipe)
    pipe.ttl = MagicMock(return_value=pipe)
    pipe.incr = MagicMock(return_value=pipe)
    pipe.expire = MagicMock(return_value=pipe)
    pipe.execute = AsyncMock(side_effect=[[None, 60], [1]])
    mock_redis.pipeline = MagicMock(return_value=pipe)
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=mock_redis)):
        result = await cache_mod.check_rate_limit_with_headers("u:ep", limit=10, window_seconds=60)
        assert isinstance(result, cache_mod.RateLimitResult)
        assert result.allowed is True
        assert result.get_headers()["X-RateLimit-Limit"] == "10"


@pytest.mark.asyncio
async def test_in_memory_rate_limiter_window_reset() -> None:
    limiter = cache_mod._InMemoryRateLimiter()
    allowed, _, _ = await limiter.check("id", 1, 1)
    assert allowed is True
    import time
    limiter._store["id"] = (1, time.time() - 1)
    allowed2, _, _ = await limiter.check("id", 1, 1)
    assert allowed2 is True


def test_in_memory_rate_limiter_cleanup() -> None:
    import time
    limiter = cache_mod._InMemoryRateLimiter()
    limiter._store = {"old": (1, time.time() - 10), "new": (1, time.time() + 60)}
    limiter._cleanup()
    assert "old" not in limiter._store
    assert "new" in limiter._store


@pytest.mark.asyncio
async def test_record_failed_login_and_lockout(mock_redis) -> None:
    pipe = MagicMock()
    pipe.incr = MagicMock(return_value=pipe)
    pipe.expire = MagicMock(return_value=pipe)
    pipe.execute = AsyncMock(return_value=[5])
    mock_redis.pipeline = MagicMock(return_value=pipe)
    mock_redis.get = AsyncMock(return_value="5")
    mock_redis.ttl = AsyncMock(return_value=120)
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=mock_redis)):
        attempts, locked = await cache_mod.record_failed_login("User@Example.com")
        assert attempts == 5
        assert locked is True
        is_locked, remaining = await cache_mod.check_account_lockout("user@example.com")
        assert is_locked is True
        assert remaining == 120


@pytest.mark.asyncio
async def test_clear_login_attempts(mock_redis) -> None:
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await cache_mod.clear_login_attempts("a@b.com") is True


@pytest.mark.asyncio
async def test_get_rate_limit_remaining(mock_redis) -> None:
    mock_redis.get = AsyncMock(return_value="3")
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await cache_mod.get_rate_limit_remaining("id", limit=10) == 7


@pytest.mark.asyncio
async def test_get_cache_stats_unavailable() -> None:
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=None)):
        stats = await cache_mod.get_cache_stats()
        assert stats["status"] == "unavailable"
        assert stats["fallback_rate_limiter"] == "active"


@pytest.mark.asyncio
async def test_company_research_cache_roundtrip(mock_redis) -> None:
    data = {"company_overview": "A great company"}
    wrapped = {"cached_at": "t", "data": data}

    async def _get_side_effect(key):
        return json.dumps(wrapped)

    mock_redis.get = AsyncMock(side_effect=_get_side_effect)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=1)

    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=mock_redis)):
        hit = await cache_mod.get_cached_company_research("Acme Inc")
        assert hit["company_overview"] == "A great company"
        assert await cache_mod.cache_company_research("Acme Inc", data) is True
        assert await cache_mod.invalidate_company_research("Acme Inc") is True


@pytest.mark.asyncio
async def test_workflow_and_profile_cache(mock_redis) -> None:
    mock_redis.get = AsyncMock(return_value=json.dumps({"cached_at": "t", "data": {"x": 1}}))
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await cache_mod.get_cached_user_profile("uid") == {"x": 1}
        assert await cache_mod.get_cached_workflow_state("sid") == {"x": 1}
        assert await cache_mod.cache_user_profile("uid", {"name": "A"}) is True
        assert await cache_mod.cache_workflow_state("sid", {"step": 1}) is True
        assert await cache_mod.invalidate_user_profile("uid") is True
        assert await cache_mod.invalidate_workflow_state("sid") is True


@pytest.mark.asyncio
async def test_llm_and_tool_result_cache(mock_redis) -> None:
    llm_wrapped = {"cached_at": "t", "data": {"response": "hello", "model": "m"}}
    tool_data = {"result": "ok"}

    async def _get(key):
        if "llm_response" in key:
            return json.dumps(llm_wrapped)
        if "tool_result" in key:
            return json.dumps(tool_data)
        return None

    mock_redis.get = AsyncMock(side_effect=_get)
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=mock_redis)):
        llm = await cache_mod.get_cached_llm_response("prompt", user_id="u1")
        assert llm["response"] == "hello"
        tool = await cache_mod.get_cached_tool_result("thank_you", {"a": 1})
        assert tool["result"] == "ok"
        assert await cache_mod.cache_llm_response("prompt", {"response": "x", "model": "m"}) is True
        assert await cache_mod.cache_tool_result("thank_you", {"a": 1}, {"result": "x"}) is True


@pytest.mark.asyncio
async def test_interview_prep_and_cv_optimizer_locks(mock_redis) -> None:
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value="1")
    mock_redis.delete = AsyncMock(return_value=1)
    with patch.object(cache_mod, "get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await cache_mod.set_interview_prep_generating("s1") is True
        assert await cache_mod.is_interview_prep_generating("s1") is True
        assert await cache_mod.clear_interview_prep_generating("s1") is True
        assert await cache_mod.set_cv_optimization_running("s2") is True
        assert await cache_mod.is_cv_optimization_running("s2") is True
        assert await cache_mod.clear_cv_optimization_running("s2") is True


@pytest.mark.asyncio
async def test_cache_job_analysis_no_key() -> None:
    assert await cache_mod.cache_job_analysis({"company_name": "A", "job_title": "B"}) is False
