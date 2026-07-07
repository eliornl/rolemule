"""
Authentication utilities for the ApplyPilot.
Provides JWT token validation and FastAPI authentication dependencies for protected endpoints.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from fastapi import Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import status
import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config.settings import get_security_settings
from utils.database import get_database
from utils.error_responses import APIError, ErrorCode, forbidden_error
from models.database import User
from utils.logging_config import sanitize_log_value

# =============================================================================
# CONFIGURATION
# =============================================================================

logger: logging.Logger = logging.getLogger(__name__)
security: HTTPBearer = HTTPBearer()
security_settings = get_security_settings()

# Redis key prefix and buffer for the JWT blocklist
_BLOCKLIST_PREFIX: str = "jwt_blocklist:"
_BLOCKLIST_TTL_BUFFER: int = 60  # extra seconds beyond token expiry

# =============================================================================
# AUTHENTICATION DEPENDENCIES
# =============================================================================


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_database),
) -> Dict[str, Any]:
    """
    Get current authenticated user from JWT token.

    This is the main authentication dependency used across the application.
    It validates the JWT token from either URL parameters or Authorization header,
    then fetches current user information from the database.

    Args:
        credentials: HTTP Bearer token from Authorization header (may be None if using URL params)
        request: FastAPI request object for extracting tokens from query parameters
        db: PostgreSQL database session for user lookup

    Returns:
        Dictionary containing current user information and metadata

    Raises:
        HTTPException: 401 for invalid, expired, or malformed tokens
                       401 for non-existent users
    """
    try:
        # Extract token from request (query params first, then header)
        token = extract_token_from_request(request)

        # If no token found in query params, use the header token
        if not token and credentials:
            token = credentials.credentials

        if not token:
            raise APIError(
                ErrorCode.AUTH_UNAUTHORIZED,
                "No authentication token provided",
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Validate and decode JWT token
        user_info: Optional[Dict[str, Any]] = await _validate_jwt_token(token, db)

        if not user_info:
            raise APIError(
                ErrorCode.AUTH_TOKEN_INVALID,
                "Invalid authentication credentials",
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user_info

    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        raise APIError(
            ErrorCode.AUTH_TOKEN_EXPIRED,
            "Token has expired",
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        logger.warning("Invalid token provided")
        raise APIError(
            ErrorCode.AUTH_TOKEN_INVALID,
            "Invalid token",
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (APIError, Exception) as e:
        if isinstance(e, APIError):
            raise
        logger.error(f"Authentication error: {e}", exc_info=True)
        raise APIError(
            ErrorCode.AUTH_UNAUTHORIZED,
            "Authentication failed",
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_admin(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Require the current user to have admin privileges.

    Args:
        current_user: Current user from get_current_user dependency

    Returns:
        User information if user is an admin

    Raises:
        HTTPException: 403 if user is not an admin
    """
    if not current_user.get("is_admin", False):
        raise forbidden_error("Admin privileges required")
    return current_user


async def get_current_user_with_complete_profile(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get current user with complete profile requirement.

    Ensures the current user has completed their profile setup
    before allowing access to profile-dependent endpoints.

    Args:
        current_user: Current user from get_current_user dependency

    Returns:
        User information with complete profile

    Raises:
        HTTPException: 403 if profile is not completed
    """
    if not current_user.get("profile_completed", False):
        raise forbidden_error("Profile setup must be completed to access this resource")

    return current_user


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def extract_token_from_request(request: Request) -> Optional[str]:
    """
    Extract authentication token from request.

    For WebSocket connections, tokens may be passed as query parameters because
    the WebSocket protocol does not support custom headers.  For all other HTTP
    requests only the Authorization header is accepted — tokens in URL query
    parameters leak into server logs, browser history, and Referer headers.

    Args:
        request: The FastAPI Request object containing headers and query parameters

    Returns:
        The extracted token or None if not found
    """
    # Allow query-param tokens only for WebSocket upgrade requests
    is_websocket = request.url.path.startswith("/api/ws/")
    if is_websocket:
        token_param: Optional[str] = request.query_params.get(
            "token"
        ) or request.query_params.get("access_token")
        if token_param:
            logger.debug("WebSocket token found in query parameters")
            return token_param

    # For all paths: accept the Authorization header
    auth_header: Optional[str] = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        logger.debug("Token found in Authorization header")
        return auth_header.replace("Bearer ", "").strip()

    logger.debug("No token found in request")
    return None


def create_access_token(data: dict, expire_hours: Optional[int] = None) -> str:
    """
    Create a new access token.

    A unique `jti` (JWT ID) and `iat` (issued-at) claim are always added so
    that tokens can be individually revoked via the blocklist.

    Args:
        data: The data to encode in the token.
        expire_hours: Override the default expiry in hours.

    Returns:
        The encoded JWT token.
    """
    to_encode: Dict[str, Any] = data.copy()
    hours = expire_hours if expire_hours is not None else security_settings.jwt_config["expire_hours"]
    now = datetime.now(timezone.utc)
    expire: datetime = now + timedelta(hours=hours)
    to_encode.update({
        "exp": expire,
        "iat": now,
        "nbf": now,
        "jti": str(uuid.uuid4()),
    })
    encoded_jwt: str = jwt.encode(
        to_encode,
        security_settings.jwt_config["secret_key"],
        algorithm=security_settings.jwt_config["algorithm"],
    )
    return encoded_jwt


async def revoke_token(token: str) -> bool:
    """
    Add a JWT to the blocklist so it cannot be used again.

    Stores the token's `jti` in Redis with a TTL equal to the remaining
    token lifetime plus a small buffer.  If Redis is unavailable the revocation
    silently fails (fail-open) — log the event so operators can investigate.

    Args:
        token: The raw JWT string to revoke.

    Returns:
        True if the token was successfully blocklisted, False otherwise.
    """
    try:
        from utils.redis_client import get_redis_client
        payload: Dict[str, Any] = jwt.decode(
            token,
            security_settings.jwt_config["secret_key"],
            algorithms=[security_settings.jwt_config["algorithm"]],
        )
        jti: Optional[str] = payload.get("jti")
        exp = payload.get("exp")

        if not jti or not exp:
            logger.warning("Cannot revoke token: missing jti or exp claim")
            return False

        ttl = max(1, int(exp - datetime.now(timezone.utc).timestamp()) + _BLOCKLIST_TTL_BUFFER)
        redis_client = await get_redis_client()
        if redis_client:
            await redis_client.setex(f"{_BLOCKLIST_PREFIX}{jti}", ttl, "1")
            logger.info(f"JWT {jti[:8]}… added to blocklist (TTL {ttl}s)")
            return True

        logger.warning("Cannot revoke token: Redis unavailable")
        return False

    except jwt.ExpiredSignatureError:
        logger.debug("Revoke called on already-expired token — no-op")
        return True
    except Exception as e:
        logger.error(f"Token revocation failed: {e}", exc_info=True)
        return False


_INVALIDATED_PREFIX = "user_invalidated_before:"


async def invalidate_all_user_tokens(user_id: str) -> bool:
    """
    Record a per-user invalidation timestamp in Redis.
    Any token whose `iat` (issued-at) is earlier than this timestamp will be
    rejected, effectively revoking all tokens issued before this point.

    Used on password change and account compromise recovery.

    Args:
        user_id: UUID string of the user whose tokens should be invalidated.

    Returns:
        True if the key was stored, False on Redis error.
    """
    try:
        from utils.redis_client import get_redis_client
        from datetime import datetime, timezone
        redis_client = await get_redis_client()
        if redis_client:
            key = f"{_INVALIDATED_PREFIX}{user_id}"
            # Store as Unix timestamp float with a TTL matching max token lifetime
            # (24h for regular tokens + 7 days for remember-me = 8 days max)
            # Store as integer seconds to match PyJWT's integer `iat` encoding.
            # Floats would be fractionally larger than the new token's `iat` (also
            # issued at "now"), causing the new token to be rejected immediately.
            now_ts = int(datetime.now(timezone.utc).timestamp())
            await redis_client.set(key, str(now_ts), ex=8 * 24 * 3600)
            logger.info(
                "Invalidated all tokens for user %s",
                sanitize_log_value(str(user_id)[:8]),
            )
            return True
        logger.warning("Cannot invalidate user tokens: Redis unavailable")
        return False
    except Exception as e:
        logger.warning(f"Failed to invalidate user tokens: {e}")
        return False


async def _is_token_revoked(jti: str) -> bool:
    """
    Check whether a token JTI is in the blocklist.

    Fails **closed** when Redis is unavailable — treats the token as revoked
    so that a Redis outage cannot be exploited to bypass revocation.
    Monitor Redis availability separately.

    Args:
        jti: The JWT ID to look up.

    Returns:
        True if the token has been revoked (or Redis is unreachable), False otherwise.
    """
    try:
        from utils.redis_client import get_redis_client
        redis_client = await get_redis_client()
        if redis_client:
            result = await redis_client.get(f"{_BLOCKLIST_PREFIX}{jti}")
            return result is not None
        logger.warning("Blocklist check: Redis unavailable — failing closed (token treated as revoked)")
        return True
    except Exception as e:
        logger.warning(f"Blocklist check failed (Redis error): {e} — failing closed (token treated as revoked)")
        return True


async def _validate_jwt_token(
    token: str, db: AsyncSession
) -> Optional[Dict[str, Any]]:
    """
    Validate JWT token and return user information from database.

    This internal function handles JWT token validation and user lookup.
    It ensures the token is valid and the user still exists in the database.

    Args:
        token: JWT token string to validate
        db: PostgreSQL database session for user lookup

    Returns:
        Dictionary containing user information if valid, None otherwise

    Raises:
        jwt.ExpiredSignatureError: If token has expired
        jwt.InvalidTokenError: If token is malformed or invalid

    Note:
        This is an internal function and should not be called directly.
        Use the authentication dependencies instead.
    """
    try:
        # Decode and validate JWT token
        payload: Dict[str, Any] = jwt.decode(
            token,
            security_settings.jwt_config["secret_key"],
            algorithms=[security_settings.jwt_config["algorithm"]],
        )

        # Reject non-access tokens used as access tokens (e.g., password_reset tokens)
        token_type: Optional[str] = payload.get("type")
        if token_type is not None and token_type != "access":
            logger.warning("Rejected token with wrong type (type=%s)", token_type)
            return None

        # Check revocation blocklist
        jti: Optional[str] = payload.get("jti")
        if jti and await _is_token_revoked(jti):
            logger.warning("Rejected revoked token (jti=%s)", jti[:8] if jti else "?")
            return None

        # Check per-user invalidation timestamp (set on password change, account recovery)
        user_id_for_check: Optional[str] = payload.get("sub") or payload.get("user_id") or payload.get("id")
        iat: Optional[float] = payload.get("iat")
        if user_id_for_check and iat is not None:
            try:
                from utils.redis_client import get_redis_client
                redis_client = await get_redis_client()
                if redis_client:
                    inv_key = f"{_INVALIDATED_PREFIX}{user_id_for_check}"
                    inv_ts = await redis_client.get(inv_key)
                    if inv_ts and float(inv_ts) > iat:
                        logger.warning("Rejected token issued before user invalidation (user=%s)", str(user_id_for_check)[:8])
                        return None
            except Exception as e:
                logger.debug(f"User invalidation check skipped (Redis error): {e}")

        # Extract user information from token payload
        # Look for user ID in multiple fields for compatibility
        user_id_str: Optional[str] = (
            payload.get("sub") or payload.get("user_id") or payload.get("id")
        )

        # Validate required fields are present
        if not user_id_str:
            logger.warning("Token missing user ID field (checked sub, user_id, and id)")
            return None

        # Convert string to UUID
        try:
            user_id = uuid.UUID(user_id_str)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid UUID format for user_id: {user_id_str}, error: {e}", exc_info=True)
            return None

        # Fetch current user information from database using SQLAlchemy
        result = await db.execute(select(User).where(User.id == user_id))
        user: Optional[User] = result.scalar_one_or_none()

        if not user:
            logger.warning(f"User not found in database: {user_id}")
            return None

        # Return comprehensive user information
        return {
            "id": str(user.id),
            "_id": str(user.id),  # For backward compatibility
            "email": user.email,
            "auth_method": user.auth_method,
            "full_name": user.full_name,
            "is_admin": user.is_admin,
            "profile_completed": user.profile_completed,
            "profile_completion_percentage": user.profile_completion_percentage,
            "has_google_linked": user.google_id is not None,
            "has_password": user.password_hash is not None,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "last_login": user.last_login,
        }

    except jwt.ExpiredSignatureError:
        logger.warning("Token validation failed: Token has expired")
        raise
    except jwt.InvalidTokenError:
        logger.warning("Token validation failed: Invalid token")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during token validation: {e}", exc_info=True)
        return None
