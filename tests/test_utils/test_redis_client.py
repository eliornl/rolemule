"""Tests for utils/redis_client.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import ConnectionError

import utils.redis_client as redis_mod
from utils.redis_client import (
    check_redis_health,
    close_redis_connection,
    connect_to_redis,
    get_redis_client,
)


@pytest.fixture(autouse=True)
def reset_redis_global():
    redis_mod._redis_client = None
    yield
    redis_mod._redis_client = None


@pytest.mark.asyncio
async def test_check_redis_health_no_client() -> None:
    assert await check_redis_health() is False


@pytest.mark.asyncio
async def test_check_redis_health_ok() -> None:
    client = AsyncMock()
    client.ping = AsyncMock(return_value=True)
    redis_mod._redis_client = client
    assert await check_redis_health() is True


@pytest.mark.asyncio
async def test_check_redis_health_ping_fails() -> None:
    client = AsyncMock()
    client.ping = AsyncMock(side_effect=RuntimeError("down"))
    redis_mod._redis_client = client
    assert await check_redis_health() is False


@pytest.mark.asyncio
async def test_get_redis_client_connects_when_missing() -> None:
    mock_client = AsyncMock()

    async def _connect():
        redis_mod._redis_client = mock_client
        return mock_client

    with patch.object(redis_mod, "connect_to_redis", AsyncMock(side_effect=_connect)):
        client = await get_redis_client()
        assert client is mock_client


@pytest.mark.asyncio
async def test_connect_to_redis_success() -> None:
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    with patch("utils.redis_client.redis.from_url", return_value=mock_client), \
         patch("utils.redis_client.get_settings") as gs, \
         patch("utils.redis_client.get_database_settings") as dbs, \
         patch.object(redis_mod, "check_redis_health", AsyncMock(return_value=True)):
        gs.return_value = MagicMock(redis_url="redis://localhost:6379/0")
        dbs.return_value = MagicMock(redis_connection_params={})
        client = await connect_to_redis()
        assert client is mock_client


@pytest.mark.asyncio
async def test_connect_to_redis_health_check_fails() -> None:
    mock_client = AsyncMock()
    with patch("utils.redis_client.redis.from_url", return_value=mock_client), \
         patch("utils.redis_client.get_settings") as gs, \
         patch("utils.redis_client.get_database_settings") as dbs, \
         patch.object(redis_mod, "check_redis_health", AsyncMock(return_value=False)):
        gs.return_value = MagicMock(redis_url="redis://localhost:6379/0")
        dbs.return_value = MagicMock(redis_connection_params={})
        with pytest.raises(ConnectionError):
            await connect_to_redis()


@pytest.mark.asyncio
async def test_close_redis_connection() -> None:
    client = AsyncMock()
    redis_mod._redis_client = client
    await close_redis_connection()
    client.close.assert_awaited()
    assert redis_mod._redis_client is None


@pytest.mark.asyncio
async def test_connect_to_redis_generic_exception() -> None:
    with patch("utils.redis_client.redis.from_url", side_effect=RuntimeError("unexpected")):
        with pytest.raises(RuntimeError, match="unexpected"):
            await connect_to_redis()
