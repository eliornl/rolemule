"""
Tests for api/websocket.py — ConnectionManager, auth, endpoints, broadcasts.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi import WebSocketDisconnect
from starlette.websockets import WebSocketState

from api import websocket as ws_module
from api.websocket import (
    ConnectionManager,
    broadcast_agent_update,
    broadcast_cv_optimization_complete,
    broadcast_cv_optimization_error,
    broadcast_cv_optimization_iteration,
    broadcast_cv_optimization_started,
    broadcast_document_generation_started,
    broadcast_gate_decision,
    broadcast_hiring_outreach_complete,
    broadcast_hiring_outreach_error,
    broadcast_hiring_outreach_started,
    broadcast_interview_prep_complete,
    broadcast_interview_prep_error,
    broadcast_interview_prep_started,
    broadcast_phase_change,
    broadcast_workflow_complete,
    broadcast_workflow_error,
    broadcast_workflow_resumed,
    manager,
    verify_websocket_token,
)
from config.settings import get_security_settings


def _valid_token(user_id: str | None = None, *, jti: str | None = "ws-jti-123") -> str:
    uid = user_id or str(uuid.uuid4())
    sec = get_security_settings()
    payload = {
        "sub": uid,
        "email": f"ws_{uid[:8]}@example.com",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc).timestamp(),
        "jti": str(uuid.uuid4()),
    }
    if jti is not None:
        payload["jti"] = jti
    return jwt.encode(payload, sec.jwt_config["secret_key"], algorithm=sec.jwt_config["algorithm"])


# ---------------------------------------------------------------------------
# ConnectionManager unit tests
# ---------------------------------------------------------------------------


class TestConnectionManager:
    """ConnectionManager limits, connect/disconnect, send helpers."""

    @pytest.mark.asyncio
    async def test_check_user_connection_limit(self):
        cm = ConnectionManager()
        uid = "user-limit-test"
        for i in range(ws_module.MAX_CONNECTIONS_PER_USER):
            mock_ws = AsyncMock()
            mock_ws.accept = AsyncMock()
            await cm.connect(mock_ws, uid, None)
        allowed, reason = cm._check_connection_limits(uid, None)
        assert allowed is False
        assert "Maximum connections per user" in reason

    @pytest.mark.asyncio
    async def test_check_session_connection_limit(self):
        cm = ConnectionManager()
        uid = "session-limit-user"
        sid = "session-limit-id"
        for _ in range(ws_module.MAX_CONNECTIONS_PER_SESSION):
            mock_ws = AsyncMock()
            mock_ws.accept = AsyncMock()
            await cm.connect(mock_ws, uid, sid)
        allowed, reason = cm._check_connection_limits(uid, sid)
        assert allowed is False
        assert "Maximum connections per session" in reason

    @pytest.mark.asyncio
    async def test_connect_rejects_over_limit(self):
        cm = ConnectionManager()
        uid = "reject-user"
        websockets = []
        for _ in range(ws_module.MAX_CONNECTIONS_PER_USER):
            mock_ws = AsyncMock()
            mock_ws.accept = AsyncMock()
            mock_ws.close = AsyncMock()
            await cm.connect(mock_ws, uid, None)
            websockets.append(mock_ws)

        extra = AsyncMock()
        extra.close = AsyncMock()
        ok = await cm.connect(extra, uid, None)
        assert ok is False
        extra.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_unknown_socket_noop(self):
        cm = ConnectionManager()
        cm.disconnect(AsyncMock())  # should not raise

    @pytest.mark.asyncio
    async def test_send_to_user_cleans_dead_connections(self):
        cm = ConnectionManager()
        uid = "send-user"
        live = AsyncMock()
        live.client_state = WebSocketState.CONNECTED
        live.send_json = AsyncMock()
        dead = AsyncMock()
        dead.client_state = WebSocketState.CONNECTED
        dead.send_json = AsyncMock(side_effect=RuntimeError("broken pipe"))

        cm._user_connections[uid] = {(live, None), (dead, None)}
        cm._connection_info[live] = (uid, None)
        cm._connection_info[dead] = (uid, None)

        await cm.send_to_user(uid, {"type": "test"})
        live.send_json.assert_called_once()
        assert dead not in cm._connection_info

    @pytest.mark.asyncio
    async def test_send_to_session_cleans_dead_connections(self):
        cm = ConnectionManager()
        sid = "sess-send"
        live = AsyncMock()
        live.client_state = WebSocketState.CONNECTED
        live.send_json = AsyncMock()
        dead = AsyncMock()
        dead.client_state = WebSocketState.CONNECTED
        dead.send_json = AsyncMock(side_effect=RuntimeError("broken"))

        cm._session_connections[sid] = {live, dead}
        cm._connection_info[live] = ("u1", sid)
        cm._connection_info[dead] = ("u1", sid)

        await cm.send_to_session(sid, {"type": "test"})
        assert dead not in cm._connection_info

    def test_get_connection_count(self):
        stats = manager.get_connection_count()
        assert {"total_users", "total_connections", "total_sessions"} <= set(stats.keys())


# ---------------------------------------------------------------------------
# verify_websocket_token
# ---------------------------------------------------------------------------


class TestVerifyWebsocketToken:
    """JWT verification including revocation checks."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_payload(self):
        uid = str(uuid.uuid4())
        token = _valid_token(uid)
        with (
            patch("utils.auth._is_token_revoked", AsyncMock(return_value=False)),
            patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)),
        ):
            payload = await verify_websocket_token(token)
        assert payload is not None
        assert payload["sub"] == uid

    @pytest.mark.asyncio
    async def test_expired_token_returns_none(self):
        sec = get_security_settings()
        expired = jwt.encode(
            {"sub": "u1", "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
            sec.jwt_config["secret_key"],
            algorithm=sec.jwt_config["algorithm"],
        )
        assert await verify_websocket_token(expired) is None

    @pytest.mark.asyncio
    async def test_revoked_jti_returns_none(self):
        token = _valid_token()
        with patch("utils.auth._is_token_revoked", AsyncMock(return_value=True)):
            assert await verify_websocket_token(token) is None

    @pytest.mark.asyncio
    async def test_user_invalidation_timestamp_rejects_token(self):
        uid = str(uuid.uuid4())
        token = _valid_token(uid)
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=str(datetime.now(timezone.utc).timestamp() + 100))
        with (
            patch("utils.auth._is_token_revoked", AsyncMock(return_value=False)),
            patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_redis)),
        ):
            assert await verify_websocket_token(token) is None


# ---------------------------------------------------------------------------
# WebSocket endpoints (httpx websocket_connect)
# ---------------------------------------------------------------------------


class TestWebSocketEndpoints:
    """WS handlers invoked directly with mock WebSocket objects."""

    @pytest.mark.asyncio
    async def test_user_updates_connect_and_ping_pong(self):
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.receive_text = AsyncMock(
            side_effect=['{"type": "ping"}', WebSocketDisconnect()]
        )
        mock_ws.client_state = WebSocketState.CONNECTED
        mock_ws.close = AsyncMock()

        with (
            patch("api.websocket.verify_websocket_token", AsyncMock(return_value={"sub": "ws-user"})),
            patch.object(manager, "connect", AsyncMock(return_value=True)),
            patch.object(manager, "disconnect") as disconnect,
        ):
            await ws_module.user_updates(mock_ws, token="valid")

        assert mock_ws.send_json.await_count >= 2
        first_call = mock_ws.send_json.await_args_list[0].args[0]
        assert first_call["type"] == "connected"
        disconnect.assert_called_once_with(mock_ws)

    @pytest.mark.asyncio
    async def test_workflow_updates_oversized_message_closes(self):
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.close = AsyncMock()
        oversized = "x" * (ws_module._WS_MAX_MESSAGE_BYTES + 1)
        mock_ws.receive_text = AsyncMock(return_value=oversized)

        with (
            patch("api.websocket.verify_websocket_token", AsyncMock(return_value={"sub": "ws-user"})),
            patch.object(manager, "connect", AsyncMock(return_value=True)),
            patch.object(manager, "disconnect"),
        ):
            await ws_module.workflow_updates(mock_ws, session_id=str(uuid.uuid4()), token="valid")

        mock_ws.close.assert_called()
        close_code = mock_ws.close.await_args.kwargs.get("code") or mock_ws.close.await_args[1].get("code")
        assert close_code == ws_module.status.WS_1009_MESSAGE_TOO_BIG

    @pytest.mark.asyncio
    async def test_workflow_updates_invalid_token_closes(self):
        mock_ws = AsyncMock()
        mock_ws.close = AsyncMock()
        with patch("api.websocket.verify_websocket_token", AsyncMock(return_value=None)):
            await ws_module.workflow_updates(mock_ws, session_id=str(uuid.uuid4()), token="bad")
        mock_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_workflow_updates_missing_user_id_closes(self):
        mock_ws = AsyncMock()
        mock_ws.close = AsyncMock()
        with patch("api.websocket.verify_websocket_token", AsyncMock(return_value={"email": "x@y.com"})):
            await ws_module.workflow_updates(mock_ws, session_id=str(uuid.uuid4()), token="valid")
        mock_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_ws_stats_requires_auth(self, api_client):
        resp = await api_client.get("/api/v1/ws/stats")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_ws_stats_authed(self, authed_client):
        resp = await authed_client.get("/api/v1/ws/stats")
        assert resp.status_code == 200
        assert "total_connections" in resp.json()


# ---------------------------------------------------------------------------
# Broadcast helpers
# ---------------------------------------------------------------------------


class TestBroadcastHelpers:
    """All broadcast_* functions delegate to manager."""

    @pytest.mark.asyncio
    async def test_all_broadcast_functions(self):
        uid = str(uuid.uuid4())
        sid = str(uuid.uuid4())
        with (
            patch.object(manager, "send_to_session", AsyncMock()) as sess,
            patch.object(manager, "send_to_user", AsyncMock()) as user,
        ):
            await broadcast_agent_update(uid, sid, "job_analyzer", "running", "Working")
            await broadcast_phase_change(uid, sid, "analysis", 25)
            await broadcast_workflow_complete(uid, sid, {"ok": True})
            await broadcast_workflow_error(uid, sid, "failed", "job_analyzer")
            await broadcast_gate_decision(uid, sid, 0.8, "Strong match")
            await broadcast_workflow_resumed(uid, sid)
            await broadcast_document_generation_started(uid, sid)
            await broadcast_interview_prep_started(uid, sid)
            await broadcast_interview_prep_complete(uid, sid)
            await broadcast_interview_prep_error(uid, sid, "oops")
            await broadcast_cv_optimization_started(uid, sid)
            await broadcast_cv_optimization_iteration(uid, sid, 1, 7.5, [], [], [])
            await broadcast_cv_optimization_complete(uid, sid, 8.0, "score_threshold", 3)
            await broadcast_cv_optimization_error(uid, sid, "quota")
            await broadcast_hiring_outreach_started(uid, sid)
            await broadcast_hiring_outreach_complete(uid, sid)
            await broadcast_hiring_outreach_error(uid, sid, "failed")

        assert sess.await_count == 17
        assert user.await_count == 17
        first_payload = sess.await_args_list[0].args[1]
        assert first_payload["type"] == "agent_update"


class TestConnectionManagerExtended:
    """Additional ConnectionManager branches."""

    @pytest.mark.asyncio
    async def test_disconnect_cleans_empty_user_and_session_buckets(self):
        cm = ConnectionManager()
        uid = "disconnect-cleanup-user"
        sid = "disconnect-cleanup-session"
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        await cm.connect(mock_ws, uid, sid)
        cm.disconnect(mock_ws)
        assert uid not in cm._user_connections
        assert sid not in cm._session_connections
        assert mock_ws not in cm._connection_info

    @pytest.mark.asyncio
    async def test_send_to_user_no_connections_is_noop(self):
        cm = ConnectionManager()
        await cm.send_to_user("nobody-here", {"type": "test"})

    @pytest.mark.asyncio
    async def test_send_to_session_no_connections_is_noop(self):
        cm = ConnectionManager()
        await cm.send_to_session("no-session", {"type": "test"})


class TestVerifyWebsocketTokenExtended:
    """Additional JWT verification branches."""

    @pytest.mark.asyncio
    async def test_invalid_token_signature_returns_none(self):
        bad = "not.a.valid.jwt.token"
        assert await verify_websocket_token(bad) is None

    @pytest.mark.asyncio
    async def test_redis_invalidation_check_skipped_on_error(self):
        uid = str(uuid.uuid4())
        token = _valid_token(uid)
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=RuntimeError("redis down"))
        with (
            patch("utils.auth._is_token_revoked", AsyncMock(return_value=False)),
            patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_redis)),
        ):
            payload = await verify_websocket_token(token)
        assert payload is not None
        assert payload["sub"] == uid


class TestWebSocketHandlersExtended:
    """Workflow/user handler message loops."""

    @pytest.mark.asyncio
    async def test_workflow_updates_ping_pong_and_invalid_json(self):
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.receive_text = AsyncMock(
            side_effect=['{"type": "ping"}', "not-json", WebSocketDisconnect()]
        )
        mock_ws.client_state = WebSocketState.CONNECTED

        with (
            patch("api.websocket.verify_websocket_token", AsyncMock(return_value={"sub": "ws-user"})),
            patch.object(manager, "connect", AsyncMock(return_value=True)),
            patch.object(manager, "disconnect"),
        ):
            await ws_module.workflow_updates(mock_ws, session_id=str(uuid.uuid4()), token="valid")

        pong_calls = [
            c.args[0] for c in mock_ws.send_json.await_args_list if c.args[0].get("type") == "pong"
        ]
        assert pong_calls
        mock_ws.close.assert_called()

    @pytest.mark.asyncio
    async def test_user_updates_oversized_message_closes(self):
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.close = AsyncMock()
        oversized = "x" * (ws_module._WS_MAX_MESSAGE_BYTES + 1)
        mock_ws.receive_text = AsyncMock(return_value=oversized)

        with (
            patch("api.websocket.verify_websocket_token", AsyncMock(return_value={"sub": "ws-user"})),
            patch.object(manager, "connect", AsyncMock(return_value=True)),
            patch.object(manager, "disconnect"),
        ):
            await ws_module.user_updates(mock_ws, token="valid")

        mock_ws.close.assert_called()

    @pytest.mark.asyncio
    async def test_workflow_updates_connection_limit_rejected(self):
        mock_ws = AsyncMock()
        mock_ws.close = AsyncMock()
        with (
            patch("api.websocket.verify_websocket_token", AsyncMock(return_value={"sub": "ws-user"})),
            patch.object(manager, "connect", AsyncMock(return_value=False)),
        ):
            await ws_module.workflow_updates(mock_ws, session_id=str(uuid.uuid4()), token="valid")
        mock_ws.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_user_updates_missing_user_id_closes(self):
        mock_ws = AsyncMock()
        mock_ws.close = AsyncMock()
        with patch("api.websocket.verify_websocket_token", AsyncMock(return_value={"email": "x@y.com"})):
            await ws_module.user_updates(mock_ws, token="valid")
        mock_ws.close.assert_called_once()


class TestWebSocketExceptionHandling:
    """Unexpected errors inside message loops."""

    @pytest.mark.asyncio
    async def test_workflow_updates_reports_unexpected_exception(self):
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=RuntimeError("loop broke"))
        mock_ws.client_state = WebSocketState.CONNECTED

        with (
            patch("api.websocket.verify_websocket_token", AsyncMock(return_value={"sub": "ws-user"})),
            patch.object(manager, "connect", AsyncMock(return_value=True)),
            patch.object(manager, "disconnect") as disconnect,
            patch("api.websocket.report_exception", AsyncMock()) as report,
        ):
            await ws_module.workflow_updates(mock_ws, session_id=str(uuid.uuid4()), token="valid")

        report.assert_awaited_once()
        disconnect.assert_called_once_with(mock_ws)

    @pytest.mark.asyncio
    async def test_user_updates_ping_pong(self):
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.receive_text = AsyncMock(
            side_effect=['{"type": "ping"}', WebSocketDisconnect()]
        )
        mock_ws.client_state = WebSocketState.CONNECTED

        with (
            patch("api.websocket.verify_websocket_token", AsyncMock(return_value={"sub": "ws-user"})),
            patch.object(manager, "connect", AsyncMock(return_value=True)),
            patch.object(manager, "disconnect"),
        ):
            await ws_module.user_updates(mock_ws, token="valid")

        pong = [c.args[0] for c in mock_ws.send_json.await_args_list if c.args[0].get("type") == "pong"]
        assert pong

