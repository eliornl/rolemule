"""
Direct-handler coverage for remaining api/websocket.py gaps.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import WebSocketDisconnect
from starlette.websockets import WebSocketState

from api import websocket as ws_module
from api.websocket import manager


class TestWebSocketRemainingHandlers:
    @pytest.mark.asyncio
    async def test_workflow_updates_websocket_disconnect_inner_loop(self) -> None:
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())
        mock_ws.client_state = WebSocketState.CONNECTED

        with (
            patch("api.websocket.verify_websocket_token", AsyncMock(return_value={"sub": "ws-user"})),
            patch.object(manager, "connect", AsyncMock(return_value=True)),
            patch.object(manager, "disconnect") as disconnect,
        ):
            await ws_module.workflow_updates(
                mock_ws,
                session_id=str(uuid.uuid4()),
                token="valid",
            )
        disconnect.assert_called_once_with(mock_ws)

    @pytest.mark.asyncio
    async def test_user_updates_invalid_json_closes(self) -> None:
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.receive_text = AsyncMock(return_value="not-json")
        mock_ws.client_state = WebSocketState.CONNECTED

        with (
            patch("api.websocket.verify_websocket_token", AsyncMock(return_value={"sub": "ws-user"})),
            patch.object(manager, "connect", AsyncMock(return_value=True)),
            patch.object(manager, "disconnect"),
        ):
            await ws_module.user_updates(mock_ws, token="valid")
        mock_ws.close.assert_called()

    @pytest.mark.asyncio
    async def test_user_updates_websocket_disconnect(self) -> None:
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())
        mock_ws.client_state = WebSocketState.CONNECTED

        with (
            patch("api.websocket.verify_websocket_token", AsyncMock(return_value={"sub": "ws-user"})),
            patch.object(manager, "connect", AsyncMock(return_value=True)),
            patch.object(manager, "disconnect") as disconnect,
        ):
            await ws_module.user_updates(mock_ws, token="valid")
        disconnect.assert_called_once_with(mock_ws)

    @pytest.mark.asyncio
    async def test_user_updates_invalid_token_closes(self) -> None:
        mock_ws = AsyncMock()
        mock_ws.close = AsyncMock()
        with patch("api.websocket.verify_websocket_token", AsyncMock(return_value=None)):
            await ws_module.user_updates(mock_ws, token="bad")
        mock_ws.close.assert_called_once()

        mock_ws = AsyncMock()
        with (
            patch("api.websocket.verify_websocket_token", AsyncMock(return_value={"sub": "ws-user"})),
            patch.object(manager, "connect", AsyncMock(return_value=False)),
        ):
            await ws_module.user_updates(mock_ws, token="valid")
        mock_ws.accept.assert_not_called()
