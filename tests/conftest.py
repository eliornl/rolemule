"""
Pytest configuration and fixtures for the RoleMule tests.

Uses local PostgreSQL and Redis for testing to match production environment.
"""

import uuid
import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Dict, Any

import jwt
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import delete

# Load environment variables before importing app modules
from dotenv import load_dotenv
load_dotenv()

from main import app
from models.database import User, AuthMethod
from utils.database import get_database
from config.settings import get_settings, get_security_settings


# =============================================================================
# TEST DATABASE SETUP
# =============================================================================

# Get the database URL from environment
settings = get_settings()
TEST_DATABASE_URL = settings.database_url

# Create a separate engine for tests
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

TestingSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


# Store test user IDs for cleanup
_test_user_ids = set()


async def get_test_database() -> AsyncGenerator[AsyncSession, None]:
    """Override database dependency for testing."""
    async with TestingSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# Override the database dependency
app.dependency_overrides[get_database] = get_test_database


# =============================================================================
# FIXTURES
# =============================================================================

@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for tests."""
    async with TestingSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Alias for client fixture - provides an async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def test_user_data() -> Dict[str, Any]:
    """Return test user data with unique email to avoid conflicts."""
    unique_id = uuid.uuid4().hex[:8]
    user_id = uuid.uuid4()
    _test_user_ids.add(user_id)
    return {
        "id": user_id,
        "email": f"testuser_{unique_id}@example.com",
        "full_name": "Test User",
        "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.O4O4O4O4O4O4O4",  # bcrypt hash
        "auth_method": AuthMethod.LOCAL.value,
        "profile_completed": False,
        "profile_completion_percentage": 0,
    }


@pytest.fixture
def google_user_data() -> Dict[str, Any]:
    """Return Google OAuth user data with unique email."""
    unique_id = uuid.uuid4().hex[:8]
    user_id = uuid.uuid4()
    _test_user_ids.add(user_id)
    return {
        "id": user_id,
        "email": f"googleuser_{unique_id}@gmail.com",
        "full_name": "Google User",
        "password_hash": None,
        "auth_method": AuthMethod.GOOGLE.value,
        "google_id": f"google_{unique_id}",
        "profile_completed": False,
        "profile_completion_percentage": 0,
    }


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, test_user_data: Dict[str, Any]) -> User:
    """Create a test user in the database."""
    user = User(**test_user_data)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    yield user
    
    # Cleanup: Delete the test user
    try:
        await db_session.execute(delete(User).where(User.id == user.id))
        await db_session.commit()
    except Exception:
        await db_session.rollback()


@pytest_asyncio.fixture
async def google_user(db_session: AsyncSession, google_user_data: Dict[str, Any]) -> User:
    """Create a Google OAuth test user in the database."""
    user = User(**google_user_data)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    yield user
    
    # Cleanup: Delete the test user
    try:
        await db_session.execute(delete(User).where(User.id == user.id))
        await db_session.commit()
    except Exception:
        await db_session.rollback()


@pytest.fixture
def auth_token(test_user_data: Dict[str, Any]) -> str:
    """Generate a valid JWT token for testing."""
    security_settings = get_security_settings()
    token_data = {
        "sub": str(test_user_data["id"]),
        "email": test_user_data["email"],
        "auth_method": test_user_data["auth_method"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return jwt.encode(
        token_data,
        security_settings.jwt_config["secret_key"],
        algorithm=security_settings.jwt_config["algorithm"],
    )


@pytest.fixture
def google_auth_token(google_user_data: Dict[str, Any]) -> str:
    """Generate a valid JWT token for Google OAuth user."""
    security_settings = get_security_settings()
    token_data = {
        "sub": str(google_user_data["id"]),
        "email": google_user_data["email"],
        "auth_method": google_user_data["auth_method"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return jwt.encode(
        token_data,
        security_settings.jwt_config["secret_key"],
        algorithm=security_settings.jwt_config["algorithm"],
    )


@pytest.fixture
def mock_google_oauth_response() -> Dict[str, Any]:
    """Return mock Google OAuth token response."""
    return {
        "access_token": "mock_google_access_token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": "mock_refresh_token",
        "scope": "openid email profile",
    }


@pytest.fixture
def mock_google_userinfo() -> Dict[str, Any]:
    """Return mock Google userinfo response."""
    unique_id = uuid.uuid4().hex[:8]
    return {
        "id": f"google_{unique_id}",
        "email": f"newgoogleuser_{unique_id}@gmail.com",
        "verified_email": True,
        "name": "New Google User",
        "given_name": "New",
        "family_name": "User",
        "picture": "https://example.com/photo.jpg",
    }


# Cleanup hook
@pytest.fixture(autouse=True)
def cleanup_test_emails():
    """Clean up test emails after each test."""
    yield
    # Test data uses unique IDs so cleanup happens in fixtures
