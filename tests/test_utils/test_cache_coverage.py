"""Additional edge-case tests for utils/cache.py coverage gaps."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.cache import (
    _CacheMetrics,
    _fallback_limiter,
    cache_delete,
    cache_delete_pattern,
    cache_tool_result,
    check_account_lockout,
    clear_cv_optimization_running,
    clear_interview_prep_generating,
    clear_login_attempts,
    get_cached_company_research,
    get_cached_job_analysis,
    get_cached_llm_response,
    get_cached_tool_result,
    get_cache_stats,
    get_login_attempts,
    get_redis_or_none,
    invalidate_all_user_profile_caches_sync,
    invalidate_user_llm_cache,
    is_cv_optimization_running,
    is_interview_prep_generating,
    record_failed_login,
    set_cv_optimization_running,
    set_interview_prep_generating,
)


@pytest.fixture(autouse=True)
def reset_fallback_limiter():
    _fallback_limiter._store.clear()
    yield
    _fallback_limiter._store.clear()


@pytest.mark.asyncio
async def test_get_redis_or_none_exception() -> None:
    with patch("utils.cache.get_redis_client", AsyncMock(side_effect=RuntimeError("down"))):
        assert await get_redis_or_none() is None


@pytest.mark.asyncio
async def test_cache_delete_no_redis() -> None:
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=None)):
        assert await cache_delete("k") is False


@pytest.mark.asyncio
async def test_cache_delete_error(mock_redis) -> None:
    mock_redis.delete = AsyncMock(side_effect=RuntimeError("fail"))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await cache_delete("k") is False


@pytest.mark.asyncio
async def test_cache_delete_pattern_no_redis() -> None:
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=None)):
        assert await cache_delete_pattern("x:*") == 0


@pytest.mark.asyncio
async def test_cache_delete_pattern_error(mock_redis) -> None:
    async def _fail_scan(*args, **kwargs):
        raise RuntimeError("scan fail")
        yield  # pragma: no cover

    mock_redis.scan_iter = _fail_scan
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await cache_delete_pattern("x:*") == 0


@pytest.mark.asyncio
async def test_get_cached_job_analysis_no_key() -> None:
    assert await get_cached_job_analysis() is None


@pytest.mark.asyncio
async def test_get_cached_company_research_invalid_evicted(mock_redis) -> None:
    wrapped = {"cached_at": "t", "data": {"wrong": "shape"}}
    mock_redis.get = AsyncMock(return_value=json.dumps(wrapped))
    mock_redis.delete = AsyncMock(return_value=1)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await get_cached_company_research("Acme") is None
        mock_redis.delete.assert_awaited()


@pytest.mark.asyncio
async def test_get_cached_company_research_miss(mock_redis) -> None:
    mock_redis.get = AsyncMock(return_value=None)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await get_cached_company_research("Acme") is None


@pytest.mark.asyncio
async def test_get_cached_llm_response_invalid_evicted(mock_redis) -> None:
    wrapped = {"cached_at": "t", "data": {"wrong_field": "only"}}
    mock_redis.get = AsyncMock(return_value=json.dumps(wrapped))
    mock_redis.delete = AsyncMock(return_value=1)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await get_cached_llm_response("prompt", user_id="u1") is None


@pytest.mark.asyncio
async def test_get_cached_llm_response_miss(mock_redis) -> None:
    mock_redis.get = AsyncMock(return_value=None)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await get_cached_llm_response("prompt") is None


@pytest.mark.asyncio
async def test_interview_prep_generating_paths(mock_redis) -> None:
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=None)):
        assert await set_interview_prep_generating("s") is True
        assert await clear_interview_prep_generating("s") is False
        assert await is_interview_prep_generating("s") is False

    mock_redis.set = AsyncMock(side_effect=RuntimeError("fail"))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await set_interview_prep_generating("s") is True

    mock_redis2 = AsyncMock()
    mock_redis2.delete = AsyncMock(side_effect=RuntimeError("fail"))
    mock_redis2.get = AsyncMock(side_effect=RuntimeError("fail"))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis2)):
        assert await clear_interview_prep_generating("s") is False
        assert await is_interview_prep_generating("s") is False


@pytest.mark.asyncio
async def test_cv_optimization_running_paths(mock_redis) -> None:
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=None)):
        assert await set_cv_optimization_running("s") is True
        assert await clear_cv_optimization_running("s") is False
        assert await is_cv_optimization_running("s") is False

    mock_redis.set = AsyncMock(side_effect=RuntimeError("fail"))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await set_cv_optimization_running("s") is True

    mock_redis2 = AsyncMock()
    mock_redis2.delete = AsyncMock(side_effect=RuntimeError("fail"))
    mock_redis2.get = AsyncMock(side_effect=RuntimeError("fail"))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis2)):
        assert await clear_cv_optimization_running("s") is False
        assert await is_cv_optimization_running("s") is False


@pytest.mark.asyncio
async def test_get_cached_tool_result_no_redis() -> None:
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=None)):
        assert await get_cached_tool_result("tool", {"a": 1}) is None


@pytest.mark.asyncio
async def test_get_cached_tool_result_error_records_metric(mock_redis) -> None:
    mock_redis.get = AsyncMock(side_effect=RuntimeError("fail"))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await get_cached_tool_result("tool", {"a": 1}) is None


@pytest.mark.asyncio
async def test_cache_tool_result_no_redis() -> None:
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=None)):
        assert await cache_tool_result("tool", {"a": 1}, {"ok": True}) is False


@pytest.mark.asyncio
async def test_cache_tool_result_error(mock_redis) -> None:
    mock_redis.setex = AsyncMock(side_effect=RuntimeError("fail"))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await cache_tool_result("tool", {"a": 1}, {"ok": True}) is False


@pytest.mark.asyncio
async def test_invalidate_user_llm_cache_scan_error() -> None:
    mock_redis = AsyncMock()
    mock_redis.scan = AsyncMock(side_effect=RuntimeError("scan fail"))
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_redis)):
        assert await invalidate_user_llm_cache("u1") == 0


def test_invalidate_all_user_profile_caches_sync_batch_and_exception() -> None:
    mock_client = MagicMock()
    keys = [f"k{i}" for i in range(501)]
    mock_client.scan_iter.return_value = iter(keys)
    mock_client.delete.return_value = 501
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_client)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("redis.Redis.from_url", return_value=mock_ctx), \
         patch("utils.cache.get_settings") as gs:
        gs.return_value = MagicMock(cache_version="v1", redis_url="redis://localhost")
        deleted = invalidate_all_user_profile_caches_sync()
        assert deleted == 1002

    with patch("redis.Redis.from_url", side_effect=RuntimeError("redis down")), \
         patch("utils.cache.get_settings") as gs:
        gs.return_value = MagicMock(cache_version="v1", redis_url="redis://localhost")
        assert invalidate_all_user_profile_caches_sync() == 0


@pytest.mark.asyncio
async def test_record_failed_login_no_redis() -> None:
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=None)):
        attempts, locked = await record_failed_login("a@b.com")
        assert attempts == 0
        assert locked is False


@pytest.mark.asyncio
async def test_record_failed_login_error() -> None:
    redis = AsyncMock()
    redis.pipeline = MagicMock(side_effect=RuntimeError("pipe fail"))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=redis)):
        attempts, locked = await record_failed_login("a@b.com")
        assert attempts == 0
        assert locked is False


@pytest.mark.asyncio
async def test_check_account_lockout_no_redis_and_not_locked(mock_redis) -> None:
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=None)):
        locked, remaining = await check_account_lockout("a@b.com")
        assert locked is False
        assert remaining == 0

    mock_redis.get = AsyncMock(return_value="2")
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        locked, remaining = await check_account_lockout("a@b.com")
        assert locked is False


@pytest.mark.asyncio
async def test_check_account_lockout_error() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=RuntimeError("fail"))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=redis)):
        locked, remaining = await check_account_lockout("a@b.com")
        assert locked is False
        assert remaining == 0


@pytest.mark.asyncio
async def test_clear_login_attempts_no_redis_and_error() -> None:
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=None)):
        assert await clear_login_attempts("a@b.com") is False

    redis = AsyncMock()
    redis.delete = AsyncMock(side_effect=RuntimeError("fail"))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=redis)):
        assert await clear_login_attempts("a@b.com") is False


@pytest.mark.asyncio
async def test_get_login_attempts_error() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=RuntimeError("fail"))
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=redis)):
        assert await get_login_attempts("a@b.com") == 0


@pytest.mark.asyncio
async def test_get_cache_stats_scan_iter(mock_redis) -> None:
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
        assert "key_counts" in stats


def test_metrics_record_error_and_stats() -> None:
    m = _CacheMetrics()
    m.record_error("unit_test_type")
    stats = m.get_stats()
    assert stats["unit_test_type"]["errors"] == 1


def test_validate_cache_data_non_dict() -> None:
    from utils.cache import _validate_cache_data, CACHE_PREFIX_JOB_ANALYSIS

    assert _validate_cache_data(CACHE_PREFIX_JOB_ANALYSIS, "not-a-dict") is False


@pytest.mark.asyncio
async def test_check_rate_limit_with_headers_no_redis_fallback() -> None:
    from utils.cache import check_rate_limit_with_headers

    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=None)):
        result = await check_rate_limit_with_headers("fb:no-redis", limit=5, window_seconds=60)
    assert result.allowed is True
    assert result.limit == 5


@pytest.mark.asyncio
async def test_cache_job_analysis_no_key() -> None:
    from utils.cache import cache_job_analysis

    assert await cache_job_analysis({"company_name": "A", "job_title": "B"}) is False


@pytest.mark.asyncio
async def test_cache_job_analysis_success(mock_redis) -> None:
    from utils.cache import cache_job_analysis

    mock_redis.setex = AsyncMock(return_value=True)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        ok = await cache_job_analysis(
            {"company_name": "A", "job_title": "B"},
            job_url="https://jobs.example.com/1",
            job_content="job body",
        )
        assert ok is True


@pytest.mark.asyncio
async def test_invalidate_user_llm_cache_no_redis() -> None:
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)):
        assert await invalidate_user_llm_cache("user-1") == 0


@pytest.mark.asyncio
async def test_get_cached_job_analysis_miss(mock_redis) -> None:
    mock_redis.get = AsyncMock(return_value=None)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await get_cached_job_analysis(
            job_url="https://jobs.example.com/1",
            job_content="x" * 100,
        ) is None


@pytest.mark.asyncio
async def test_get_cached_user_profile_miss(mock_redis) -> None:
    from utils.cache import get_cached_user_profile

    mock_redis.get = AsyncMock(return_value=None)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await get_cached_user_profile("user-1") is None


@pytest.mark.asyncio
async def test_get_cached_workflow_state_miss(mock_redis) -> None:
    from utils.cache import get_cached_workflow_state

    mock_redis.get = AsyncMock(return_value=None)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await get_cached_workflow_state("session-1") is None


@pytest.mark.asyncio
async def test_get_cached_cv_optimization_miss(mock_redis) -> None:
    from utils.cache import get_cached_cv_optimization

    mock_redis.get = AsyncMock(return_value=None)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await get_cached_cv_optimization("session-1") is None


@pytest.mark.asyncio
async def test_get_cached_tool_result_miss(mock_redis) -> None:
    mock_redis.get = AsyncMock(return_value=None)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        assert await get_cached_tool_result("thank_you", {"a": 1}) is None


@pytest.mark.asyncio
async def test_check_account_lockout_no_attempts_key(mock_redis) -> None:
    mock_redis.get = AsyncMock(return_value=None)
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        locked, remaining = await check_account_lockout("a@b.com")
        assert locked is False
        assert remaining == 0


@pytest.mark.asyncio
async def test_get_cache_stats_counts_keys(mock_redis) -> None:
    keys = iter(["v1:job_analysis:1", "v1:job_analysis:2"])

    async def _scan_iter(*args, **kwargs):
        for key in keys:
            yield key

    mock_redis.info = AsyncMock(
        side_effect=[
            {"used_memory_human": "1M", "used_memory_peak_human": "2M"},
            {"keyspace_hits": 10, "keyspace_misses": 5, "evicted_keys": 0},
        ]
    )
    mock_redis.scan_iter = _scan_iter
    with patch("utils.cache.get_redis_or_none", AsyncMock(return_value=mock_redis)):
        stats = await get_cache_stats()
        assert stats["key_counts"]["job_analysis"] >= 1


def test_safe_log_identifier_masks_email_in_prefix() -> None:
    from utils.cache import _safe_log_identifier

    masked = _safe_log_identifier("export_data:user@example.com")
    assert masked.startswith("export_data:")
    assert "user@example.com" not in masked
    assert "***" in masked
