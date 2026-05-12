"""
Cache utilities for the ApplyPilot.
Provides high-level caching functions for various data types with automatic
serialization, TTL management, and graceful fallbacks.
"""

import json
import hashlib
import logging
import asyncio
import time
from datetime import datetime, timezone, timedelta
from time import perf_counter
from typing import Optional, Dict, Any, List, Callable, TypeVar
from functools import wraps

from config.settings import get_settings
from utils.redis_client import get_redis_client
from utils.logging_config import get_structured_logger, mask_email

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

logger: logging.Logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)

# Schema version — configurable via CACHE_VERSION env var; bump to flush all caches on deploy
CACHE_VERSION: str = get_settings().cache_version

# Cache key prefixes for namespace separation
CACHE_PREFIX_JOB_ANALYSIS = "job_analysis"
CACHE_PREFIX_COMPANY_RESEARCH = "company_research"
CACHE_PREFIX_USER_PROFILE = "user_profile"
CACHE_PREFIX_WORKFLOW_STATE = "workflow_state"
CACHE_PREFIX_LLM_RESPONSE = "llm_response"
CACHE_PREFIX_RATE_LIMIT = "rate_limit"
CACHE_PREFIX_INTERVIEW_PREP = "interview_prep"
CACHE_PREFIX_INTERVIEW_PREP_GENERATING = "interview_prep_generating"
CACHE_PREFIX_CV_OPTIMIZATION = "cv_optimization"
CACHE_PREFIX_CV_OPTIMIZATION_RUNNING = "cv_optimization_running"
CACHE_PREFIX_TOOL_RESULT = "tool_result"
CACHE_PREFIX_COMPUTE_LOCK = "computing"

# Default TTLs (in seconds)
TTL_JOB_ANALYSIS = 60 * 60 * 24  # 24 hours
TTL_COMPANY_RESEARCH = 60 * 60 * 24 * 7  # 7 days
TTL_USER_PROFILE = 60 * 5  # 5 minutes
TTL_WORKFLOW_STATE = 2  # 2 seconds — shorter than 3s poll interval so every poll sees fresh current_agent
TTL_LLM_RESPONSE = 60 * 60  # 1 hour
TTL_RATE_LIMIT = 60  # 1 minute
TTL_INTERVIEW_PREP = 60 * 60 * 24 * 7  # 7 days
TTL_INTERVIEW_PREP_GENERATING = 60 * 10  # 10 minutes — auto-expires if background task crashes
TTL_CV_OPTIMIZATION = 60 * 60 * 24  # 24 hours
TTL_CV_OPTIMIZATION_RUNNING = 60 * 30  # 30 minutes — auto-expires if background task crashes
TTL_TOOL_RESULT = 60 * 60  # 1 hour
TTL_COMPUTE_LOCK = 60  # 1 minute — prevents stampede, auto-expires if compute crashes

T = TypeVar('T')

# Minimum required top-level fields per cache type — used for schema validation on read.
# Extend this dict when the stored schema gains required fields.
_CACHE_REQUIRED_FIELDS: Dict[str, List[str]] = {
    CACHE_PREFIX_JOB_ANALYSIS: ["company_name", "job_title"],
    CACHE_PREFIX_COMPANY_RESEARCH: ["company_overview"],
    CACHE_PREFIX_USER_PROFILE: [],
    CACHE_PREFIX_WORKFLOW_STATE: [],
    CACHE_PREFIX_LLM_RESPONSE: ["response"],
    CACHE_PREFIX_INTERVIEW_PREP: [],
    CACHE_PREFIX_CV_OPTIMIZATION: [],
    CACHE_PREFIX_TOOL_RESULT: [],
}


# =============================================================================
# IN-MEMORY FALLBACK RATE LIMITER
# =============================================================================


class _InMemoryRateLimiter:
    """
    Fallback rate limiter that runs entirely in-process when Redis is unavailable.

    This prevents Redis outages from becoming a free pass for unlimited requests.
    Accuracy is limited to a single process/replica — use only as a last resort.
    """

    def __init__(self) -> None:
        self._store: Dict[str, tuple] = {}  # identifier -> (count, window_end)
        self._lock = asyncio.Lock()

    async def check(
        self, identifier: str, limit: int, window_seconds: int
    ) -> tuple:
        """
        Check and increment rate limit counter.

        Returns:
            Tuple of (allowed, remaining, reset_seconds)
        """
        async with self._lock:
            now = time.time()
            count, window_end = self._store.get(identifier, (0, now + window_seconds))

            if now > window_end:
                count = 0
                window_end = now + window_seconds

            if count >= limit:
                return False, 0, max(1, int(window_end - now))

            count += 1
            self._store[identifier] = (count, window_end)
            return True, limit - count, max(1, int(window_end - now))

    def _cleanup(self) -> None:
        """Evict expired windows to prevent unbounded memory growth."""
        now = time.time()
        self._store = {k: v for k, v in self._store.items() if v[1] > now}


_fallback_limiter = _InMemoryRateLimiter()


# =============================================================================
# CACHE METRICS
# =============================================================================


class _CacheMetrics:
    """
    In-process hit/miss/error and latency counters per cache type.
    Metrics reset on process restart — use for live dashboards and alerting,
    not for long-term trend analysis (use Cloud Monitoring for that).
    """

    def __init__(self) -> None:
        self._hits: Dict[str, int] = {}
        self._misses: Dict[str, int] = {}
        self._errors: Dict[str, int] = {}
        self._latency_ms_sum: Dict[str, float] = {}
        self._latency_count: Dict[str, int] = {}

    def record_hit(self, cache_type: str, latency_ms: float = 0.0) -> None:
        self._hits[cache_type] = self._hits.get(cache_type, 0) + 1
        self._latency_ms_sum[cache_type] = self._latency_ms_sum.get(cache_type, 0.0) + latency_ms
        self._latency_count[cache_type] = self._latency_count.get(cache_type, 0) + 1

    def record_miss(self, cache_type: str, latency_ms: float = 0.0) -> None:
        self._misses[cache_type] = self._misses.get(cache_type, 0) + 1
        self._latency_ms_sum[cache_type] = self._latency_ms_sum.get(cache_type, 0.0) + latency_ms
        self._latency_count[cache_type] = self._latency_count.get(cache_type, 0) + 1

    def record_error(self, cache_type: str) -> None:
        self._errors[cache_type] = self._errors.get(cache_type, 0) + 1

    def get_stats(self) -> Dict[str, Any]:
        """Return per-type hit rates, latency, and error counts."""
        all_types = set(list(self._hits.keys()) + list(self._misses.keys()) + list(self._errors.keys()))
        result: Dict[str, Any] = {}
        for t in all_types:
            hits = self._hits.get(t, 0)
            misses = self._misses.get(t, 0)
            total = hits + misses
            lat_count = self._latency_count.get(t, 0)
            avg_latency = (
                self._latency_ms_sum.get(t, 0.0) / lat_count
                if lat_count > 0
                else 0.0
            )
            result[t] = {
                "hits": hits,
                "misses": misses,
                "hit_rate": round(hits / total, 3) if total > 0 else None,
                "errors": self._errors.get(t, 0),
                "avg_latency_ms": round(avg_latency, 2),
            }
        return result


_metrics = _CacheMetrics()


# =============================================================================
# CORE CACHE FUNCTIONS
# =============================================================================


def generate_hash(content: str) -> str:
    """Generate MD5 hash for cache key generation."""
    return hashlib.md5(content.encode('utf-8')).hexdigest()


async def get_redis_or_none():
    """Get Redis client or None if unavailable."""
    try:
        return await get_redis_client()
    except Exception as e:
        logger.debug(f"Redis not available: {e}")
        return None


async def cache_get(key: str) -> Optional[Dict[str, Any]]:
    """
    Get value from cache with automatic JSON deserialization.
    
    Args:
        key: Full cache key
        
    Returns:
        Cached data or None if not found/expired
    """
    try:
        redis = await get_redis_or_none()
        if not redis:
            return None
            
        cached = await redis.get(key)
        if cached:
            data = json.loads(cached)
            logger.debug(f"Cache hit: {key}")
            return data
        return None
        
    except Exception as e:
        logger.warning(f"Cache get error for {key}: {e}")
        return None


async def cache_set(key: str, data: Dict[str, Any], ttl: int) -> bool:
    """
    Set value in cache with automatic JSON serialization.
    
    Args:
        key: Full cache key
        data: Data to cache (must be JSON serializable)
        ttl: Time to live in seconds
        
    Returns:
        True if cached successfully, False otherwise
    """
    try:
        redis = await get_redis_or_none()
        if not redis:
            return False
            
        # Add metadata
        cache_data = {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        
        await redis.set(key, json.dumps(cache_data), ex=ttl)
        logger.debug(f"Cache set: {key} (TTL: {ttl}s)")
        return True
        
    except Exception as e:
        logger.warning(f"Cache set error for {key}: {e}")
        return False


async def cache_delete(key: str) -> bool:
    """Delete a key from cache."""
    try:
        redis = await get_redis_or_none()
        if not redis:
            return False
            
        await redis.delete(key)
        logger.debug(f"Cache deleted: {key}")
        return True
        
    except Exception as e:
        logger.warning(f"Cache delete error for {key}: {e}")
        return False


async def cache_delete_pattern(pattern: str) -> int:
    """
    Delete all keys matching a pattern.
    
    Args:
        pattern: Redis pattern (e.g., "user_profile:*")
        
    Returns:
        Number of keys deleted
    """
    try:
        redis = await get_redis_or_none()
        if not redis:
            return 0
            
        keys = []
        async for key in redis.scan_iter(match=pattern):
            keys.append(key)
            
        if keys:
            await redis.delete(*keys)
            logger.info(f"Cache pattern delete: {pattern} ({len(keys)} keys)")
            
        return len(keys)
        
    except Exception as e:
        logger.warning(f"Cache pattern delete error for {pattern}: {e}")
        return 0


# =============================================================================
# JOB ANALYSIS CACHE
# =============================================================================

# Must match api/workflow.py MAX_TEXT_LENGTH — hash enough of the posting that
# cache keys differ when the job body differs after a long shared page chrome
# (nav, feed shell, etc. on job-board SPAs).
_MAX_JOB_CONTENT_FOR_CACHE_KEY: int = 50000


def _get_job_cache_key(job_url: Optional[str], job_content: Optional[str]) -> str:
    """Generate versioned cache key for job analysis."""
    if job_url:
        content_hash = generate_hash(job_url)
    elif job_content:
        normalized = job_content[:_MAX_JOB_CONTENT_FOR_CACHE_KEY]
        content_hash = generate_hash(normalized)
    else:
        return ""
    return f"{CACHE_VERSION}:{CACHE_PREFIX_JOB_ANALYSIS}:{content_hash}"


def _validate_cache_data(cache_type: str, data: Any) -> bool:
    """
    Validate that a cached payload has the expected shape.

    Args:
        cache_type: Cache prefix constant identifying the data type
        data: Deserialized payload from Redis

    Returns:
        True if the data passes basic schema checks
    """
    if not isinstance(data, dict):
        return False
    required = _CACHE_REQUIRED_FIELDS.get(cache_type, [])
    return all(field in data for field in required)


async def get_cached_job_analysis(
    job_url: Optional[str] = None,
    job_content: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get cached job analysis results.
    
    Args:
        job_url: Job posting URL
        job_content: Job posting text content
        
    Returns:
        Cached job analysis or None
    """
    key = _get_job_cache_key(job_url, job_content)
    if not key:
        return None

    t0 = perf_counter()
    cached = await cache_get(key)
    latency_ms = (perf_counter() - t0) * 1000

    if cached and "data" in cached:
        data = cached["data"]
        if not _validate_cache_data(CACHE_PREFIX_JOB_ANALYSIS, data):
            logger.warning("job_analysis cache entry failed schema validation — evicting")
            await cache_delete(key)
            _metrics.record_miss(CACHE_PREFIX_JOB_ANALYSIS, latency_ms)
            structured_logger.log_cache_miss("job_analysis", key)
            return None
        _metrics.record_hit(CACHE_PREFIX_JOB_ANALYSIS, latency_ms)
        structured_logger.log_cache_hit("job_analysis", key)
        return data
    _metrics.record_miss(CACHE_PREFIX_JOB_ANALYSIS, latency_ms)
    structured_logger.log_cache_miss("job_analysis", key)
    return None


async def cache_job_analysis(
    analysis: Dict[str, Any],
    job_url: Optional[str] = None,
    job_content: Optional[str] = None,
) -> bool:
    """
    Cache job analysis results.
    
    Args:
        analysis: Job analysis results
        job_url: Job posting URL
        job_content: Job posting text content
        
    Returns:
        True if cached successfully
    """
    key = _get_job_cache_key(job_url, job_content)
    if not key:
        return False
        
    return await cache_set(key, analysis, TTL_JOB_ANALYSIS)


# =============================================================================
# COMPANY RESEARCH CACHE
# =============================================================================


def _get_company_research_cache_key(company_name: str) -> str:
    """Generate versioned, normalized cache key for company research."""
    normalized = company_name.lower().strip()
    name_hash = generate_hash(normalized)
    return f"{CACHE_VERSION}:{CACHE_PREFIX_COMPANY_RESEARCH}:{name_hash}:{normalized[:30]}"


async def get_cached_company_research(company_name: str) -> Optional[Dict[str, Any]]:
    """
    Get cached company research result.

    Args:
        company_name: Company name (case-insensitive)

    Returns:
        Cached research dict or None on miss
    """
    key = _get_company_research_cache_key(company_name)
    t0 = perf_counter()
    cached = await cache_get(key)
    latency_ms = (perf_counter() - t0) * 1000
    if cached and "data" in cached:
        data = cached["data"]
        if not _validate_cache_data(CACHE_PREFIX_COMPANY_RESEARCH, data):
            logger.warning(f"company_research cache entry for '{company_name}' failed schema validation — evicting")
            await cache_delete(key)
            _metrics.record_miss(CACHE_PREFIX_COMPANY_RESEARCH, latency_ms)
            structured_logger.log_cache_miss("company_research", key[:30])
            return None
        _metrics.record_hit(CACHE_PREFIX_COMPANY_RESEARCH, latency_ms)
        structured_logger.log_cache_hit("company_research", key[:30])
        return data
    _metrics.record_miss(CACHE_PREFIX_COMPANY_RESEARCH, latency_ms)
    structured_logger.log_cache_miss("company_research", key[:30])
    return None


async def cache_company_research(company_name: str, research: Dict[str, Any]) -> bool:
    """
    Cache company research result using the shared 7-day TTL.

    Args:
        company_name: Company name
        research: Research result dict

    Returns:
        True if cached successfully
    """
    key = _get_company_research_cache_key(company_name)
    return await cache_set(key, research, TTL_COMPANY_RESEARCH)


async def invalidate_company_research(company_name: str) -> bool:
    """Invalidate company research cache entry."""
    key = _get_company_research_cache_key(company_name)
    return await cache_delete(key)


# =============================================================================
# COMPUTE LOCK (STAMPEDE PROTECTION)
# =============================================================================


async def acquire_compute_lock(cache_key: str) -> bool:
    """
    Atomically acquire a short-lived lock for an expensive computation.

    Use this to prevent cache stampedes: when multiple concurrent requests all
    miss the cache at the same time, only the first should compute — the rest
    should wait and retry the cache.

    Pattern:
        claimed = await acquire_compute_lock(key)
        if not claimed:
            # Poll cache while another coroutine computes
            return await wait_for_computed_cache(key, get_fn)
        try:
            result = await compute()
            await cache_set(key, result, ttl)
        finally:
            await release_compute_lock(key)

    Args:
        cache_key: The cache key being computed (used as lock identifier)

    Returns:
        True if lock was acquired (caller should compute), False if already locked
    """
    try:
        redis = await get_redis_or_none()
        if not redis:
            return True  # Fail open — allow compute without lock
        lock_key = f"{CACHE_PREFIX_COMPUTE_LOCK}:{cache_key}"
        was_set = await redis.set(lock_key, "1", nx=True, ex=TTL_COMPUTE_LOCK)
        return was_set is not None
    except Exception as e:
        logger.warning(f"acquire_compute_lock failed for {cache_key}: {e}")
        return True  # Fail open


async def release_compute_lock(cache_key: str) -> bool:
    """
    Release a compute lock acquired by acquire_compute_lock.

    Args:
        cache_key: The cache key whose lock should be released

    Returns:
        True if released successfully
    """
    try:
        redis = await get_redis_or_none()
        if not redis:
            return False
        lock_key = f"{CACHE_PREFIX_COMPUTE_LOCK}:{cache_key}"
        await redis.delete(lock_key)
        return True
    except Exception as e:
        logger.warning(f"release_compute_lock failed for {cache_key}: {e}")
        return False


# =============================================================================
# USER PROFILE CACHE
# =============================================================================


def _get_profile_cache_key(user_id: str) -> str:
    """Generate versioned cache key for user profile."""
    return f"{CACHE_VERSION}:{CACHE_PREFIX_USER_PROFILE}:{user_id}"


async def get_cached_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get cached user profile.
    
    Args:
        user_id: User UUID as string
        
    Returns:
        Cached profile data or None
    """
    key = _get_profile_cache_key(user_id)
    t0 = perf_counter()
    cached = await cache_get(key)
    latency_ms = (perf_counter() - t0) * 1000
    if cached and "data" in cached:
        _metrics.record_hit(CACHE_PREFIX_USER_PROFILE, latency_ms)
        structured_logger.log_cache_hit("user_profile", user_id[:8])
        return cached["data"]
    _metrics.record_miss(CACHE_PREFIX_USER_PROFILE, latency_ms)
    structured_logger.log_cache_miss("user_profile", user_id[:8])
    return None


async def cache_user_profile(user_id: str, profile: Dict[str, Any]) -> bool:
    """
    Cache user profile.
    
    Args:
        user_id: User UUID as string
        profile: Profile data
        
    Returns:
        True if cached successfully
    """
    key = _get_profile_cache_key(user_id)
    return await cache_set(key, profile, TTL_USER_PROFILE)


async def invalidate_user_profile(user_id: str) -> bool:
    """Invalidate user profile cache when profile is updated."""
    key = _get_profile_cache_key(user_id)
    return await cache_delete(key)


def invalidate_all_user_profile_caches_sync() -> int:
    """Clear all cached ``GET /profile`` payloads from Redis (synchronous).

    Call from Alembic ``upgrade()`` after SQL backfills on ``user_profiles`` that
    bypass the profile API (which normally calls :func:`invalidate_user_profile`).
    Best-effort: logs and returns 0 if Redis is unavailable — does not raise.

    Returns:
        Number of keys deleted.
    """
    try:
        import redis as redis_sync
    except ImportError:
        logger.warning(
            "redis package unavailable — skipping user_profile cache invalidation"
        )
        return 0

    try:
        settings = get_settings()
        pattern = f"{settings.cache_version}:{CACHE_PREFIX_USER_PROFILE}:*"
        deleted = 0
        with redis_sync.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
        ) as client:
            batch: List[str] = []
            for key in client.scan_iter(match=pattern, count=500):
                batch.append(key)
                if len(batch) >= 500:
                    deleted += int(client.delete(*batch))
                    batch.clear()
            if batch:
                deleted += int(client.delete(*batch))
        if deleted:
            logger.info(
                "Invalidated %s cached user_profile keys (migration / bulk backfill)",
                deleted,
            )
        return deleted
    except Exception as e:
        logger.warning(
            "user_profile cache invalidation skipped: %s",
            e,
            exc_info=True,
        )
        return 0


async def invalidate_user_llm_cache(user_id: str) -> int:
    """Delete all per-user LLM response cache entries.

    Call this when the user updates or removes their BYOK API key so that
    cached responses generated under the old key are not served to new
    requests that may use a different model or key.

    Returns:
        Number of cache keys deleted (0 if Redis is unavailable or no keys exist).
    """
    from utils.redis_client import get_redis_client

    redis_client = await get_redis_client()
    if not redis_client:
        return 0

    pattern = f"{CACHE_VERSION}:{CACHE_PREFIX_LLM_RESPONSE}:{user_id}:*"
    deleted = 0
    try:
        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(cursor, match=pattern, count=100)
            if keys:
                await redis_client.delete(*keys)
                deleted += len(keys)
            if cursor == 0:
                break
    except Exception as e:
        logger.warning(f"Failed to invalidate LLM cache for user {user_id}: {e}")

    return deleted


# =============================================================================
# WORKFLOW STATE CACHE
# =============================================================================


def _get_workflow_cache_key(session_id: str) -> str:
    """Generate versioned cache key for workflow state."""
    return f"{CACHE_VERSION}:{CACHE_PREFIX_WORKFLOW_STATE}:{session_id}"


async def get_cached_workflow_state(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Get cached workflow state.
    
    Args:
        session_id: Workflow session ID
        
    Returns:
        Cached workflow state or None
    """
    key = _get_workflow_cache_key(session_id)
    t0 = perf_counter()
    cached = await cache_get(key)
    latency_ms = (perf_counter() - t0) * 1000
    if cached and "data" in cached:
        _metrics.record_hit(CACHE_PREFIX_WORKFLOW_STATE, latency_ms)
        structured_logger.log_cache_hit("workflow_state", session_id[:8])
        return cached["data"]
    _metrics.record_miss(CACHE_PREFIX_WORKFLOW_STATE, latency_ms)
    structured_logger.log_cache_miss("workflow_state", session_id[:8])
    return None


async def cache_workflow_state(session_id: str, state: Dict[str, Any]) -> bool:
    """
    Cache workflow state.
    
    Args:
        session_id: Workflow session ID
        state: Workflow state data
        
    Returns:
        True if cached successfully
    """
    key = _get_workflow_cache_key(session_id)
    return await cache_set(key, state, TTL_WORKFLOW_STATE)


async def invalidate_workflow_state(session_id: str) -> bool:
    """Invalidate workflow state cache."""
    key = _get_workflow_cache_key(session_id)
    return await cache_delete(key)


# =============================================================================
# LLM RESPONSE CACHE
# =============================================================================


def _get_llm_cache_key(prompt: str, system: Optional[str] = None, user_id: Optional[str] = None) -> str:
    """
    Generate versioned cache key for LLM response.

    When user_id is provided the key is scoped per user, preventing cross-user
    data leakage for prompts that contain personal content (resumes, etc.).
    Omit user_id only for purely public/shared prompts (e.g. job descriptions).
    """
    content = f"{system or ''}:{prompt}"
    content_hash = generate_hash(content)
    if user_id:
        return f"{CACHE_VERSION}:{CACHE_PREFIX_LLM_RESPONSE}:{user_id}:{content_hash}"
    return f"{CACHE_VERSION}:{CACHE_PREFIX_LLM_RESPONSE}:{content_hash}"


async def get_cached_llm_response(
    prompt: str,
    system: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get cached LLM response.

    Args:
        prompt: The prompt sent to LLM
        system: System message (optional)
        user_id: User UUID — provide whenever the prompt contains personal content
                 (resumes, cover letters) to prevent cross-user cache hits.

    Returns:
        Cached LLM response or None
    """
    key = _get_llm_cache_key(prompt, system, user_id)
    t0 = perf_counter()
    cached = await cache_get(key)
    latency_ms = (perf_counter() - t0) * 1000
    if cached and "data" in cached:
        data = cached["data"]
        if not _validate_cache_data(CACHE_PREFIX_LLM_RESPONSE, data):
            logger.warning("llm_response cache entry failed schema validation — evicting")
            await cache_delete(key)
            _metrics.record_miss(CACHE_PREFIX_LLM_RESPONSE, latency_ms)
            structured_logger.log_cache_miss("llm_response", key[:20])
            return None
        _metrics.record_hit(CACHE_PREFIX_LLM_RESPONSE, latency_ms)
        structured_logger.log_cache_hit("llm_response", key[:20])
        return data
    _metrics.record_miss(CACHE_PREFIX_LLM_RESPONSE, latency_ms)
    structured_logger.log_cache_miss("llm_response", key[:20])
    return None


async def cache_llm_response(
    prompt: str,
    response: Dict[str, Any],
    system: Optional[str] = None,
    user_id: Optional[str] = None,
) -> bool:
    """
    Cache LLM response.

    Args:
        prompt: The prompt sent to LLM
        response: LLM response data
        system: System message (optional)
        user_id: User UUID — must match the value passed to get_cached_llm_response.

    Returns:
        True if cached successfully
    """
    key = _get_llm_cache_key(prompt, system, user_id)
    return await cache_set(key, response, TTL_LLM_RESPONSE)


# =============================================================================
# INTERVIEW PREP CACHE
# =============================================================================


def _get_interview_prep_cache_key(session_id: str) -> str:
    """Generate versioned cache key for interview prep materials."""
    return f"{CACHE_VERSION}:{CACHE_PREFIX_INTERVIEW_PREP}:{session_id}"


async def get_cached_interview_prep(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Get cached interview prep materials.
    
    Args:
        session_id: Workflow session ID
        
    Returns:
        Cached interview prep data or None
    """
    key = _get_interview_prep_cache_key(session_id)
    t0 = perf_counter()
    cached = await cache_get(key)
    latency_ms = (perf_counter() - t0) * 1000
    if cached and "data" in cached:
        _metrics.record_hit(CACHE_PREFIX_INTERVIEW_PREP, latency_ms)
        structured_logger.log_cache_hit("interview_prep", session_id[:8])
        return cached
    _metrics.record_miss(CACHE_PREFIX_INTERVIEW_PREP, latency_ms)
    structured_logger.log_cache_miss("interview_prep", session_id[:8])
    return None


async def cache_interview_prep(session_id: str, data: Dict[str, Any]) -> bool:
    """
    Cache interview prep materials.
    
    Args:
        session_id: Workflow session ID
        data: Interview prep data
        
    Returns:
        True if cached successfully
    """
    key = _get_interview_prep_cache_key(session_id)
    return await cache_set(key, data, TTL_INTERVIEW_PREP)


async def invalidate_interview_prep(session_id: str) -> bool:
    """
    Invalidate interview prep cache (for regeneration).
    
    Args:
        session_id: Workflow session ID
        
    Returns:
        True if deleted successfully
    """
    key = _get_interview_prep_cache_key(session_id)
    return await cache_delete(key)


async def set_interview_prep_generating(session_id: str) -> bool:
    """
    Atomically mark interview prep generation as in-progress for a session.

    Uses Redis SET NX (set-if-not-exists) so that concurrent requests only
    succeed for the *first* caller — subsequent callers get False, indicating
    that generation is already running and a 409 should be returned.

    Args:
        session_id: Workflow session ID

    Returns:
        True if the flag was successfully claimed (caller should proceed),
        False if the flag already existed (another task is already generating).
    """
    try:
        redis = await get_redis_or_none()
        if not redis:
            # Redis unavailable — allow the request to proceed (fail open)
            return True
        key = f"{CACHE_VERSION}:{CACHE_PREFIX_INTERVIEW_PREP_GENERATING}:{session_id}"
        # SET key "1" NX EX ttl — returns True if key was set, None if it already existed
        was_set = await redis.set(key, "1", nx=True, ex=TTL_INTERVIEW_PREP_GENERATING)
        return was_set is not None
    except Exception as e:
        logger.warning(f"Failed to set interview_prep generating flag: {e}")
        return True  # Fail open so a Redis outage doesn't block generation


async def clear_interview_prep_generating(session_id: str) -> bool:
    """
    Clear the in-progress generation flag for a session.

    Args:
        session_id: Workflow session ID

    Returns:
        True if flag was cleared
    """
    try:
        redis = await get_redis_or_none()
        if not redis:
            return False
        key = f"{CACHE_VERSION}:{CACHE_PREFIX_INTERVIEW_PREP_GENERATING}:{session_id}"
        await redis.delete(key)
        return True
    except Exception as e:
        logger.warning(f"Failed to clear interview_prep generating flag: {e}")
        return False


async def is_interview_prep_generating(session_id: str) -> bool:
    """
    Check whether interview prep generation is currently in progress.

    Args:
        session_id: Workflow session ID

    Returns:
        True if generation is in progress
    """
    try:
        redis = await get_redis_or_none()
        if not redis:
            return False
        key = f"{CACHE_VERSION}:{CACHE_PREFIX_INTERVIEW_PREP_GENERATING}:{session_id}"
        value = await redis.get(key)
        return value is not None
    except Exception as e:
        logger.warning(f"Failed to check interview_prep generating flag: {e}")
        return False


# =============================================================================
# CV OPTIMIZATION CACHE
# =============================================================================


def _get_cv_optimization_cache_key(session_id: str) -> str:
    """Generate versioned cache key for CV optimization results."""
    return f"{CACHE_VERSION}:{CACHE_PREFIX_CV_OPTIMIZATION}:{session_id}"


async def get_cached_cv_optimization(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Get cached CV optimization result.

    Args:
        session_id: Workflow session ID

    Returns:
        Cached optimization data or None
    """
    key = _get_cv_optimization_cache_key(session_id)
    t0 = perf_counter()
    cached = await cache_get(key)
    latency_ms = (perf_counter() - t0) * 1000
    if cached:
        _metrics.record_hit(CACHE_PREFIX_CV_OPTIMIZATION, latency_ms)
        structured_logger.log_cache_hit("cv_optimization", session_id[:8])
        return cached
    _metrics.record_miss(CACHE_PREFIX_CV_OPTIMIZATION, latency_ms)
    structured_logger.log_cache_miss("cv_optimization", session_id[:8])
    return None


async def cache_cv_optimization(session_id: str, data: Dict[str, Any]) -> bool:
    """
    Cache CV optimization result.

    Args:
        session_id: Workflow session ID
        data: Optimization result data

    Returns:
        True if cached successfully
    """
    key = _get_cv_optimization_cache_key(session_id)
    return await cache_set(key, data, TTL_CV_OPTIMIZATION)


async def invalidate_cv_optimization(session_id: str) -> bool:
    """
    Invalidate CV optimization cache (allows re-run).

    Args:
        session_id: Workflow session ID

    Returns:
        True if deleted successfully
    """
    key = _get_cv_optimization_cache_key(session_id)
    return await cache_delete(key)


async def set_cv_optimization_running(session_id: str) -> bool:
    """
    Atomically mark CV optimization as in-progress for a session.

    Uses Redis SET NX so only the first caller succeeds; subsequent callers
    get False, indicating another task is already running (return 409).

    Args:
        session_id: Workflow session ID

    Returns:
        True if the flag was claimed (caller should proceed),
        False if another task is already running.
    """
    try:
        redis = await get_redis_or_none()
        if not redis:
            return True  # Fail open so a Redis outage doesn't block the feature
        key = f"{CACHE_VERSION}:{CACHE_PREFIX_CV_OPTIMIZATION_RUNNING}:{session_id}"
        was_set = await redis.set(key, "1", nx=True, ex=TTL_CV_OPTIMIZATION_RUNNING)
        return was_set is not None
    except Exception as e:
        logger.warning(f"Failed to set cv_optimization running flag: {e}")
        return True


async def clear_cv_optimization_running(session_id: str) -> bool:
    """
    Clear the in-progress flag for CV optimization.

    Args:
        session_id: Workflow session ID

    Returns:
        True if flag was cleared
    """
    try:
        redis = await get_redis_or_none()
        if not redis:
            return False
        key = f"{CACHE_VERSION}:{CACHE_PREFIX_CV_OPTIMIZATION_RUNNING}:{session_id}"
        await redis.delete(key)
        return True
    except Exception as e:
        logger.warning(f"Failed to clear cv_optimization running flag: {e}")
        return False


async def is_cv_optimization_running(session_id: str) -> bool:
    """
    Check whether CV optimization is currently in progress.

    Args:
        session_id: Workflow session ID

    Returns:
        True if optimization is in progress
    """
    try:
        redis = await get_redis_or_none()
        if not redis:
            return False
        key = f"{CACHE_VERSION}:{CACHE_PREFIX_CV_OPTIMIZATION_RUNNING}:{session_id}"
        value = await redis.get(key)
        return value is not None
    except Exception as e:
        logger.warning(f"Failed to check cv_optimization running flag: {e}")
        return False


# =============================================================================
# CAREER TOOL RESULT CACHING
# =============================================================================


def _get_tool_result_cache_key(tool_name: str, payload_hash: str) -> str:
    """Generate versioned cache key for career tool results."""
    return f"{CACHE_VERSION}:{CACHE_PREFIX_TOOL_RESULT}:{tool_name}:{payload_hash}"


async def get_cached_tool_result(
    tool_name: str, payload: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Return a cached career tool result or None on miss.

    Args:
        tool_name: Name of the tool (e.g. "thank_you", "salary_coach")
        payload: The exact request payload dict used as cache key material

    Returns:
        Cached result dict, or None on miss / Redis unavailable
    """
    try:
        redis = await get_redis_or_none()
        if not redis:
            return None
        payload_hash = generate_hash(json.dumps(payload, sort_keys=True))
        key = _get_tool_result_cache_key(tool_name, payload_hash)
        t0 = perf_counter()
        cached = await redis.get(key)
        latency_ms = (perf_counter() - t0) * 1000
        if cached:
            data = json.loads(cached)
            if not isinstance(data, dict):
                logger.warning(f"tool_result cache entry for {tool_name} is not a dict — evicting")
                await redis.delete(key)
                _metrics.record_miss(tool_name, latency_ms)
                structured_logger.log_cache_miss(tool_name, key)
                return None
            _metrics.record_hit(tool_name, latency_ms)
            structured_logger.log_cache_hit(tool_name, key)
            return data
        _metrics.record_miss(tool_name, latency_ms)
        structured_logger.log_cache_miss(tool_name, key)
        return None
    except Exception as e:
        logger.warning(f"Tool result cache get error ({tool_name}): {e}")
        _metrics.record_error(tool_name)
        return None


async def cache_tool_result(
    tool_name: str, payload: Dict[str, Any], result: Dict[str, Any]
) -> bool:
    """
    Cache a career tool result for 1 hour.

    Args:
        tool_name: Name of the tool
        payload: The exact request payload dict used as cache key material
        result: The tool result to cache

    Returns:
        True on success
    """
    try:
        redis = await get_redis_or_none()
        if not redis:
            return False
        payload_hash = generate_hash(json.dumps(payload, sort_keys=True))
        key = _get_tool_result_cache_key(tool_name, payload_hash)
        await redis.setex(key, TTL_TOOL_RESULT, json.dumps(result))
        return True
    except Exception as e:
        logger.warning(f"Tool result cache set error ({tool_name}): {e}")
        return False


# =============================================================================
# RATE LIMITING
# =============================================================================


class RateLimitResult:
    """Result of a rate limit check with all relevant info for headers."""
    
    def __init__(
        self,
        allowed: bool,
        limit: int,
        remaining: int,
        reset_seconds: int,
    ):
        self.allowed = allowed
        self.limit = limit
        self.remaining = remaining
        self.reset_seconds = reset_seconds
    
    def get_headers(self) -> Dict[str, str]:
        """Get rate limit headers for HTTP response."""
        return {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(self.reset_seconds),
        }


async def check_rate_limit(
    identifier: str,
    limit: int,
    window_seconds: int = 60,
) -> tuple:
    """
    Check if rate limit is exceeded.

    Falls back to in-memory limiting when Redis is unavailable so that a
    Redis outage does not silently disable all rate limits.

    Args:
        identifier: Unique identifier (e.g., "user_id:endpoint")
        limit: Maximum requests allowed in window
        window_seconds: Time window in seconds

    Returns:
        Tuple of (is_allowed, remaining_requests)
    """
    try:
        redis = await get_redis_or_none()
        if not redis:
            logger.warning("Redis unavailable — using in-memory rate limiter fallback")
            allowed, remaining, _ = await _fallback_limiter.check(identifier, limit, window_seconds)
            return allowed, remaining

        key = f"{CACHE_PREFIX_RATE_LIMIT}:{identifier}"
        
        # Get current count
        current = await redis.get(key)
        current_count = int(current) if current else 0
        
        if current_count >= limit:
            logger.warning(f"Rate limit exceeded for {identifier}")
            return False, 0
            
        # Increment counter
        pipe = redis.pipeline()
        pipe.incr(key)
        if current_count == 0:
            pipe.expire(key, window_seconds)
        await pipe.execute()
        
        remaining = limit - current_count - 1
        return True, remaining
        
    except Exception as e:
        logger.warning(f"Rate limit check error: {e} — using in-memory fallback")
        allowed, remaining, _ = await _fallback_limiter.check(identifier, limit, window_seconds)
        return allowed, remaining


async def check_rate_limit_with_headers(
    identifier: str,
    limit: int,
    window_seconds: int = 60,
) -> RateLimitResult:
    """
    Check rate limit and return full result with header info.

    Falls back to in-memory limiting when Redis is unavailable so that a
    Redis outage does not silently disable all rate limits.

    Args:
        identifier: Unique identifier (e.g., "user_id:endpoint")
        limit: Maximum requests allowed in window
        window_seconds: Time window in seconds

    Returns:
        RateLimitResult with allowed status and header info
    """
    try:
        redis = await get_redis_or_none()
        if not redis:
            logger.warning("Redis unavailable — using in-memory rate limiter fallback")
            allowed, remaining, reset_secs = await _fallback_limiter.check(
                identifier, limit, window_seconds
            )
            return RateLimitResult(
                allowed=allowed,
                limit=limit,
                remaining=remaining,
                reset_seconds=reset_secs,
            )

        key = f"{CACHE_PREFIX_RATE_LIMIT}:{identifier}"
        
        # Get current count and TTL
        pipe = redis.pipeline()
        pipe.get(key)
        pipe.ttl(key)
        results = await pipe.execute()
        
        current = results[0]
        ttl = results[1]
        current_count = int(current) if current else 0
        reset_seconds = ttl if ttl and ttl > 0 else window_seconds
        
        if current_count >= limit:
            logger.warning(f"Rate limit exceeded for {identifier}")
            return RateLimitResult(
                allowed=False,
                limit=limit,
                remaining=0,
                reset_seconds=reset_seconds,
            )
            
        # Increment counter
        pipe = redis.pipeline()
        pipe.incr(key)
        if current_count == 0:
            pipe.expire(key, window_seconds)
        await pipe.execute()
        
        remaining = limit - current_count - 1
        return RateLimitResult(
            allowed=True,
            limit=limit,
            remaining=remaining,
            reset_seconds=reset_seconds if ttl and ttl > 0 else window_seconds,
        )
        
    except Exception as e:
        logger.error(f"Rate limit check error: {e} — using in-memory fallback", exc_info=True)
        allowed, remaining, reset_secs = await _fallback_limiter.check(
            identifier, limit, window_seconds
        )
        return RateLimitResult(
            allowed=allowed,
            limit=limit,
            remaining=remaining,
            reset_seconds=reset_secs,
        )


async def get_rate_limit_remaining(
    identifier: str,
    limit: int,
) -> int:
    """Get remaining requests for a rate limit."""
    try:
        redis = await get_redis_or_none()
        if not redis:
            return limit
            
        key = f"{CACHE_PREFIX_RATE_LIMIT}:{identifier}"
        current = await redis.get(key)
        current_count = int(current) if current else 0
        return max(0, limit - current_count)
        
    except Exception as e:
        logger.warning(f"Rate limit remaining error: {e}")
        return limit


# =============================================================================
# ACCOUNT LOCKOUT
# =============================================================================

CACHE_PREFIX_LOGIN_ATTEMPTS = "login_attempts"
LOCKOUT_THRESHOLD = 5  # Failed attempts before lockout
LOCKOUT_DURATION = 900  # 15 minutes in seconds
ATTEMPT_WINDOW = 900  # Track attempts within 15 minutes


async def record_failed_login(email: str) -> tuple[int, bool]:
    """
    Record a failed login attempt and check for lockout.
    
    Args:
        email: Email address that failed login
        
    Returns:
        Tuple of (current_attempts, is_locked)
    """
    try:
        redis = await get_redis_or_none()
        if not redis:
            return 0, False
            
        key = f"{CACHE_PREFIX_LOGIN_ATTEMPTS}:{email.lower()}"
        
        # Increment attempt counter
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, ATTEMPT_WINDOW)
        results = await pipe.execute()
        
        current_attempts = results[0]
        is_locked = current_attempts >= LOCKOUT_THRESHOLD
        
        if is_locked:
            logger.warning(f"Account locked due to failed attempts: {mask_email(email)}")
            # Set lockout with longer expiry
            await redis.expire(key, LOCKOUT_DURATION)
            
        return current_attempts, is_locked
        
    except Exception as e:
        logger.warning(f"Failed to record login attempt: {e}")
        return 0, False


async def check_account_lockout(email: str) -> tuple[bool, int]:
    """
    Check if account is currently locked out.
    
    Args:
        email: Email address to check
        
    Returns:
        Tuple of (is_locked, remaining_seconds)
    """
    try:
        redis = await get_redis_or_none()
        if not redis:
            return False, 0
            
        key = f"{CACHE_PREFIX_LOGIN_ATTEMPTS}:{email.lower()}"
        
        # Get current attempts
        attempts = await redis.get(key)
        if not attempts:
            return False, 0
            
        current_attempts = int(attempts)
        if current_attempts >= LOCKOUT_THRESHOLD:
            # Get TTL to know when lockout expires
            ttl = await redis.ttl(key)
            return True, max(0, ttl)
            
        return False, 0
        
    except Exception as e:
        logger.warning(f"Failed to check lockout: {e}")
        return False, 0


async def clear_login_attempts(email: str) -> bool:
    """
    Clear login attempts after successful login.
    
    Args:
        email: Email address to clear
        
    Returns:
        True if cleared successfully
    """
    try:
        redis = await get_redis_or_none()
        if not redis:
            return False
            
        key = f"{CACHE_PREFIX_LOGIN_ATTEMPTS}:{email.lower()}"
        await redis.delete(key)
        return True
        
    except Exception as e:
        logger.warning(f"Failed to clear login attempts: {e}")
        return False


async def get_login_attempts(email: str) -> int:
    """
    Get current number of failed login attempts.
    
    Args:
        email: Email address to check
        
    Returns:
        Number of failed attempts
    """
    try:
        redis = await get_redis_or_none()
        if not redis:
            return 0
            
        key = f"{CACHE_PREFIX_LOGIN_ATTEMPTS}:{email.lower()}"
        attempts = await redis.get(key)
        return int(attempts) if attempts else 0
        
    except Exception as e:
        logger.warning(f"Failed to get login attempts: {e}")
        return 0


# =============================================================================
# CACHE STATISTICS
# =============================================================================


async def get_cache_stats() -> Dict[str, Any]:
    """
    Get cache statistics for monitoring.

    Returns key counts per prefix, memory usage, in-process hit/miss metrics,
    and the current cache schema version.
    """
    try:
        redis = await get_redis_or_none()
        if not redis:
            return {
                "status": "unavailable",
                "cache_version": CACHE_VERSION,
                "hit_miss_metrics": _metrics.get_stats(),
                "fallback_rate_limiter": "active",
            }

        info_memory = await redis.info("memory")
        info_stats = await redis.info("stats")

        # Count keys by versioned prefix
        prefixes = [
            CACHE_PREFIX_JOB_ANALYSIS,
            CACHE_PREFIX_COMPANY_RESEARCH,
            CACHE_PREFIX_USER_PROFILE,
            CACHE_PREFIX_WORKFLOW_STATE,
            CACHE_PREFIX_LLM_RESPONSE,
            CACHE_PREFIX_RATE_LIMIT,
            CACHE_PREFIX_INTERVIEW_PREP,
            CACHE_PREFIX_TOOL_RESULT,
        ]

        key_counts: Dict[str, int] = {}
        for prefix in prefixes:
            count = 0
            async for _ in redis.scan_iter(match=f"{CACHE_VERSION}:{prefix}:*"):
                count += 1
            key_counts[prefix] = count

        # Redis-level hit/miss (keyspace hits/misses since last restart)
        keyspace_hits = info_stats.get("keyspace_hits", 0)
        keyspace_misses = info_stats.get("keyspace_misses", 0)
        total_lookups = keyspace_hits + keyspace_misses
        redis_hit_rate = round(keyspace_hits / total_lookups, 3) if total_lookups > 0 else None

        # Memory eviction counter — non-zero means Redis is under memory pressure
        evicted_keys = info_stats.get("evicted_keys", 0)

        return {
            "status": "connected",
            "cache_version": CACHE_VERSION,
            "used_memory": info_memory.get("used_memory_human", "unknown"),
            "used_memory_peak": info_memory.get("used_memory_peak_human", "unknown"),
            "key_counts": key_counts,
            "total_versioned_keys": sum(key_counts.values()),
            "redis_keyspace_hit_rate": redis_hit_rate,
            "redis_evicted_keys": evicted_keys,
            "hit_miss_metrics": _metrics.get_stats(),
            "fallback_rate_limiter": "standby",
        }

    except Exception as e:
        logger.error(f"Cache stats error: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}

