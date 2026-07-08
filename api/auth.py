"""
Authentication API endpoints for comprehensive user management.
Provides JWT-based authentication, OAuth integration, and password operations with security validation.
"""

import re
import uuid
import jwt
import logging
import secrets
import httpx
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Union
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Depends, status, Request, Query, Response
from fastapi.security import HTTPBearer
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator, ValidationInfo, EmailStr
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError as _SQLIntegrityError

from config.settings import get_settings, get_security_settings
from models.database import User, AuthMethod
from utils.database import get_database
from utils.cache import (
    check_account_lockout,
    record_failed_login,
    clear_login_attempts,
    check_rate_limit,
    check_rate_limit_with_headers,
    LOCKOUT_THRESHOLD,
    LOCKOUT_DURATION,
)
from utils.auth import get_current_user, extract_token_from_request, revoke_token, invalidate_all_user_tokens
from utils.error_responses import (
    APIError,
    ErrorCode,
    account_locked_error,
    external_service_error,
    internal_error,
    not_found_error,
    rate_limit_error,
    unauthorized_error,
    validation_error,
)
from utils.logging_config import get_structured_logger, mask_email, sanitize_log_value

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

# Password validation constants
MIN_PASSWORD_LENGTH: int = 8
MAX_PASSWORD_LENGTH: int = 128
SPECIAL_CHARACTERS: str = "!@#$%^&*()_+-=[]{}|;:,.<>?"

# Name validation constants
MIN_NAME_LENGTH: int = 2
MAX_NAME_LENGTH: int = 100

# Email validation constants
MAX_EMAIL_LENGTH: int = 254

# Validation patterns
NAME_PATTERN: str = r"^[a-zA-Z\s\-'\.]+$"
EMAIL_PATTERN: str = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

# Token and session constants
SECONDS_PER_HOUR: int = 3600
REMEMBER_ME_DURATION_HOURS: int = 24 * 7  # 1 week
AUTH_TOKEN_TYPE: str = "bearer"

# HTTP response constants
SUCCESS_MESSAGE_LOGOUT: str = "Logged out successfully"
SUCCESS_MESSAGE_PASSWORD_CHANGE: str = "Password changed successfully"

# Google OAuth constants
GOOGLE_AUTH_URL: str = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL: str = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL: str = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_OAUTH_SCOPES: str = "openid email profile"

# =============================================================================
# SHARED VALIDATION METHODS
# =============================================================================


def _validate_email(email: str, field_name: str = "Email") -> str:
    """
    Validate and normalize email address format.

    Ensures email address is properly formatted, within length limits,
    and normalized to lowercase for consistent storage and comparison.

    Args:
        email: Email address string to validate
        field_name: Name of the field being validated (for error messages)

    Returns:
        Cleaned and validated email address string

    Raises:
        ValueError: If email format is invalid or exceeds length limits
    """
    if not email:
        raise ValueError(f"{field_name} cannot be empty")

    email = email.strip().lower()

    # Check length limits
    if len(email) > MAX_EMAIL_LENGTH:
        raise ValueError(f"{field_name} cannot exceed {MAX_EMAIL_LENGTH} characters")

    # Validate email format
    if not re.match(EMAIL_PATTERN, email):
        raise ValueError("Invalid email format")

    return email


def _validate_password_strength(password: str, field_name: str = "Password") -> str:
    """
    Validate password strength requirements.

    Ensures password meets security requirements including length, character variety,
    and complexity standards to protect against common attacks.

    Args:
        password: Password string to validate
        field_name: Name of the field being validated (for error messages)

    Returns:
        Validated password string

    Raises:
        ValueError: If password doesn't meet strength requirements
    """
    if not password:
        raise ValueError(f"{field_name} cannot be empty")

    # Check length limits
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"{field_name} must be at least {MIN_PASSWORD_LENGTH} characters long"
        )

    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"{field_name} cannot exceed {MAX_PASSWORD_LENGTH} characters")

    # Check character variety requirements
    has_upper: bool = any(c.isupper() for c in password)
    has_lower: bool = any(c.islower() for c in password)
    has_digit: bool = any(c.isdigit() for c in password)
    has_special: bool = any(c in SPECIAL_CHARACTERS for c in password)

    missing_requirements: List[str] = []
    if not has_upper:
        missing_requirements.append("uppercase letter")
    if not has_lower:
        missing_requirements.append("lowercase letter")
    if not has_digit:
        missing_requirements.append("digit")
    if not has_special:
        missing_requirements.append("special character")

    if missing_requirements:
        requirements_text = ", ".join(missing_requirements)
        raise ValueError(f"{field_name} must contain at least one: {requirements_text}")

    return password


def _validate_password_confirmation(
    password: str, confirm_password: str, field_name: str = "Password"
) -> str:
    """
    Validate password confirmation matches original password.

    Ensures the password confirmation exactly matches the original password
    for account security and user experience.

    Args:
        password: Original password string
        confirm_password: Password confirmation string to validate
        field_name: Name of the password field being confirmed (for error messages)

    Returns:
        Validated password confirmation string

    Raises:
        ValueError: If passwords don't match
    """
    if not confirm_password:
        raise ValueError(f"{field_name} confirmation cannot be empty")

    if password != confirm_password:
        raise ValueError("Passwords do not match")

    return confirm_password


def _validator_field_values(info_or_values: Union[ValidationInfo, Dict[str, Any], None]) -> Dict[str, Any]:
    """Partial field data from Pydantic ValidationInfo or a raw dict (unit tests)."""
    if info_or_values is None:
        return {}
    if isinstance(info_or_values, dict):
        return info_or_values
    data = getattr(info_or_values, "data", None)
    return data if isinstance(data, dict) else {}


def _validate_register_full_name(v: str) -> str:
    """Validate and clean full name."""
    if not v:
        raise ValueError("Full name cannot be empty")

    name: str = v.strip()

    if len(name) < MIN_NAME_LENGTH:
        raise ValueError(f"Full name must be at least {MIN_NAME_LENGTH} characters")

    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"Full name cannot exceed {MAX_NAME_LENGTH} characters")

    if not re.match(NAME_PATTERN, name):
        raise ValueError(
            "Full name can only contain letters, spaces, hyphens, apostrophes, and periods"
        )

    name = re.sub(r"\s+", " ", name)
    return name.title()


def _validate_login_password(v: str) -> str:
    """Validate password for login authentication."""
    if not v or not v.strip():
        raise ValueError("Password cannot be empty")

    return v.strip()


def _validate_confirm_password_field(
    v: str,
    info_or_values: Union[ValidationInfo, Dict[str, Any], None],
    password_field: str,
    field_name: str = "Password",
) -> str:
    password: str = _validator_field_values(info_or_values).get(password_field, "")
    return _validate_password_confirmation(password, v, field_name)


# =============================================================================
# SETUP AND INITIALIZATION
# =============================================================================

logger: logging.Logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)
router: APIRouter = APIRouter()
security: HTTPBearer = HTTPBearer()

# Configuration instances
settings = get_settings()
security_settings = get_security_settings()
pwd_context: CryptContext = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=security_settings.settings.bcrypt_rounds,
)

# bcrypt 5.x+ raises an error for passwords longer than 72 bytes instead of
# silently truncating (old behavior). Always normalise before hash/verify so
# that existing stored hashes (computed from the first 72 bytes) remain valid.
_BCRYPT_MAX_BYTES: int = 72

# Dummy hash used to perform a constant-time bcrypt comparison when a user is
# not found. This prevents timing-based user enumeration: without it, login
# attempts for non-existent accounts return in ~5 ms while real accounts take
# ~200 ms due to bcrypt work factor.
_DUMMY_HASH: str = pwd_context.hash("dummy-timing-protection-placeholder")


def _bcrypt_safe(password: str) -> str:
    """Return password truncated to 72 UTF-8 bytes, safe for bcrypt."""
    encoded: bytes = password.encode("utf-8")
    if len(encoded) <= _BCRYPT_MAX_BYTES:
        return password
    return encoded[:_BCRYPT_MAX_BYTES].decode("utf-8", errors="ignore")


def _make_jwt(payload: Dict[str, Any], expire_hours: int, token_type: str = "access") -> str:
    """
    Encode a JWT with a unique `jti`, `iat`, and `type` claim.

    Centralises token creation so that every issued token can be individually
    revoked via the Redis blocklist.  All callers in this module must use this
    helper instead of calling `jwt.encode` directly.

    The `type` claim prevents an access token from being used where a different
    token type is expected (e.g., password-reset token vs. access token).

    Args:
        payload: Claims to include (must NOT already contain exp/iat/jti/type).
        expire_hours: Lifetime of the token in hours.
        token_type: Semantic type of the token (e.g. "access", "password_reset").

    Returns:
        Encoded JWT string.
    """
    now = datetime.now(timezone.utc)
    payload = {
        **payload,
        "type": token_type,
        "exp": now + timedelta(hours=expire_hours),
        "iat": now,
        "nbf": now,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(
        payload,
        security_settings.jwt_config["secret_key"],
        algorithm=security_settings.jwt_config["algorithm"],
    )

# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class RegisterRequest(BaseModel):
    """
    User registration request model.

    Validates user input for account creation including name, email, and password
    with confirmation. Enforces password strength requirements and email format validation.
    """

    full_name: str = Field(
        ...,
        min_length=MIN_NAME_LENGTH,
        max_length=MAX_NAME_LENGTH,
        description="User's full name (2-100 characters)",
    )
    email: EmailStr = Field(..., description="Valid email address")
    password: str = Field(
        ...,
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_PASSWORD_LENGTH,
        description=f"Password (minimum {MIN_PASSWORD_LENGTH} characters)",
    )
    confirm_password: str = Field(
        ...,
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_PASSWORD_LENGTH,
        description="Password confirmation - must match password",
    )

    validate_full_name = field_validator("full_name")(_validate_register_full_name)
    validate_email = field_validator("email")(_validate_email)
    validate_password_strength = field_validator("password")(_validate_password_strength)
    passwords_match = field_validator("confirm_password")(
        lambda v, info: _validate_confirm_password_field(v, info, "password")
    )


class LoginRequest(BaseModel):
    """
    User login request model.

    Handles authentication credentials and login preferences including
    remember me functionality for extended session duration.
    """

    email: EmailStr = Field(..., description="Registered email address")
    password: str = Field(..., max_length=MAX_PASSWORD_LENGTH, description="User password")
    remember_me: bool = Field(
        False, description="Extend session duration for convenience (less secure)"
    )

    validate_email = field_validator("email")(_validate_email)
    validate_password = field_validator("password")(_validate_login_password)


class UserInfo(BaseModel):
    """User information model."""

    id: str = Field(..., description="User ID")
    email: str = Field(..., description="User email address")
    full_name: str = Field("", description="User's full name")
    auth_method: str = Field(..., description="Authentication method used")


class AuthResponse(BaseModel):
    """Authentication response model."""

    access_token: str = Field(..., description="JWT access token for API authorization")
    token_type: str = Field(
        default=AUTH_TOKEN_TYPE, description="Token type (always 'bearer')"
    )
    expires_in: int = Field(..., description="Token expiration time in seconds")
    user: Dict[str, Any] = Field(..., description="User profile information")
    profile_completed: bool = Field(
        ..., description="Whether user has completed profile setup"
    )


class UserInfoResponse(BaseModel):
    """User information response model."""

    id: str = Field(..., description="Unique user identifier")
    full_name: str = Field(..., description="User's full name")
    email: str = Field(..., description="User's email address")
    auth_method: str = Field(..., description="Authentication method used (local)")
    profile_completed: bool = Field(..., description="Profile completion status")
    created_at: datetime = Field(..., description="Account creation timestamp")
    updated_at: datetime = Field(..., description="Profile last updated timestamp")
    last_login: Optional[datetime] = Field(None, description="Last login timestamp")


class PasswordChangeRequest(BaseModel):
    """Password change request model."""

    current_password: str = Field(..., description="Current password for verification")
    new_password: str = Field(
        ...,
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_PASSWORD_LENGTH,
        description=f"New password (minimum {MIN_PASSWORD_LENGTH} characters)",
    )
    confirm_password: str = Field(..., description="New password confirmation")

    validate_new_password_strength = field_validator("new_password")(
        lambda v: _validate_password_strength(v, "New password")
    )
    new_passwords_match = field_validator("confirm_password")(
        lambda v, info: _validate_confirm_password_field(v, info, "new_password", "New password")
    )


# =============================================================================
# API ENDPOINTS
# =============================================================================


@router.post("/register", response_model=AuthResponse)
async def register_user(
    request: Request, user_data: RegisterRequest, db: AsyncSession = Depends(get_database)
) -> AuthResponse:
    """
    Register a new user account with email and password.

    Creates a new user account with local authentication, validates input data,
    hashes the password securely, and returns an access token for immediate login.
    """
    try:
        # Rate limit: 10 registration attempts per hour per IP (skipped in TESTING for E2E/CI)
        if not settings.testing:
            client_ip = request.client.host if request.client else "unknown"
            is_allowed, _remaining = await check_rate_limit(
                identifier=f"register:{client_ip}",
                limit=10,
                window_seconds=3600,
            )
            if not is_allowed:
                raise rate_limit_error("Too many registration attempts. Please try again later.", retry_after=3600)

        # Check if user already exists
        result = await db.execute(
            select(User).where(User.email == user_data.email.lower())
        )
        existing_user = result.scalar_one_or_none()

        if existing_user:
            raise validation_error("User with this email already exists")

        # Hash password securely
        password_hash: str = pwd_context.hash(_bcrypt_safe(user_data.password))

        # When email verification is disabled (self-hosted mode), mark the
        # user as verified immediately so they can log in right after registering.
        auto_verified = settings.disable_email_verification
        now = datetime.now(timezone.utc)

        # Create user model
        new_user = User(
            id=uuid.uuid4(),
            email=user_data.email.lower(),
            password_hash=password_hash,
            auth_method=AuthMethod.LOCAL.value,
            full_name=user_data.full_name,
            profile_completed=False,
            profile_completion_percentage=0,
            last_login=now,
            email_verified=auto_verified,
            email_verified_at=now if auto_verified else None,
        )

        if auto_verified:
            logger.info("Email verification disabled (DISABLE_EMAIL_VERIFICATION=true) — auto-verified new user")

        # Insert user into database
        db.add(new_user)
        try:
            await db.commit()
            await db.refresh(new_user)
        except _SQLIntegrityError:
            # Two concurrent requests with the same email both passed the
            # existence check before either committed.  Return the same
            # user-friendly message rather than letting the 500 bubble up.
            await db.rollback()
            raise validation_error("An account with this email already exists.")

        user_id: str = str(new_user.id)

        # Create JWT access token
        access_token: str = _make_jwt(
            {
                "sub": user_id,
                "email": user_data.email.lower(),
                "auth_method": AuthMethod.LOCAL.value,
            },
            expire_hours=security_settings.jwt_config["expire_hours"],
        )

        structured_logger.log_registration(user_data.email, AuthMethod.LOCAL.value)

        # Skip verification email when auto-verified (no SMTP needed)
        if not auto_verified:
            try:
                await _send_verification_email(user_data.email.lower(), user_data.full_name)
            except Exception as email_error:
                logger.warning("Failed to send verification email: %s", sanitize_log_value(str(email_error)))

        return AuthResponse(
            access_token=access_token,
            token_type=AUTH_TOKEN_TYPE,
            expires_in=security_settings.jwt_config["expire_hours"] * SECONDS_PER_HOUR,
            user={
                "id": user_id,
                "email": user_data.email.lower(),
                "full_name": user_data.full_name,
                "auth_method": AuthMethod.LOCAL.value,
                "email_verified": auto_verified,
            },
            profile_completed=False,
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Registration failed: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Registration failed")


@router.post("/login", response_model=AuthResponse)
async def login_user(
    request: Request, user_data: LoginRequest, db: AsyncSession = Depends(get_database)
) -> AuthResponse:
    """
    Authenticate user with email and password.

    Validates user credentials against the database, creates a JWT token,
    and returns access token for API access. Supports remember me functionality.
    Includes account lockout protection after multiple failed attempts.
    """
    try:
        logger.debug("Login attempt for email: %s", mask_email(str(user_data.email)))

        if not user_data.email or not user_data.password:
            raise validation_error("Email and password are required")

        # Rate limit: 20 login attempts per hour per IP (defense-in-depth; account lockout is per-email)
        client_ip = request.client.host if request.client else "unknown"
        is_allowed, _remaining = await check_rate_limit(
            identifier=f"login:{client_ip}",
            limit=20,
            window_seconds=3600,
        )
        if not is_allowed:
            raise rate_limit_error("Too many login attempts. Please try again later.", retry_after=3600)

        # Check for account lockout before processing
        is_locked, remaining_seconds = await check_account_lockout(user_data.email)
        if is_locked:
            structured_logger.log_login_failure(
                user_data.email, "account_locked", attempts_remaining=0
            )
            raise account_locked_error(
                f"Account temporarily locked due to too many failed login attempts. Try again in {remaining_seconds // 60} minutes.",
                retry_after=remaining_seconds,
            )

        # Find user by email
        result = await db.execute(
            select(User).where(User.email == user_data.email.lower())
        )
        user = result.scalar_one_or_none()

        if not user:
            # Perform a dummy bcrypt comparison to equalise response time with
            # the real-user path and prevent timing-based account enumeration.
            pwd_context.verify(_bcrypt_safe(user_data.password), _DUMMY_HASH)
            await record_failed_login(user_data.email)
            structured_logger.log_login_failure(user_data.email, "user_not_found")
            raise APIError(
                ErrorCode.AUTH_INVALID_CREDENTIALS,
                "Invalid email or password",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        # Verify password
        if not pwd_context.verify(_bcrypt_safe(user_data.password), user.password_hash):
            # Record failed login attempt
            attempts, is_now_locked = await record_failed_login(user_data.email)
            remaining = LOCKOUT_THRESHOLD - attempts
            
            if is_now_locked:
                structured_logger.log_account_lockout(user_data.email, LOCKOUT_DURATION)
                raise APIError(
                    ErrorCode.AUTH_ACCOUNT_LOCKED,
                    f"Account locked due to too many failed attempts. Try again in {LOCKOUT_DURATION // 60} minutes.",
                    status_code=status.HTTP_423_LOCKED,
                    headers={"Retry-After": str(LOCKOUT_DURATION)},
                )
            
            structured_logger.log_login_failure(
                user_data.email, "invalid_password", attempts_remaining=remaining
            )

            raise APIError(
                ErrorCode.AUTH_INVALID_CREDENTIALS,
                "Invalid email or password",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        # Clear failed login attempts on successful login
        await clear_login_attempts(user_data.email)
        
        # Check if email is verified (required before full access).
        # Skipped when DISABLE_EMAIL_VERIFICATION=true (self-hosted mode).
        if not user.email_verified and not settings.disable_email_verification:
            # Resend verification code
            try:
                await _send_verification_email(user.email, user.full_name)
                logger.info("Resent verification code during login for: %s", mask_email(str(user.email)))
            except Exception as e:
                logger.warning("Failed to resend verification code: %s", sanitize_log_value(str(e)))

            raise APIError(
                ErrorCode.AUTH_FORBIDDEN,
                "Email not verified. A new verification code has been sent to your email.",
                status_code=status.HTTP_403_FORBIDDEN,
                headers={"X-Verification-Required": "true"},
            )
        
        # Log successful login
        structured_logger.log_login_success(user_data.email, user.auth_method)

        # Update last login time
        user.last_login = datetime.now(timezone.utc)
        await db.commit()

        # Generate JWT token
        expire_hours = (
            security_settings.jwt_config["expire_hours"]
            if not user_data.remember_me
            else security_settings.jwt_config["expire_hours"] * 30
        )

        try:
            access_token = _make_jwt(
                {"sub": str(user.id), "email": user.email},
                expire_hours=expire_hours,
            )
        except Exception as e:
            logger.error("JWT encoding error: %s", sanitize_log_value(str(e)), exc_info=True)
            raise internal_error("Authentication error")

        expires_in = expire_hours * SECONDS_PER_HOUR

        user_info = {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "auth_method": user.auth_method,
            "email_verified": user.email_verified,
        }

        return AuthResponse(
            access_token=access_token,
            token_type=AUTH_TOKEN_TYPE,
            expires_in=expires_in,
            user=user_info,
            profile_completed=user.profile_completed,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Login failed: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("An unexpected error occurred. Please try again later.")


@router.post("/logout")
async def logout_user(request: Request) -> Dict[str, str]:
    """
    Logout user by revoking the current JWT.

    The token is added to a Redis blocklist keyed by its `jti` claim so that
    even if the client retains a copy it will be rejected on next use.

    Args:
        request: FastAPI request used to extract the current token.

    Returns:
        Success message.
    """
    from utils.auth import extract_token_from_request, revoke_token

    token = extract_token_from_request(request)
    if token:
        revoked = await revoke_token(token)
        if not revoked:
            logger.warning("Logout: token could not be added to blocklist (Redis may be down)")

    logger.info("User logout requested")
    return {"message": SUCCESS_MESSAGE_LOGOUT}


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> AuthResponse:
    """
    Refresh JWT token for extended session.

    Generates a new access token and revokes the old one so the previous token
    cannot be reused after a successful refresh.

    Returns:
        AuthResponse with new access token and user info
    """
    try:
        user_id = current_user.get("id") or current_user.get("_id")
        email = current_user.get("email", "")
        
        if not user_id:
            raise unauthorized_error()

        # Rate-limit refresh attempts to 20 per hour per user
        allowed, _remaining = await check_rate_limit(
            identifier=f"{user_id}:token_refresh",
            limit=20,
            window_seconds=3600,
        )
        if not allowed:
            raise rate_limit_error(retry_after=3600)

        # Revoke the incoming token so it cannot be reused after this refresh
        old_token = extract_token_from_request(request)
        if old_token:
            revoked = await revoke_token(old_token)
            if not revoked:
                logger.warning("refresh_token: could not revoke old token (Redis may be down)")

        # Generate new token with fresh expiry
        access_token = _make_jwt(
            {"sub": user_id, "email": email},
            expire_hours=security_settings.jwt_config["expire_hours"],
        )

        expires_in = security_settings.jwt_config["expire_hours"] * SECONDS_PER_HOUR

        structured_logger.log_token_refresh(email)

        return AuthResponse(
            access_token=access_token,
            token_type=AUTH_TOKEN_TYPE,
            expires_in=expires_in,
            user={
                "id": user_id,
                "email": email,
                "full_name": current_user.get("full_name", ""),
                "auth_method": current_user.get("auth_method", AuthMethod.LOCAL.value),
            },
            profile_completed=current_user.get("profile_completed", False),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Token refresh failed: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to refresh token")


@router.get("/verify")
async def verify_token(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Verify if the current token is valid.

    Used by frontend to check authentication status without
    making a full user info request.

    Returns:
        Success status and basic user info
    """
    return {
        "success": True,
        "user_id": current_user.get("id") or current_user.get("_id"),
        "email": current_user.get("email"),
        "profile_completed": current_user.get("profile_completed", False),
    }


@router.get("/extension-status")
async def get_extension_status(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get authentication status for Chrome extension.

    Returns user info and token validity status specifically
    formatted for the Chrome extension popup.

    Returns:
        Success status, user info, and extension-specific metadata
    """
    user_id = current_user.get("id") or current_user.get("_id")
    return {
        "success": True,
        "authenticated": True,
        "user": {
            "id": user_id,
            "email": current_user.get("email"),
            "full_name": current_user.get("full_name", ""),
        },
        "profile_completed": current_user.get("profile_completed", False),
        "can_start_workflow": current_user.get("profile_completed", False),
    }


# =============================================================================
# GOOGLE OAUTH ENDPOINTS
# =============================================================================


@router.get("/oauth/status")
async def get_oauth_status() -> Dict[str, Any]:
    """
    Check if Google OAuth is configured and available.

    Returns:
        Dictionary with OAuth availability status
    """
    return {
        "google_oauth_enabled": settings.is_google_oauth_configured,
    }


@router.get("/google")
async def google_login(
    request: Request,
    redirect_url: Optional[str] = Query(None, description="URL to redirect after login"),
) -> RedirectResponse:
    """
    Initiate Google OAuth login flow.

    Redirects user to Google's OAuth consent screen. After authentication,
    Google will redirect back to /api/v1/auth/google/callback with an authorization code.

    The CSRF `state` token is stored in Redis (TTL 10 min) along with the
    validated redirect destination.  Only relative paths are accepted as
    redirect targets to prevent open-redirect attacks.

    Args:
        request: FastAPI request object for building callback URL
        redirect_url: Optional relative path to redirect after successful login

    Returns:
        RedirectResponse to Google's OAuth consent screen

    Raises:
        HTTPException: 503 if Google OAuth is not configured
    """
    if not settings.is_google_oauth_configured:
        raise external_service_error("Google OAuth is not configured. Please contact the administrator.")

    # Validate redirect_url: only allow relative paths to prevent open redirects
    safe_redirect = "/dashboard"
    if redirect_url:
        # Strip whitespace and ensure it starts with / but not //
        candidate = redirect_url.strip()
        if candidate.startswith("/") and not candidate.startswith("//"):
            safe_redirect = candidate
        else:
            logger.warning(
                "OAuth: ignoring non-relative redirect_url: %s",
                sanitize_log_value(redirect_url),
            )

    # Generate a cryptographically secure state token for CSRF protection
    state = secrets.token_urlsafe(32)

    # Store state → redirect destination in Redis (10-minute TTL)
    state_stored = False
    try:
        from utils.redis_client import get_redis_client
        redis_client = await get_redis_client()
        if redis_client:
            import json as _json
            await redis_client.setex(
                f"oauth_state:{state}",
                600,
                _json.dumps({"redirect": safe_redirect}),
            )
            state_stored = True
    except Exception as e:
        logger.error("Failed to store OAuth state in Redis: %s", sanitize_log_value(str(e)), exc_info=True)

    if not state_stored:
        raise external_service_error("Authentication service temporarily unavailable. Please try again.")

    # Build callback URL and Google authorization URL
    callback_url = str(request.url_for("google_callback"))
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": GOOGLE_OAUTH_SCOPES,
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }

    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    logger.info("Initiating Google OAuth login flow")
    return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="State token for CSRF protection"),
    error: Optional[str] = Query(None, description="Error from Google OAuth"),
    db: AsyncSession = Depends(get_database),
) -> RedirectResponse:
    """
    Handle Google OAuth callback after user authentication.

    This endpoint:
    1. Verifies the CSRF state token against the Redis-stored value
    2. Exchanges the authorization code for an access token
    3. Fetches user info from Google
    4. Creates or links the user account
    5. Issues a short-lived one-time code (30 s) that the frontend exchanges
       for a JWT — the JWT itself is never placed in a redirect URL

    Args:
        request: FastAPI request object
        code: Authorization code from Google
        state: CSRF state token (must match the Redis-stored value)
        error: Error from Google OAuth if present
        db: Database session

    Returns:
        RedirectResponse to frontend with a one-time exchange code
    """
    # Handle OAuth errors from Google
    if error:
        logger.warning("Google OAuth returned an error (details omitted from redirect)")
        return RedirectResponse(
            url="/auth/login?error=oauth_failed",
            status_code=status.HTTP_302_FOUND,
        )

    if not settings.is_google_oauth_configured:
        return RedirectResponse(
            url="/auth/login?error=oauth_not_configured",
            status_code=status.HTTP_302_FOUND,
        )

    # ── CSRF state verification ──────────────────────────────────────────────
    try:
        from utils.redis_client import get_redis_client
        import json as _json
        redis_client = await get_redis_client()
        if not redis_client:
            logger.error("OAuth callback: Redis unavailable for state verification")
            return RedirectResponse(
                url="/auth/login?error=service_unavailable",
                status_code=status.HTTP_302_FOUND,
            )

        state_key = f"oauth_state:{state}"
        # Atomically read-and-delete the state token to prevent replay attacks.
        # Using GETDEL prevents a race condition where two concurrent requests
        # could both read the state before either deletes it.
        stored_raw = await redis_client.getdel(state_key)
        if not stored_raw:
            logger.warning("OAuth callback: state token not found or expired (possible CSRF)")
            return RedirectResponse(
                url="/auth/login?error=invalid_state",
                status_code=status.HTTP_302_FOUND,
            )

        stored_data = _json.loads(stored_raw)
        redirect_after_login = stored_data.get("redirect", "/dashboard")
        _link_user_id: Optional[str] = stored_data.get("link_user_id")

        # Defensive re-validation: reject anything that isn't a relative path
        if not redirect_after_login.startswith("/") or redirect_after_login.startswith("//"):
            redirect_after_login = "/dashboard"

    except Exception as e:
        logger.error("OAuth state verification failed: %s", sanitize_log_value(str(e)), exc_info=True)
        return RedirectResponse(
            url="/auth/login?error=service_unavailable",
            status_code=status.HTTP_302_FOUND,
        )

    try:
        # Exchange authorization code for tokens
        callback_url = str(request.url_for("google_callback"))

        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": callback_url,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if token_response.status_code != 200:
            logger.error('Google token exchange failed: %s', sanitize_log_value(token_response.status_code))
            return RedirectResponse(
                url="/auth/login?error=token_exchange_failed",
                status_code=status.HTTP_302_FOUND,
            )

        token_data = token_response.json()
        google_access_token = token_data.get("access_token")

        if not google_access_token:
            logger.error("No access token in Google response")
            return RedirectResponse(
                url="/auth/login?error=no_access_token",
                status_code=status.HTTP_302_FOUND,
            )

        # Fetch user info from Google
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            userinfo_response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {google_access_token}"},
            )

        if userinfo_response.status_code != 200:
            logger.error('Google userinfo fetch failed: %s', sanitize_log_value(userinfo_response.status_code))
            return RedirectResponse(
                url="/auth/login?error=userinfo_failed",
                status_code=status.HTTP_302_FOUND,
            )

        google_user = userinfo_response.json()
        google_id = google_user.get("id")
        email = google_user.get("email", "").lower()
        full_name = google_user.get("name", "")

        if not google_id or not email:
            logger.error("Missing required fields from Google userinfo")
            return RedirectResponse(
                url="/auth/login?error=missing_user_info",
                status_code=status.HTTP_302_FOUND,
            )

        # ── Account-linking path ────────────────────────────────────────────────
        # When the state contains "link_user_id", this is a linking flow initiated
        # by an authenticated user.  Link the Google account to that specific user
        # instead of performing a normal login.
        if _link_user_id:
            # Look up the user who initiated the link
            link_result = await db.execute(
                select(User).where(User.id == uuid.UUID(_link_user_id))
            )
            link_user = link_result.scalar_one_or_none()
            if not link_user:
                return RedirectResponse(
                    url="/auth/login?error=link_user_not_found",
                    status_code=status.HTTP_302_FOUND,
                )
            # Reject if this google_id already belongs to a DIFFERENT user
            conflict_result = await db.execute(
                select(User).where(User.google_id == google_id)
            )
            conflict_user = conflict_result.scalar_one_or_none()
            if conflict_user and str(conflict_user.id) != _link_user_id:
                logger.warning(
                    "Google account link rejected: google_id already linked to another user"
                )
                return RedirectResponse(
                    url="/dashboard/settings?error=google_already_linked_to_other",
                    status_code=status.HTTP_302_FOUND,
                )
            # Perform the link
            link_user.google_id = google_id
            if link_user.auth_method == AuthMethod.LOCAL.value:
                link_user.auth_method = AuthMethod.GOOGLE.value
            await db.commit()
            # Issue exchange code for the SAME authenticated user
            jwt_token = _make_jwt(
                {
                    "sub": str(link_user.id),
                    "email": link_user.email,
                    "auth_method": link_user.auth_method,
                },
                expire_hours=security_settings.jwt_config["expire_hours"],
            )
            exchange_code = secrets.token_urlsafe(32)
            try:
                from utils.redis_client import get_redis_client as _get_rc2
                rc2 = await _get_rc2()
                if rc2:
                    await rc2.setex(f"oauth_code:{exchange_code}", 30, jwt_token)
                else:
                    return RedirectResponse(
                        url="/auth/login?error=service_unavailable",
                        status_code=status.HTTP_302_FOUND,
                    )
            except Exception as link_exc:
                logger.error("Failed to store link exchange code: %s", sanitize_log_value(str(link_exc)), exc_info=True)
                return RedirectResponse(
                    url="/auth/login?error=service_unavailable",
                    status_code=status.HTTP_302_FOUND,
                )
            return RedirectResponse(
                url=f"{redirect_after_login}?code={exchange_code}",
                status_code=status.HTTP_302_FOUND,
            )

        # ── Normal login path ───────────────────────────────────────────────────
        # First, look up by google_id (definitive match — the account was previously linked)
        result = await db.execute(select(User).where(User.google_id == google_id))
        user = result.scalar_one_or_none()

        if user is None:
            # No google_id match — check for an existing local account with the same email
            result = await db.execute(select(User).where(User.email == email))
            email_user = result.scalar_one_or_none()

            if email_user is not None and email_user.google_id is None:
                # A local-auth account exists with this Google email but was never
                # explicitly linked.  Auto-linking would let anyone with a Google
                # account that shares the email take over the local account.
                # Redirect to a dedicated link-accounts flow instead.
                logger.warning('OAuth sign-in for %s blocked: email matches a local-auth account that has not linked Google. Redirect to account-link page.', mask_email(email))
                return RedirectResponse(
                    url="/auth/login?error=google_link_required",
                    status_code=status.HTTP_302_FOUND,
                )

        if user:
            # Enforce the same account lockout rules as email/password login
            _oauth_locked, _oauth_remaining = await check_account_lockout(email)
            if _oauth_locked:
                logger.warning("OAuth login blocked for locked account: %s", mask_email(email))
                return RedirectResponse(
                    url="/auth/login?error=account_locked",
                    status_code=status.HTTP_302_FOUND,
                )

            user.last_login = datetime.now(timezone.utc)
            await db.commit()
            structured_logger.log_oauth_login(email, "google", is_new_user=False)
        else:
            user = User(
                id=uuid.uuid4(),
                email=email,
                password_hash=None,
                auth_method=AuthMethod.GOOGLE.value,
                full_name=full_name,
                google_id=google_id,
                profile_completed=False,
                profile_completion_percentage=0,
                last_login=datetime.now(timezone.utc),
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            structured_logger.log_oauth_login(email, "google", is_new_user=True)
            redirect_after_login = "/profile/setup"

            # Send welcome email — no verification step for Google users, so send it now
            try:
                from utils.email_service import get_email_service
                _email_service = get_email_service()
                if _email_service.is_configured():
                    await _email_service.send_welcome_email(
                        to_email=email,
                        user_name=full_name,
                    )
                    logger.info("Welcome email sent to new Google user: %s", mask_email(email))
            except Exception as _welcome_err:
                logger.warning("Failed to send welcome email for Google user: %s", sanitize_log_value(str(_welcome_err)))

        # Override redirect if profile is not complete
        if not user.profile_completed:
            redirect_after_login = "/profile/setup"

        # ── Issue a one-time exchange code (JWT never goes in the URL) ────────
        jwt_token = _make_jwt(
            {"sub": str(user.id), "email": user.email, "auth_method": user.auth_method},
            expire_hours=security_settings.jwt_config["expire_hours"],
        )

        exchange_code = secrets.token_urlsafe(32)
        try:
            from utils.redis_client import get_redis_client as _get_rc
            rc = await _get_rc()
            if rc:
                await rc.setex(f"oauth_code:{exchange_code}", 30, jwt_token)
            else:
                logger.error("Redis unavailable: cannot store OAuth exchange code")
                return RedirectResponse(
                    url="/auth/login?error=service_unavailable",
                    status_code=status.HTTP_302_FOUND,
                )
        except Exception as e:
            logger.error("Failed to store OAuth exchange code: %s", sanitize_log_value(str(e)), exc_info=True)
            return RedirectResponse(
                url="/auth/login?error=service_unavailable",
                status_code=status.HTTP_302_FOUND,
            )

        redirect_url = f"{redirect_after_login}?code={exchange_code}"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)

    except Exception:
        logger.error("Google OAuth callback error (details omitted from redirect)")
        await db.rollback()
        return RedirectResponse(
            url="/auth/login?error=oauth_error",
            status_code=status.HTTP_302_FOUND,
        )


# =============================================================================
# OAUTH EXCHANGE CODE ENDPOINT
# =============================================================================


class ExchangeCodeRequest(BaseModel):
    """Request body for the one-time OAuth code exchange."""

    code: str = Field(..., max_length=128, description="One-time code received in the OAuth redirect")


@router.post("/oauth/exchange-code")
async def exchange_oauth_code(
    request_data: ExchangeCodeRequest,
) -> Dict[str, Any]:
    """
    Exchange a short-lived OAuth one-time code for a JWT.

    After Google OAuth completes, the callback redirects the browser to the
    frontend with a `?code=` parameter instead of the JWT itself.  The
    frontend must immediately POST this code here to receive its JWT.  Codes
    are stored in Redis with a 30-second TTL and are deleted on first use.

    Args:
        request_data: The one-time code from the OAuth redirect URL.

    Returns:
        JWT access token and basic user metadata.

    Raises:
        HTTPException: 400 if the code is invalid or expired.
    """
    try:
        from utils.redis_client import get_redis_client
        redis_client = await get_redis_client()
        if not redis_client:
            raise external_service_error("Authentication service temporarily unavailable.")

        code_key = f"oauth_code:{request_data.code}"
        # Atomic read-and-delete prevents a race condition where two concurrent
        # requests could both pass the existence check before either deletes it.
        jwt_token = await redis_client.getdel(code_key)
        if not jwt_token:
            raise validation_error("Invalid or expired exchange code.")

        return {
            "access_token": jwt_token,
            "token_type": AUTH_TOKEN_TYPE,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("OAuth code exchange failed: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to exchange code.")


@router.post("/google/link")
async def link_google_account(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> Dict[str, Any]:
    """
    Get the URL to link a Google account to an existing user.

    Generates a dedicated OAuth state that embeds the authenticated user's ID
    so the callback knows to LINK the Google account to this user rather than
    performing a regular login.  Without this, the callback cannot distinguish
    a link flow from a login flow.

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        Dictionary with the OAuth URL for account linking
    """
    if not settings.is_google_oauth_configured:
        raise external_service_error("Google OAuth is not configured")

    user_id = current_user.get("id")

    # Rate limit: 10 link attempts per hour per user
    is_allowed, _remaining = await check_rate_limit(
        identifier=f"{user_id}:google_link",
        limit=10,
        window_seconds=3600,
    )
    if not is_allowed:
        raise rate_limit_error("Too many account linking attempts. Please try again later.", retry_after=3600)

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise not_found_error("User")

    if user.google_id:
        raise validation_error("Google account is already linked")

    # Generate a linking-specific state that carries the authenticated user ID.
    # The callback will look for "link_user_id" in the state data and run the
    # account-linking path instead of the normal login path.
    link_state = secrets.token_urlsafe(32)
    try:
        from utils.redis_client import get_redis_client as _get_rc
        import json as _json
        rc = await _get_rc()
        if not rc:
            raise external_service_error("Authentication service temporarily unavailable")
        await rc.setex(
            f"oauth_state:{link_state}",
            600,  # 10-minute TTL
            _json.dumps({"redirect": "/dashboard/settings", "link_user_id": str(user_id)}),
        )
    except APIError:
        raise
    except Exception as e:
        logger.error("Failed to store link OAuth state: %s", sanitize_log_value(str(e)), exc_info=True)
        raise external_service_error("Authentication service temporarily unavailable")

    callback_url = str(request.url_for("google_callback"))
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": GOOGLE_OAUTH_SCOPES,
        "state": link_state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    oauth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    return {
        "message": "Redirect the user to the oauth_url to complete Google account linking",
        "oauth_url": oauth_url,
    }


@router.delete("/google/unlink")
async def unlink_google_account(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> Dict[str, Any]:
    """
    Unlink Google account from user.

    Removes the Google OAuth connection from the user's account.
    User must have a password set if they want to unlink Google
    (to ensure they can still log in).

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message

    Raises:
        HTTPException: If user has no password and tries to unlink Google
    """
    user_id = current_user.get("id")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise not_found_error("User not found")

    if not user.google_id:
        raise validation_error("No Google account is linked")

    # Ensure user has a password if they're unlinking Google
    if not user.password_hash:
        raise validation_error("Cannot unlink Google account without a password. Please set a password first.")

    # Unlink Google account
    user.google_id = None
    if user.auth_method == AuthMethod.GOOGLE.value:
        user.auth_method = AuthMethod.LOCAL.value
    
    await db.commit()
    
    logger.info("Unlinked Google account for user: %s", mask_email(str(user.email)))
    
    return {"message": "Google account unlinked successfully"}


# =============================================================================
# PASSWORD RESET ENDPOINTS
# =============================================================================


class ForgotPasswordRequest(BaseModel):
    """Request model for forgot password."""

    email: EmailStr = Field(..., description="Email address for password reset")

    validate_email = field_validator("email")(_validate_email)


class ResetPasswordRequest(BaseModel):
    """Request model for password reset."""

    token: str = Field(..., max_length=128, description="Password reset token from email")
    new_password: str = Field(
        ...,
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_PASSWORD_LENGTH,
        description=f"New password (minimum {MIN_PASSWORD_LENGTH} characters)",
    )
    confirm_password: str = Field(..., description="Password confirmation")

    validate_new_password_strength = field_validator("new_password")(
        lambda v: _validate_password_strength(v, "New password")
    )
    passwords_match = field_validator("confirm_password")(
        lambda v, info: _validate_confirm_password_field(v, info, "new_password", "New password")
    )


# Password reset token settings
RESET_TOKEN_EXPIRY_SECONDS = 3600  # 1 hour
RESET_TOKEN_PREFIX = "password_reset:"


async def _store_reset_token(email: str, token: str) -> bool:
    """Store password reset token in Redis."""
    try:
        from utils.redis_client import get_redis_client
        redis_client = await get_redis_client()
        if redis_client:
            key = f"{RESET_TOKEN_PREFIX}{token}"
            await redis_client.setex(key, RESET_TOKEN_EXPIRY_SECONDS, email)
            return True
        return False
    except Exception as e:
        logger.error("Failed to store reset token: %s", sanitize_log_value(str(e)), exc_info=True)
        return False


async def _consume_reset_token(token: str) -> Optional[str]:
    """Atomically consume (read and delete) a password reset token.

    Uses Redis GETDEL so the token is deleted in the same operation that reads
    it, preventing a race condition where two concurrent requests both validate
    the same token before either deletes it.

    Returns the associated email on success, or None if the token is invalid/expired.
    """
    try:
        from utils.redis_client import get_redis_client
        redis_client = await get_redis_client()
        if redis_client:
            key = f"{RESET_TOKEN_PREFIX}{token}"
            email = await redis_client.getdel(key)
            return email
        return None
    except Exception as e:
        logger.error("Failed to consume reset token: %s", sanitize_log_value(str(e)), exc_info=True)
        return None


# Keep backward-compatible aliases pointing to the atomic versions.
async def _verify_reset_token(token: str) -> Optional[str]:
    return await _consume_reset_token(token)


async def _delete_reset_token(token: str) -> None:
    """No-op: token is already deleted by _consume_reset_token."""
    return None


@router.post("/forgot-password")
async def forgot_password(
    request_data: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_database),
) -> Dict[str, str]:
    """
    Request a password reset email.

    Sends an email with a password reset link if the email exists.
    For security, always returns success even if email doesn't exist
    (to prevent email enumeration attacks).

    Args:
        request_data: Email address for password reset
        request: FastAPI request for building reset URL
        db: Database session

    Returns:
        Success message (always, for security)
    """
    try:
        email = request_data.email.lower()

        # Rate limit: 5 requests per hour per email to prevent abuse
        is_allowed, _remaining = await check_rate_limit(
            identifier=f"forgot_password:{email}",
            limit=5,
            window_seconds=3600,
        )
        if not is_allowed:
            raise rate_limit_error("Too many password reset requests. Please wait before trying again.", retry_after=3600)

        # Check if user exists
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        _generic_reset_response = {
            "message": "If an account exists with this email address, you will receive a password reset link shortly."
        }

        if not user:
            logger.info("Password reset requested for non-existent email: %s", mask_email(email))
            return _generic_reset_response

        # Check if user has a password (Google OAuth users without password)
        if not user.password_hash and user.auth_method == AuthMethod.GOOGLE.value:
            logger.info("Password reset requested for Google OAuth user without password: %s", mask_email(email))
            return _generic_reset_response

        # Generate secure reset token
        reset_token = secrets.token_urlsafe(32)

        # Store token in Redis
        token_stored = await _store_reset_token(email, reset_token)
        if not token_stored:
            logger.error("Failed to store password reset token for: %s", mask_email(email))
            return {
                "message": "Something went wrong. Please try again later.",
                "email_sent": "false"
            }

        # Build reset URL
        base_url = settings.base_url.rstrip("/")
        reset_url = f"{base_url}/auth/reset-password?token={reset_token}"

        # Send email
        try:
            from utils.email_service import get_email_service
            email_service = get_email_service()
            
            if email_service.is_configured():
                email_sent = await email_service.send_password_reset_email(
                    to_email=email,
                    reset_token=reset_token,
                    reset_url=reset_url,
                    user_name=user.full_name,
                )
                if email_sent:
                    structured_logger.log_password_reset_request(email)
                else:
                    logger.warning("Failed to send password reset email to: %s", mask_email(email))
            else:
                # No SMTP configured — surface the reset URL directly so self-hosted
                # users are not permanently locked out without an email service.
                logger.warning('Email service not configured. Returning reset URL directly for %s (self-hosted mode).', mask_email(email))
                return {
                    "message": (
                        "Email is not configured on this server. "
                        "Use the link below to reset your password."
                    ),
                    "reset_url": reset_url,
                }
        except Exception as email_error:
            logger.error("Error sending password reset email: %s", sanitize_log_value(str(email_error)), exc_info=True)

        # Always return the same generic message to prevent email enumeration
        return _generic_reset_response

    except Exception as e:
        logger.error("Password reset request failed: %s", sanitize_log_value(str(e)), exc_info=True)
        return {
            "message": "If an account exists with this email address, you will receive a password reset link shortly."
        }


@router.post("/reset-password")
async def reset_password(
    request: Request,
    request_data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_database),
) -> Dict[str, str]:
    """
    Reset password using token from email.

    Validates the reset token and updates the user's password.

    Args:
        request: FastAPI request (used for rate limiting)
        request_data: Reset token and new password
        db: Database session

    Returns:
        Success message

    Raises:
        HTTPException: 400 if token is invalid/expired, 500 on error
    """
    try:
        # Rate limit: 10 attempts per hour per IP to prevent token brute-force
        client_ip = request.client.host if request.client else "unknown"
        is_allowed, _remaining = await check_rate_limit(
            identifier=f"reset_password:{client_ip}",
            limit=10,
            window_seconds=3600,
        )
        if not is_allowed:
            raise rate_limit_error("Too many password reset attempts. Please wait before trying again.", retry_after=3600)

        # Verify token (atomic GETDEL — also consumes it so it cannot be replayed)
        email = await _verify_reset_token(request_data.token)
        
        if not email:
            raise validation_error("Invalid or expired reset token. Please request a new password reset.")

        # Honour account lockout — an attacker who obtained a reset token for a
        # locked account should not be able to bypass the lockout.
        _reset_locked, _reset_remaining = await check_account_lockout(email)
        if _reset_locked:
            raise account_locked_error(retry_after=_reset_remaining)

        # Find user
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            raise validation_error("Invalid or expired reset token. Please request a new password reset.")

        # Hash new password
        new_password_hash = pwd_context.hash(_bcrypt_safe(request_data.new_password))

        # Capture before assignment — once we set password_hash the old value is gone
        had_password = user.password_hash is not None

        # Update password
        user.password_hash = new_password_hash
        user.updated_at = datetime.now(timezone.utc)

        # If this is the first password for a non-OAuth user, mark auth method as LOCAL
        if not had_password and user.auth_method != AuthMethod.GOOGLE.value:
            user.auth_method = AuthMethod.LOCAL.value

        await db.commit()

        # Delete used token (must be single-use)
        await _delete_reset_token(request_data.token)

        # Invalidate all existing sessions — attacker who had the old password
        # should not retain an active session after the reset.
        try:
            await invalidate_all_user_tokens(str(user.id))
        except Exception as revoke_err:
            logger.warning("Failed to invalidate sessions after password reset: %s", sanitize_log_value(str(revoke_err)))

        structured_logger.log_password_reset_complete(email)

        return {"message": "Password reset successfully. You can now log in with your new password."}

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Password reset failed: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to reset password. Please try again.")


@router.put("/change-password")
async def change_password(
    request_data: PasswordChangeRequest,
    response: Response,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> Dict[str, str]:
    """
    Change password for authenticated user.

    Requires current password verification before setting new password.

    Args:
        request_data: Current password and new password
        response: FastAPI response (for rate-limit headers)
        current_user: Authenticated user
        db: Database session

    Returns:
        Success message

    Raises:
        HTTPException: 400 if current password is wrong, 500 on error
    """
    try:
        user_id = current_user.get("id")

        rate_result = await check_rate_limit_with_headers(
            identifier=f"{user_id}:change_password",
            limit=5,
            window_seconds=3600,
        )
        response.headers["X-RateLimit-Limit"] = str(rate_result.limit)
        response.headers["X-RateLimit-Remaining"] = str(rate_result.remaining)
        response.headers["X-RateLimit-Reset"] = str(rate_result.reset_seconds)
        if not rate_result.allowed:
            raise rate_limit_error("Rate limit exceeded. Maximum 5 password changes per hour.")
        
        result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
        user = result.scalar_one_or_none()

        if not user:
            raise not_found_error("User not found")

        # Verify current password
        if not user.password_hash:
            raise validation_error("No password set for this account. Please use 'Forgot Password' to set one.")

        if not pwd_context.verify(_bcrypt_safe(request_data.current_password), user.password_hash):
            raise validation_error("Current password is incorrect")

        # Check that new password is different
        if pwd_context.verify(_bcrypt_safe(request_data.new_password), user.password_hash):
            raise validation_error("New password must be different from current password")

        # Hash and set new password
        user.password_hash = pwd_context.hash(_bcrypt_safe(request_data.new_password))
        user.updated_at = datetime.now(timezone.utc)

        await db.commit()

        # Invalidate all existing tokens so stolen tokens cannot be reused after password change
        await invalidate_all_user_tokens(str(user.id))

        # Issue a fresh token so the current session stays alive
        new_token = _make_jwt(
            {"sub": str(user.id), "email": user.email},
            expire_hours=security_settings.jwt_config["expire_hours"],
        )

        structured_logger.log_password_change(user.email)

        return {
            "message": SUCCESS_MESSAGE_PASSWORD_CHANGE,
            "access_token": new_token,
            "token_type": "bearer",
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Password change failed: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to change password. Please try again.")


@router.get("/email-status")
async def get_email_service_status() -> Dict[str, Any]:
    """
    Check if email service is configured.
    
    Useful for frontend to show appropriate UI for password reset.
    """
    try:
        from utils.email_service import get_email_service
        email_service = get_email_service()
        
        return {
            "email_configured": email_service.is_configured(),
            "message": "Email service is configured" if email_service.is_configured() 
                      else "Email service is not configured. Password reset emails cannot be sent.",
        }
    except Exception as e:
        logger.error("Error checking email status: %s", sanitize_log_value(str(e)), exc_info=True)
        return {
            "email_configured": False,
            "message": "Unable to check email service status",
        }


# =============================================================================
# EMAIL VERIFICATION ENDPOINTS
# =============================================================================

# Email verification token settings
VERIFICATION_TOKEN_EXPIRY_SECONDS = 900  # 15 minutes for 6-digit code
VERIFICATION_TOKEN_PREFIX = "email_verification:"
VERIFICATION_USER_PREFIX = "email_verification_user:"


async def _store_verification_token(email: str, token: str) -> bool:
    """Store email verification token in Redis, invalidating any prior active code.

    Two keys are written atomically:
    - ``email_verification:{token}``      → email  (consumed on use via GETDEL)
    - ``email_verification_user:{email}`` → token  (tracks which code is current)

    If a previous code key is found via the user→code mapping it is deleted before
    the new keys are written, ensuring only one code is ever valid at a time.
    """
    try:
        from utils.redis_client import get_redis_client
        redis_client = await get_redis_client()
        if redis_client:
            user_key = f"{VERIFICATION_USER_PREFIX}{email.lower()}"

            # Atomically retrieve (and delete) the previous active code for this email.
            old_code = await redis_client.getdel(user_key)
            if old_code:
                old_token_key = f"{VERIFICATION_TOKEN_PREFIX}{old_code}"
                await redis_client.delete(old_token_key)

            # Write the new code→email mapping and the new email→code mapping.
            token_key = f"{VERIFICATION_TOKEN_PREFIX}{token}"
            pipe = redis_client.pipeline()
            pipe.setex(token_key, VERIFICATION_TOKEN_EXPIRY_SECONDS, email)
            pipe.setex(user_key, VERIFICATION_TOKEN_EXPIRY_SECONDS, token)
            await pipe.execute()
            return True
        return False
    except Exception as e:
        logger.error("Failed to store verification token: %s", sanitize_log_value(str(e)), exc_info=True)
        return False


async def _consume_verification_token(token: str) -> Optional[str]:
    """Atomically consume (read and delete) an email verification token.

    Uses Redis GETDEL so the token is invalidated in the same operation that
    validates it, preventing a race condition where two concurrent requests
    both pass verification before either deletes the token.

    Also removes the email→code tracking key so no stale pointer remains.

    Returns the associated email on success, or None if the token is invalid/expired.
    """
    try:
        from utils.redis_client import get_redis_client
        redis_client = await get_redis_client()
        if redis_client:
            key = f"{VERIFICATION_TOKEN_PREFIX}{token}"
            email = await redis_client.getdel(key)
            if email:
                # Clean up the reverse mapping; ignore errors (key may have already expired).
                try:
                    user_key = f"{VERIFICATION_USER_PREFIX}{email.lower()}"
                    await redis_client.delete(user_key)
                except Exception as cleanup_err:
                    logger.debug('Failed to remove verification user key: %s', sanitize_log_value(cleanup_err))
            return email
        return None
    except Exception as e:
        logger.error("Failed to consume verification token: %s", sanitize_log_value(str(e)), exc_info=True)
        return None


# Backward-compatible aliases pointing to the atomic version.
async def _verify_verification_token(token: str) -> Optional[str]:
    return await _consume_verification_token(token)


async def _delete_verification_token(token: str) -> None:
    """No-op: token already consumed atomically by _consume_verification_token."""
    return None


async def _send_verification_email(email: str, user_name: Optional[str] = None) -> bool:
    """Generate 6-digit code and send verification email."""
    try:
        # Generate a cryptographically secure 6-digit verification code
        verification_code = str(secrets.randbelow(900000) + 100000)

        # Store code in Redis (using the code as the token)
        token_stored = await _store_verification_token(email, verification_code)
        if not token_stored:
            logger.error("Failed to store verification code for: %s", mask_email(email))
            return False

        # Send email with code
        from utils.email_service import get_email_service
        email_service = get_email_service()
        
        if email_service.is_configured():
            email_sent = await email_service.send_verification_code_email(
                to_email=email,
                verification_code=verification_code,
                user_name=user_name,
            )
            if email_sent:
                logger.info("Verification code email sent to: %s", mask_email(email))
                return True
            else:
                logger.warning("Failed to send verification code email to: %s", mask_email(email))
                return False
        else:
            logger.warning("Email service not configured. Verification code generated for %s but not delivered.", mask_email(email))
            if settings.debug:
                logger.debug(
                    "DEBUG: Verification code generated for %s (value redacted)",
                    mask_email(email),
                )
            return False
    except Exception as e:
        logger.error("Error sending verification email: %s", sanitize_log_value(str(e)), exc_info=True)
        return False


class ResendVerificationRequest(BaseModel):
    """Request model for resending verification email."""

    email: EmailStr = Field(..., description="Email address to resend verification to")


class VerifyCodeRequest(BaseModel):
    """Request model for verifying email with code."""

    email: EmailStr = Field(..., description="Email address to verify")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")


@router.post("/verify-code")
async def verify_email_code(
    request: Request,
    request_data: VerifyCodeRequest,
    db: AsyncSession = Depends(get_database),
) -> Dict[str, Any]:
    """
    Verify email address using 6-digit code.

    Args:
        request: FastAPI request (used for rate limiting)
        request_data: Email and verification code
        db: Database session

    Returns:
        Success message and redirect info
    """
    try:
        email = request_data.email.lower()

        # Rate limit: 10 attempts per hour per email to prevent code brute-force
        is_allowed, _remaining = await check_rate_limit(
            identifier=f"verify_code:{email}",
            limit=10,
            window_seconds=3600,
        )
        if not is_allowed:
            raise rate_limit_error("Too many verification attempts. Please wait before trying again.", retry_after=3600)

        code = request_data.code

        # Find user first
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            raise validation_error("Invalid email or verification code.")

        # Respect account lockout (same policy as login — too many failed attempts
        # on related endpoints should not be a bypass route for lockout).
        _verify_locked, _verify_remaining = await check_account_lockout(email)
        if _verify_locked:
            raise account_locked_error(retry_after=_verify_remaining)

        # Check if already verified
        if user.email_verified:
            return {
                "message": "Email already verified.",
                "email_verified": True,
                "redirect": "/dashboard" if user.profile_completed else "/profile/setup",
            }

        # Verify the code
        stored_email = await _verify_verification_token(code)
        
        if not stored_email or stored_email.lower() != email:
            raise validation_error("Invalid or expired verification code. Please request a new one.")

        # Mark email as verified
        user.email_verified = True
        user.email_verified_at = datetime.now(timezone.utc)
        user.updated_at = datetime.now(timezone.utc)

        await db.commit()

        # Delete used code
        await _delete_verification_token(code)

        logger.info("Email verified via code for: %s", mask_email(email))

        # Send welcome email now that email is verified
        try:
            from utils.email_service import get_email_service
            email_service = get_email_service()
            if email_service.is_configured():
                await email_service.send_welcome_email(
                    to_email=email,
                    user_name=user.full_name,
                )
                logger.info("Welcome email sent to: %s", mask_email(email))
        except Exception as email_error:
            logger.warning("Failed to send welcome email after verification: %s", sanitize_log_value(str(email_error)))

        # Determine redirect based on profile completion
        redirect_url = "/dashboard" if user.profile_completed else "/profile/setup"

        # Generate JWT token so user is automatically logged in
        try:
            access_token = _make_jwt(
                {"sub": str(user.id), "email": user.email},
                expire_hours=security_settings.jwt_config["expire_hours"],
            )
        except Exception as e:
            logger.error("JWT encoding error during verification: %s", sanitize_log_value(str(e)), exc_info=True)
            return {
                "message": "Email verified successfully! Please log in to continue.",
                "email_verified": True,
                "redirect": "/auth/login",
            }

        expires_in = security_settings.jwt_config["expire_hours"] * SECONDS_PER_HOUR

        return {
            "message": "Email verified successfully! Welcome to ApplyPilot.",
            "email_verified": True,
            "redirect": redirect_url,
            "access_token": access_token,
            "token_type": AUTH_TOKEN_TYPE,
            "expires_in": expires_in,
            "user": {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "auth_method": user.auth_method,
                "email_verified": True,
            },
            "profile_completed": user.profile_completed,
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Email code verification failed: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to verify email. Please try again.")


@router.get("/verify-email")
async def verify_email(
    token: str = Query(..., description="Email verification token"),
    db: AsyncSession = Depends(get_database),
) -> Dict[str, Any]:
    """
    Verify email address using token from verification email.

    Args:
        token: Verification token from email
        db: Database session

    Returns:
        Success message and redirect info
    """
    try:
        # Verify token
        email = await _verify_verification_token(token)
        
        if not email:
            raise validation_error("Invalid or expired verification token. Please request a new verification email.")

        # Find user
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            raise validation_error("Invalid or expired verification token.")

        # Check if already verified
        if user.email_verified:
            await _delete_verification_token(token)
            return {
                "message": "Email already verified.",
                "email_verified": True,
                "redirect": "/dashboard",
            }

        # Mark email as verified
        user.email_verified = True
        user.email_verified_at = datetime.now(timezone.utc)
        user.updated_at = datetime.now(timezone.utc)

        await db.commit()

        # Delete used token
        await _delete_verification_token(token)

        logger.info("Email verified for: %s", mask_email(email))

        # Send welcome email now that email is verified
        try:
            from utils.email_service import get_email_service
            email_service = get_email_service()
            if email_service.is_configured():
                await email_service.send_welcome_email(
                    to_email=email,
                    user_name=user.full_name,
                )
                logger.info("Welcome email sent to: %s", mask_email(email))
        except Exception as email_error:
            logger.warning("Failed to send welcome email after verification: %s", sanitize_log_value(str(email_error)))
            # Don't fail verification if welcome email fails

        # Check if user has completed profile setup
        profile_completed = user.profile_completed if hasattr(user, 'profile_completed') else False
        redirect_url = "/dashboard" if profile_completed else "/profile/setup"

        return {
            "message": "Email verified successfully! Welcome to ApplyPilot.",
            "email_verified": True,
            "redirect": redirect_url,
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Email verification failed: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to verify email. Please try again.")


@router.post("/resend-verification")
async def resend_verification_email(
    request_data: ResendVerificationRequest,
    db: AsyncSession = Depends(get_database),
) -> Dict[str, str]:
    """
    Resend email verification email.

    For security, always returns success even if email doesn't exist
    (to prevent email enumeration attacks).

    Args:
        request_data: Email address to resend verification to
        db: Database session

    Returns:
        Success message (always, for security)
    """
    try:
        email = request_data.email.lower()

        # Rate limit: 5 resend requests per hour per email
        is_allowed, _remaining = await check_rate_limit(
            identifier=f"resend_verification:{email}",
            limit=5,
            window_seconds=3600,
        )
        if not is_allowed:
            raise rate_limit_error("Too many resend requests. Please wait before trying again.", retry_after=3600)
        
        success_message = {
            "message": "If an account exists with this email and is not yet verified, you will receive a verification email shortly."
        }

        # Check if user exists
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            logger.info("Verification resend requested for non-existent email: %s", mask_email(email))
            return success_message

        # Check if already verified — return the same generic message to prevent
        # leaking whether the account is already verified.
        if user.email_verified:
            logger.info("Verification resend requested for already verified email: %s", mask_email(email))
            return success_message

        # Send verification email
        await _send_verification_email(email, user.full_name)

        return success_message

    except Exception as e:
        logger.error("Resend verification failed: %s", sanitize_log_value(str(e)), exc_info=True)
        return {
            "message": "If an account exists with this email and is not yet verified, you will receive a verification email shortly."
        }


@router.get("/verification-status")
async def get_verification_status(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> Dict[str, Any]:
    """
    Get email verification status for current user.

    Args:
        current_user: Authenticated user
        db: Database session

    Returns:
        Verification status info
    """
    try:
        user_id = current_user.get("id")
        
        result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
        user = result.scalar_one_or_none()

        if not user:
            raise not_found_error("User not found")

        return {
            "email": user.email,
            "email_verified": user.email_verified,
            "email_verified_at": user.email_verified_at.isoformat() if user.email_verified_at else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get verification status: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to get verification status")
