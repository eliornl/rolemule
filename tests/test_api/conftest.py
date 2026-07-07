"""
Shared fixtures for API integration tests.

All tests in tests/test_api/ use the FastAPI TestClient via ASGITransport —
no running server is required.  The key fixtures provided here:

  • api_client          — unauthenticated AsyncClient
  • authed_client       — AsyncClient with mock get_current_user (no real DB user needed)
  • authed_client_with_user — AsyncClient backed by a real User row in the test DB
  • no_rate_limit       — autouse: every rate-limit check always returns "allowed"
  • no_email            — autouse: outbound email is suppressed
  • no_account_lockout  — autouse: account-lockout check always returns not-locked

NullPool note:
  asyncio_default_fixture_loop_scope=session (in pytest.ini) means each test
  function shares the session event loop. asyncpg connections are loop-bound, so the
  shared test_engine pool would try to reuse connections from a closed loop.
  We override get_database here with a NullPool engine to ensure every request
  creates a fresh connection for the current event loop.
"""

import uuid
import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import jwt
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import delete

from main import app
from config.settings import get_security_settings, get_settings
from utils.cache import RateLimitResult
from utils.database import get_database
from models.database import User, AuthMethod


# ---------------------------------------------------------------------------
# NullPool engine — avoids "attached to a different loop" when each test
# function gets its own asyncio event loop.
# ---------------------------------------------------------------------------

_settings = get_settings()

_null_pool_engine = create_async_engine(
    _settings.database_url,
    echo=False,
    poolclass=NullPool,
)

_NullSessionLocal = async_sessionmaker(
    _null_pool_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def _get_null_pool_db() -> AsyncGenerator[AsyncSession, None]:
    async with _NullSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# Override the database dependency to use the NullPool engine for all test_api tests
app.dependency_overrides[get_database] = _get_null_pool_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_test_jwt(user_id: str, email: str, auth_method: str = "local") -> str:
    """Build a signed JWT for integration tests."""
    sec = get_security_settings()
    payload = {
        "sub": user_id,
        "email": email,
        "auth_method": auth_method,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return jwt.encode(payload, sec.jwt_config["secret_key"], algorithm=sec.jwt_config["algorithm"])


# ---------------------------------------------------------------------------
# Base client fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def api_client() -> AsyncGenerator[AsyncClient, None]:
    """Plain (unauthenticated) AsyncClient against the full FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as ac:
        yield ac


@pytest_asyncio.fixture
async def authed_client() -> AsyncGenerator[AsyncClient, None]:
    """
    AsyncClient that bypasses authentication via FastAPI dependency_overrides.
    A random user dict is returned by get_current_user — no real DB row needed.
    Suitable for tests that check auth guards, input validation, and tool output
    but do NOT need the user to exist in the users table.
    """
    from utils.auth import get_current_user, get_current_user_with_complete_profile

    uid = str(uuid.uuid4())
    mock_user = {
        "id": uid,
        "email": f"mock_{uid[:8]}@example.com",
        "full_name": "Mock Test User",
        "auth_method": "local",
        "profile_completed": True,
        "profile_completion_percentage": 100,
    }

    async def _mock_current_user():
        return mock_user

    app.dependency_overrides[get_current_user] = _mock_current_user
    app.dependency_overrides[get_current_user_with_complete_profile] = _mock_current_user

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://localhost",
            headers={"Authorization": f"Bearer {_make_test_jwt(uid, mock_user['email'])}"},
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_with_complete_profile, None)


@pytest_asyncio.fixture
async def authed_client_with_user() -> AsyncGenerator[AsyncClient, None]:
    """
    AsyncClient backed by a real User row in the test database.
    Use this for endpoints that INSERT or SELECT from user-owned rows
    (profile, workflow history, etc.) where FK constraints must be satisfied.
    """
    from utils.auth import get_current_user, get_current_user_with_complete_profile

    uid = uuid.uuid4()
    email = f"realuser_{uid.hex[:8]}@example.com"

    # Create user in DB
    async with _NullSessionLocal() as session:
        user = User(
            id=uid,
            email=email,
            password_hash="$2b$12$placeholder",
            auth_method=AuthMethod.LOCAL.value,
            full_name="Real Test User",
            profile_completed=False,
            profile_completion_percentage=0,
        )
        session.add(user)
        await session.commit()

    now = datetime.now(timezone.utc)
    user_dict = {
        "id": str(uid),
        "_id": str(uid),
        "email": email,
        "full_name": "Real Test User",
        "auth_method": "local",
        "is_admin": False,
        "profile_completed": False,
        "profile_completion_percentage": 0,
        "has_google_linked": False,
        "has_password": True,
        "created_at": now,
        "updated_at": now,
        "last_login": now,
    }

    async def _mock_current_user():
        return user_dict

    app.dependency_overrides[get_current_user] = _mock_current_user
    app.dependency_overrides[get_current_user_with_complete_profile] = _mock_current_user

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://localhost",
            headers={"Authorization": f"Bearer {_make_test_jwt(str(uid), email)}"},
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_with_complete_profile, None)
        # Cleanup: delete the real user
        async with _NullSessionLocal() as session:
            await session.execute(delete(User).where(User.id == uid))
            await session.commit()


# ---------------------------------------------------------------------------
# Autouse: kill rate limiting and email in ALL test_api tests
# ---------------------------------------------------------------------------

_ALLOWED_RATE_LIMIT = RateLimitResult(allowed=True, limit=100, remaining=99, reset_seconds=3600)


@pytest.fixture(autouse=True)
def no_rate_limit():
    """Patch every rate-limit check to always return "allowed"."""
    with patch("utils.cache.check_rate_limit", new_callable=AsyncMock,
               return_value=(True, 99)), \
         patch("utils.cache.check_rate_limit_with_headers", new_callable=AsyncMock,
               return_value=_ALLOWED_RATE_LIMIT), \
         patch("api.auth.check_rate_limit", new_callable=AsyncMock,
               return_value=(True, 99)), \
         patch("api.auth.check_rate_limit_with_headers", new_callable=AsyncMock,
               return_value=_ALLOWED_RATE_LIMIT), \
         patch("api.tools.check_rate_limit_with_headers", new_callable=AsyncMock,
               return_value=_ALLOWED_RATE_LIMIT), \
         patch("api.interview_prep.check_rate_limit", new_callable=AsyncMock,
               return_value=(True, 99)), \
         patch("api.workflow.check_rate_limit", new_callable=AsyncMock,
               return_value=(True, 99)), \
         patch("api.workflow.check_rate_limit_with_headers", new_callable=AsyncMock,
               return_value=_ALLOWED_RATE_LIMIT), \
         patch("api.profile.check_rate_limit", new_callable=AsyncMock,
               return_value=(True, 99)):
        yield


@pytest.fixture(autouse=True)
def no_email():
    """Suppress all outbound email."""
    with patch("api.auth._send_verification_email", new_callable=AsyncMock, return_value=True):
        yield


@pytest.fixture(autouse=True)
def no_account_lockout():
    """Always report account as not locked."""
    with patch("api.auth.check_account_lockout", new_callable=AsyncMock,
               return_value=(False, 0)):
        yield
