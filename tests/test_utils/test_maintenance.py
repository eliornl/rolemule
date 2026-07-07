"""Tests for utils/maintenance.py."""

from unittest.mock import AsyncMock, patch

import pytest

from utils.maintenance import (
    disable_maintenance_mode,
    enable_maintenance_mode,
    get_maintenance_info,
    is_maintenance_mode,
    should_bypass_maintenance,
)


@pytest.mark.asyncio
async def test_is_maintenance_mode_false_when_redis_down() -> None:
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)):
        assert await is_maintenance_mode() is False


@pytest.mark.asyncio
async def test_is_maintenance_mode_true(mock_redis) -> None:
    mock_redis.get = AsyncMock(return_value="true")
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_redis)):
        assert await is_maintenance_mode() is True


@pytest.mark.asyncio
async def test_get_maintenance_info_defaults(mock_redis) -> None:
    mock_redis.get = AsyncMock(side_effect=[None, None, None])
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_redis)):
        info = await get_maintenance_info()
        assert info["enabled"] is False
        assert "maintenance" in info["message"].lower()


@pytest.mark.asyncio
async def test_get_maintenance_info_enabled(mock_redis) -> None:
    mock_redis.get = AsyncMock(side_effect=["true", "Custom msg", "2026-07-01T00:00:00Z"])
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_redis)):
        info = await get_maintenance_info()
        assert info["enabled"] is True
        assert info["message"] == "Custom msg"
        assert info["estimated_end"] == "2026-07-01T00:00:00Z"


@pytest.mark.asyncio
async def test_enable_maintenance_mode(mock_redis) -> None:
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_redis)):
        ok = await enable_maintenance_mode(message="Upgrading", estimated_end="soon")
        assert ok is True
        mock_redis.set.assert_called()


@pytest.mark.asyncio
async def test_enable_maintenance_mode_no_redis() -> None:
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)):
        assert await enable_maintenance_mode() is False


@pytest.mark.asyncio
async def test_disable_maintenance_mode(mock_redis) -> None:
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_redis)):
        assert await disable_maintenance_mode() is True
        assert mock_redis.delete.call_count >= 1


@pytest.mark.asyncio
async def test_maintenance_redis_exception_returns_safe_defaults() -> None:
    with patch("utils.redis_client.get_redis_client", AsyncMock(side_effect=RuntimeError("fail"))):
        assert await is_maintenance_mode() is False
        info = await get_maintenance_info()
        assert info["enabled"] is False
        assert await enable_maintenance_mode() is False
        assert await disable_maintenance_mode() is False


def test_should_bypass_maintenance() -> None:
    assert should_bypass_maintenance("/api/health") is True
    assert should_bypass_maintenance("/api/v1/admin/maintenance/status") is True
    assert should_bypass_maintenance("/dashboard") is False


@pytest.mark.asyncio
async def test_enable_maintenance_mode_without_message_or_end(mock_redis) -> None:
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_redis)):
        ok = await enable_maintenance_mode()
        assert ok is True
        mock_redis.set.assert_awaited()


@pytest.mark.asyncio
async def test_disable_maintenance_mode_no_redis_client() -> None:
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)):
        assert await disable_maintenance_mode() is False


@pytest.mark.asyncio
async def test_get_maintenance_info_redis_returns_false_flag(mock_redis) -> None:
    mock_redis.get = AsyncMock(side_effect=["false", None, None])
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_redis)):
        info = await get_maintenance_info()
        assert info["enabled"] is False


@pytest.mark.asyncio
async def test_get_maintenance_info_no_redis_client() -> None:
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)):
        info = await get_maintenance_info()
        assert info == {"enabled": False, "message": None, "estimated_end": None}
