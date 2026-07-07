"""
Shared fixtures for utils unit tests.

Stubs GCP packages (same pattern as tests/test_agents/conftest.py) and provides
a reusable mock Redis client for cache/auth/maintenance tests.
"""

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# Stub GCP packages before utils modules import them.
_GCP_STUBS = [
    "google.cloud.tasks_v2",
    "google.cloud.tasks_v2.services",
    "google.cloud.tasks_v2.services.cloud_tasks",
    "google.cloud.tasks_v2.types",
    "google.cloud.pubsub_v1",
    "google.cloud.error_reporting",
]
for _mod in _GCP_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


@pytest.fixture
def mock_redis():
    """Async Redis mock with common methods pre-wired."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.setex = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.ttl = AsyncMock(return_value=60)
    redis.ping = AsyncMock(return_value=True)
    redis.info = AsyncMock(return_value={"keyspace_hits": 10, "keyspace_misses": 2, "evicted_keys": 0})
    redis.pipeline = MagicMock(return_value=_MockPipeline())
    redis.scan_iter = _async_iter([])
    redis.close = AsyncMock()
    return redis


class _MockPipeline:
    """Minimal Redis pipeline mock."""

    def __init__(self) -> None:
        self._ops: list = []

    def incr(self, key: str) -> "_MockPipeline":
        self._ops.append(("incr", key))
        return self

    def expire(self, key: str, ttl: int) -> "_MockPipeline":
        self._ops.append(("expire", key, ttl))
        return self

    def get(self, key: str) -> "_MockPipeline":
        self._ops.append(("get", key))
        return self

    def ttl(self, key: str) -> "_MockPipeline":
        self._ops.append(("ttl", key))
        return self

    async def execute(self) -> list:
        if not self._ops:
            return [1]
        if self._ops[0][0] == "get":
            return [None, 60]
        return [1]


async def _async_iter(items):
    for item in items:
        yield item
