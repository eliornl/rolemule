"""
WebSocket API for real-time workflow updates.
Provides instant push notifications for workflow status changes instead of polling.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Request, Depends, status
from starlette.websockets import WebSocketState
import jwt

from config.settings import get_settings
from utils.auth import get_current_user
from utils.error_reporting import report_exception
from utils.logging_config import get_structured_logger

_WS_MAX_MESSAGE_BYTES = 64 * 1024  # 64 KB — reject oversized client messages

# =============================================================================
# CONFIGURATION
# =============================================================================

logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)
router = APIRouter()

# Connection limits
MAX_CONNECTIONS_PER_USER = 5  # Maximum WebSocket connections per user
MAX_CONNECTIONS_PER_SESSION = 3  # Maximum connections watching same session

# =============================================================================
# CONNECTION MANAGER
# =============================================================================


class ConnectionManager:
    """
    Manages WebSocket connections for workflow updates.
    
    Supports:
    - Multiple connections per user (with limits)
    - Session-specific subscriptions
    - Broadcast to all user connections
    - Graceful disconnect handling
    - Connection limit enforcement
    """

    def __init__(self):
        # Map: user_id -> set of (websocket, session_id) tuples
        self._user_connections: Dict[str, Set[tuple]] = {}
        # Map: session_id -> set of websockets
        self._session_connections: Dict[str, Set[WebSocket]] = {}
        # Map: websocket -> (user_id, session_id)
        self._connection_info: Dict[WebSocket, tuple] = {}

    def _check_connection_limits(
        self, user_id: str, session_id: Optional[str] = None
    ) -> tuple[bool, str]:
        """
        Check if connection limits allow a new connection.
        
        Args:
            user_id: User ID requesting connection
            session_id: Optional session ID
            
        Returns:
            Tuple of (allowed, reason_if_denied)
        """
        # Check user connection limit
        user_conn_count = len(self._user_connections.get(user_id, set()))
        if user_conn_count >= MAX_CONNECTIONS_PER_USER:
            return False, f"Maximum connections per user ({MAX_CONNECTIONS_PER_USER}) exceeded"
        
        # Check session connection limit if session specified
        if session_id:
            session_conn_count = len(self._session_connections.get(session_id, set()))
            if session_conn_count >= MAX_CONNECTIONS_PER_SESSION:
                return False, f"Maximum connections per session ({MAX_CONNECTIONS_PER_SESSION}) exceeded"
        
        return True, ""

    async def connect(
        self, websocket: WebSocket, user_id: str, session_id: Optional[str] = None
    ) -> bool:
        """
        Accept a new WebSocket connection with limit checking.
        
        Args:
            websocket: The WebSocket connection
            user_id: Authenticated user ID
            session_id: Optional workflow session ID to subscribe to
            
        Returns:
            True if connection accepted, False if rejected due to limits
        """
        # Check connection limits before accepting
        allowed, reason = self._check_connection_limits(user_id, session_id)
        if not allowed:
            logger.warning(
                f"WebSocket connection rejected for user {user_id[:8]}...: {reason}"
            )
            await websocket.close(code=4429, reason=reason)  # Custom code for rate limit
            return False
        
        await websocket.accept()
        
        # Track by user
        if user_id not in self._user_connections:
            self._user_connections[user_id] = set()
        self._user_connections[user_id].add((websocket, session_id))
        
        # Track by session if specified
        if session_id:
            if session_id not in self._session_connections:
                self._session_connections[session_id] = set()
            self._session_connections[session_id].add(websocket)
        
        # Track connection info for cleanup
        self._connection_info[websocket] = (user_id, session_id)
        
        logger.info(
            f"WebSocket connected: user={user_id[:8]}..., session={session_id or 'all'}, "
            f"user_connections={len(self._user_connections[user_id])}"
        )
        return True

    def disconnect(self, websocket: WebSocket) -> None:
        """
        Remove a WebSocket connection.
        
        Args:
            websocket: The WebSocket connection to remove
        """
        if websocket not in self._connection_info:
            return
            
        user_id, session_id = self._connection_info[websocket]
        
        # Remove from user connections
        if user_id in self._user_connections:
            self._user_connections[user_id].discard((websocket, session_id))
            if not self._user_connections[user_id]:
                del self._user_connections[user_id]
        
        # Remove from session connections
        if session_id and session_id in self._session_connections:
            self._session_connections[session_id].discard(websocket)
            if not self._session_connections[session_id]:
                del self._session_connections[session_id]
        
        # Remove connection info
        del self._connection_info[websocket]
        
        logger.info(
            f"WebSocket disconnected: user={user_id[:8]}..., session={session_id or 'all'}"
        )

    async def send_to_user(self, user_id: str, message: Dict[str, Any]) -> None:
        """
        Send a message to all connections for a user.
        
        Args:
            user_id: Target user ID
            message: Message payload to send
        """
        if user_id not in self._user_connections:
            return
            
        dead_connections = []
        for websocket, _ in self._user_connections[user_id]:
            try:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to user {user_id[:8]}...: {e}")
                dead_connections.append(websocket)
        
        # Clean up dead connections
        for ws in dead_connections:
            self.disconnect(ws)

    async def send_to_session(self, session_id: str, message: Dict[str, Any]) -> None:
        """
        Send a message to all connections watching a specific session.
        
        Args:
            session_id: Target session ID
            message: Message payload to send
        """
        if session_id not in self._session_connections:
            return
            
        dead_connections = []
        for websocket in self._session_connections[session_id]:
            try:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to session {session_id[:8]}...: {e}")
                dead_connections.append(websocket)
        
        # Clean up dead connections
        for ws in dead_connections:
            self.disconnect(ws)

    def get_connection_count(self) -> Dict[str, int]:
        """Get connection statistics."""
        return {
            "total_users": len(self._user_connections),
            "total_connections": len(self._connection_info),
            "total_sessions": len(self._session_connections),
        }


# Global connection manager instance
manager = ConnectionManager()


# =============================================================================
# AUTHENTICATION HELPER
# =============================================================================


async def verify_websocket_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify JWT token for WebSocket authentication including revocation checks.

    Checks: signature, expiry, jti blocklist, and per-user invalidation timestamp.
    Returns the decoded payload if all checks pass, None otherwise.
    """
    try:
        settings = get_settings()
        payload: Dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        logger.warning("WebSocket token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"WebSocket token invalid: {e}")
        return None

    # Check jti blocklist (covers individual token revocation and logout)
    from utils.auth import _is_token_revoked, _INVALIDATED_PREFIX
    jti: Optional[str] = payload.get("jti")
    if jti and await _is_token_revoked(jti):
        logger.warning("WebSocket rejected: revoked token (jti=%s)", jti[:8])
        return None

    # Check per-user invalidation timestamp (covers password change, account recovery)
    user_id_str: Optional[str] = payload.get("sub") or payload.get("user_id") or payload.get("id")
    iat: Optional[float] = payload.get("iat")
    if user_id_str and iat is not None:
        try:
            from utils.redis_client import get_redis_client
            redis_client = await get_redis_client()
            if redis_client:
                inv_ts = await redis_client.get(f"{_INVALIDATED_PREFIX}{user_id_str}")
                if inv_ts and float(inv_ts) > iat:
                    logger.warning("WebSocket rejected: token issued before user invalidation")
                    return None
        except Exception as e:
            logger.debug(f"WebSocket user invalidation check skipped (Redis error): {e}")

    return payload


# =============================================================================
# WEBSOCKET ENDPOINTS
# =============================================================================


@router.websocket("/ws/workflow/{session_id}")
async def workflow_updates(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(..., description="JWT authentication token"),
):
    """
    WebSocket endpoint for workflow-specific updates.
    
    Receives real-time updates for a specific workflow session:
    - Agent status changes (started, completed, failed)
    - Workflow phase transitions
    - Completion/failure notifications
    
    Query params:
        token: JWT authentication token (required)
    
    Message format:
    {
        "type": "agent_update" | "phase_change" | "workflow_complete" | "workflow_error",
        "session_id": "...",
        "data": { ... },
        "timestamp": "ISO8601"
    }
    """
    # Verify token
    payload = await verify_websocket_token(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    user_id = payload.get("sub") or payload.get("id")
    if not user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    # Connect and handle messages (returns False if limit exceeded)
    connected = await manager.connect(websocket, str(user_id), session_id)
    if not connected:
        return  # Connection was rejected due to limits
    
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "session_id": session_id,
            "message": "Subscribed to workflow updates",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        # Keep connection alive and handle incoming messages
        try:
            while True:
                try:
                    # Enforce message size limit before JSON parsing
                    raw = await websocket.receive_text()
                    if len(raw) > _WS_MAX_MESSAGE_BYTES:
                        await websocket.close(code=status.WS_1009_MESSAGE_TOO_BIG)
                        break
                    try:
                        data = json.loads(raw)
                    except (json.JSONDecodeError, ValueError):
                        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                        break

                    # Handle ping
                    if isinstance(data, dict) and data.get("type") == "ping":
                        await websocket.send_json({
                            "type": "pong",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })

                except WebSocketDisconnect:
                    break
        except Exception as exc:
            await report_exception(exc, user_id=str(user_id))
            logger.error("Unexpected error in workflow WebSocket", exc_info=True)
                
    finally:
        manager.disconnect(websocket)


@router.websocket("/ws/user")
async def user_updates(
    websocket: WebSocket,
    token: str = Query(..., description="JWT authentication token"),
):
    """
    WebSocket endpoint for all user updates.
    
    Receives real-time updates for all user workflows:
    - New workflow started
    - Any workflow status changes
    - Application updates
    
    Query params:
        token: JWT authentication token (required)
    """
    # Verify token
    payload = await verify_websocket_token(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    user_id = payload.get("sub") or payload.get("id")
    if not user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    # Connect without session filter (returns False if limit exceeded)
    connected = await manager.connect(websocket, str(user_id), None)
    if not connected:
        return  # Connection was rejected due to limits
    
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "message": "Subscribed to all user updates",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        # Keep connection alive
        try:
            while True:
                try:
                    # Enforce message size limit before JSON parsing
                    raw = await websocket.receive_text()
                    if len(raw) > _WS_MAX_MESSAGE_BYTES:
                        await websocket.close(code=status.WS_1009_MESSAGE_TOO_BIG)
                        break
                    try:
                        data = json.loads(raw)
                    except (json.JSONDecodeError, ValueError):
                        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                        break

                    # Handle ping
                    if isinstance(data, dict) and data.get("type") == "ping":
                        await websocket.send_json({
                            "type": "pong",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })

                except WebSocketDisconnect:
                    break
        except Exception as exc:
            await report_exception(exc, user_id=str(user_id))
            logger.error("Unexpected error in user WebSocket", exc_info=True)
                
    finally:
        manager.disconnect(websocket)


# =============================================================================
# BROADCAST FUNCTIONS (for use by workflow)
# =============================================================================


async def broadcast_agent_update(
    user_id: str,
    session_id: str,
    agent_name: str,
    status: str,
    message: Optional[str] = None,
) -> None:
    """
    Broadcast agent status update to connected clients.
    
    Args:
        user_id: User ID to notify
        session_id: Workflow session ID
        agent_name: Name of the agent
        status: Agent status (running, completed, failed)
        message: Optional additional message
    """
    payload = {
        "type": "agent_update",
        "session_id": session_id,
        "data": {
            "agent": agent_name,
            "status": status,
            "message": message,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    # Send to session-specific subscribers
    await manager.send_to_session(session_id, payload)
    
    # Also send to general user subscribers
    await manager.send_to_user(user_id, payload)


async def broadcast_phase_change(
    user_id: str,
    session_id: str,
    phase: str,
    progress_percentage: int,
) -> None:
    """
    Broadcast workflow phase change.
    
    Args:
        user_id: User ID to notify
        session_id: Workflow session ID
        phase: New workflow phase
        progress_percentage: Estimated progress (0-100)
    """
    payload = {
        "type": "phase_change",
        "session_id": session_id,
        "data": {
            "phase": phase,
            "progress": progress_percentage,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    await manager.send_to_session(session_id, payload)
    await manager.send_to_user(user_id, payload)


async def broadcast_workflow_complete(
    user_id: str,
    session_id: str,
    result_summary: Dict[str, Any],
) -> None:
    """
    Broadcast workflow completion.
    
    Args:
        user_id: User ID to notify
        session_id: Workflow session ID
        result_summary: Summary of workflow results
    """
    payload = {
        "type": "workflow_complete",
        "session_id": session_id,
        "data": result_summary,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    await manager.send_to_session(session_id, payload)
    await manager.send_to_user(user_id, payload)


async def broadcast_workflow_error(
    user_id: str,
    session_id: str,
    error_message: str,
    failed_agent: Optional[str] = None,
) -> None:
    """
    Broadcast workflow error.
    
    Args:
        user_id: User ID to notify
        session_id: Workflow session ID
        error_message: Error description
        failed_agent: Agent that failed (if applicable)
    """
    payload = {
        "type": "workflow_error",
        "session_id": session_id,
        "data": {
            "error": error_message,
            "failed_agent": failed_agent,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    await manager.send_to_session(session_id, payload)
    await manager.send_to_user(user_id, payload)


async def broadcast_gate_decision(
    user_id: str,
    session_id: str,
    match_score: float,
    recommendation: str,
) -> None:
    """
    Broadcast gate decision requiring user confirmation.
    
    Args:
        user_id: User ID to notify
        session_id: Workflow session ID
        match_score: Profile match score (0-1)
        recommendation: AI recommendation
    """
    payload = {
        "type": "gate_decision",
        "session_id": session_id,
        "data": {
            "match_score": match_score,
            "recommendation": recommendation,
            "requires_confirmation": True,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    await manager.send_to_session(session_id, payload)
    await manager.send_to_user(user_id, payload)


async def broadcast_workflow_resumed(
    user_id: str,
    session_id: str,
) -> None:
    """
    Broadcast that a workflow has resumed after gate confirmation.

    Args:
        user_id: User ID to notify
        session_id: Workflow session ID
    """
    payload = {
        "type": "workflow_resumed",
        "session_id": session_id,
        "data": {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    await manager.send_to_session(session_id, payload)
    await manager.send_to_user(user_id, payload)


async def broadcast_document_generation_started(
    user_id: str,
    session_id: str,
) -> None:
    """
    Broadcast that document generation (resume + cover letter) has started.

    Args:
        user_id: User ID to notify
        session_id: Workflow session ID
    """
    payload = {
        "type": "document_generation_started",
        "session_id": session_id,
        "data": {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    await manager.send_to_session(session_id, payload)
    await manager.send_to_user(user_id, payload)


async def broadcast_interview_prep_started(
    user_id: str,
    session_id: str,
) -> None:
    """
    Broadcast that interview prep generation has started.

    Args:
        user_id: User ID to notify
        session_id: Workflow session ID
    """
    payload = {
        "type": "interview_prep_started",
        "session_id": session_id,
        "data": {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    await manager.send_to_session(session_id, payload)
    await manager.send_to_user(user_id, payload)


async def broadcast_interview_prep_complete(
    user_id: str,
    session_id: str,
) -> None:
    """
    Broadcast that interview prep generation has completed successfully.

    Args:
        user_id: User ID to notify
        session_id: Workflow session ID
    """
    payload = {
        "type": "interview_prep_complete",
        "session_id": session_id,
        "data": {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    await manager.send_to_session(session_id, payload)
    await manager.send_to_user(user_id, payload)


async def broadcast_interview_prep_error(
    user_id: str,
    session_id: str,
    error_message: str,
) -> None:
    """
    Broadcast that interview prep generation has failed.

    Args:
        user_id: User ID to notify
        session_id: Workflow session ID
        error_message: Description of the failure
    """
    payload = {
        "type": "interview_prep_error",
        "session_id": session_id,
        "data": {"error": error_message},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    await manager.send_to_session(session_id, payload)
    await manager.send_to_user(user_id, payload)


# =============================================================================
# CV OPTIMIZATION BROADCASTS
# =============================================================================


async def broadcast_cv_optimization_started(
    user_id: str,
    session_id: str,
) -> None:
    """
    Broadcast that CV optimization loop has started.

    Args:
        user_id: User ID to notify
        session_id: Workflow session ID
    """
    payload = {
        "type": "cv_optimization_started",
        "session_id": session_id,
        "data": {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    await manager.send_to_session(session_id, payload)
    await manager.send_to_user(user_id, payload)


async def broadcast_cv_optimization_iteration(
    user_id: str,
    session_id: str,
    iteration: int,
    score: float,
    strengths: List[str],
    gaps: List[str],
    action_items: List[str],
) -> None:
    """
    Broadcast the result of one optimization iteration.

    Args:
        user_id: User ID to notify
        session_id: Workflow session ID
        iteration: Current iteration number (0-indexed)
        score: Hiring manager score for this iteration (0-10)
        strengths: List of CV strengths identified
        gaps: List of CV gaps identified
        action_items: Specific improvement actions taken/suggested
    """
    payload = {
        "type": "cv_optimization_iteration",
        "session_id": session_id,
        "data": {
            "iteration": iteration,
            "score": score,
            "strengths": strengths,
            "gaps": gaps,
            "action_items": action_items,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    await manager.send_to_session(session_id, payload)
    await manager.send_to_user(user_id, payload)


async def broadcast_cv_optimization_complete(
    user_id: str,
    session_id: str,
    final_score: float,
    stop_reason: str,
    iteration_count: int,
) -> None:
    """
    Broadcast that CV optimization has completed successfully.

    Args:
        user_id: User ID to notify
        session_id: Workflow session ID
        final_score: Best score achieved across all iterations
        stop_reason: Why the loop stopped (score_threshold/score_decrease/score_plateau/max_iterations)
        iteration_count: Total number of iterations run
    """
    payload = {
        "type": "cv_optimization_complete",
        "session_id": session_id,
        "data": {
            "final_score": final_score,
            "stop_reason": stop_reason,
            "iteration_count": iteration_count,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    await manager.send_to_session(session_id, payload)
    await manager.send_to_user(user_id, payload)


async def broadcast_cv_optimization_error(
    user_id: str,
    session_id: str,
    error_message: str,
) -> None:
    """
    Broadcast that CV optimization has failed.

    Args:
        user_id: User ID to notify
        session_id: Workflow session ID
        error_message: Description of the failure
    """
    payload = {
        "type": "cv_optimization_error",
        "session_id": session_id,
        "data": {"error": error_message},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    await manager.send_to_session(session_id, payload)
    await manager.send_to_user(user_id, payload)


# =============================================================================
# CONNECTION STATS ENDPOINT
# =============================================================================


@router.get("/ws/stats")
async def websocket_stats(current_user: dict = Depends(get_current_user)):
    """Get WebSocket connection statistics. Requires authentication."""
    return manager.get_connection_count()

