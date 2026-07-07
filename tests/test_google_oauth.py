"""
Tests for Google OAuth integration.

These tests run against the actual running server at localhost:8000.
Make sure the server is running before executing these tests.

Tests cover:
- OAuth status endpoint
- Google login redirect endpoint
- Account linking/unlinking endpoints
- AuthMethod enum validation
"""

import uuid
import pytest
import httpx
from typing import Dict


# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_URL = "http://localhost:8000"


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def unique_email():
    """Generate a unique email for testing."""
    return f"test_{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture
def http_client():
    """Create a sync HTTP client for testing."""
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        yield client


@pytest.fixture
def authenticated_user(http_client: httpx.Client, unique_email: str):
    """Create and authenticate a user, returning the token."""
    response = http_client.post(
        "/api/auth/register",
        json={
            "email": unique_email,
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
            "full_name": "Test User",
        },
    )
    data = response.json()
    return {
        "token": data["access_token"],
        "email": unique_email,
    }


# =============================================================================
# AUTH METHOD ENUM TESTS
# =============================================================================


class TestAuthMethodEnum:
    """Tests for AuthMethod enum."""

    def test_google_auth_method_exists(self):
        """Test GOOGLE auth method exists in enum."""
        from models.database import AuthMethod
        assert hasattr(AuthMethod, 'GOOGLE')
        assert AuthMethod.GOOGLE.value == "google"

    def test_local_auth_method_exists(self):
        """Test LOCAL auth method exists in enum."""
        from models.database import AuthMethod
        assert hasattr(AuthMethod, 'LOCAL')
        assert AuthMethod.LOCAL.value == "local"

    def test_all_auth_methods(self):
        """Test all expected auth methods are present."""
        from models.database import AuthMethod
        expected_methods = ['LOCAL', 'GOOGLE']
        for method in expected_methods:
            assert hasattr(AuthMethod, method), f"Missing auth method: {method}"


# =============================================================================
# OAUTH STATUS TESTS
# =============================================================================


class TestOAuthStatus:
    """Tests for the /api/v1/auth/oauth/status endpoint."""

    def test_oauth_status_returns_boolean(self, http_client: httpx.Client):
        """Test that OAuth status returns a boolean for google_oauth_enabled."""
        response = http_client.get("/api/v1/auth/oauth/status")
        
        assert response.status_code == 200
        data = response.json()
        assert "google_oauth_enabled" in data
        assert isinstance(data["google_oauth_enabled"], bool)

    def test_oauth_status_public_access(self, http_client: httpx.Client):
        """Test that OAuth status endpoint is publicly accessible."""
        response = http_client.get("/api/v1/auth/oauth/status")
        assert response.status_code == 200


# =============================================================================
# GOOGLE LOGIN REDIRECT TESTS
# =============================================================================


class TestGoogleLoginRedirect:
    """Tests for the /api/v1/auth/google endpoint."""

    def test_google_login_redirect_behavior(self, http_client: httpx.Client):
        """Test Google login redirect endpoint behavior."""
        from config.settings import get_settings
        settings = get_settings()
        
        response = http_client.get(
            "/api/v1/auth/google",
            follow_redirects=False,
        )
        
        if settings.is_google_oauth_configured:
            # Should redirect to Google OAuth
            assert response.status_code in [302, 307]
        else:
            # Should return error when not configured
            assert response.status_code in [400, 503]


# =============================================================================
# GOOGLE ACCOUNT LINKING TESTS
# =============================================================================


class TestGoogleAccountLinking:
    """Tests for Google account linking/unlinking endpoints."""

    def test_google_link_requires_authentication(self, http_client: httpx.Client):
        """Test that Google account linking requires authentication."""
        response = http_client.post("/api/v1/auth/google/link")
        # API returns 401 or 403 for unauthenticated requests
        assert response.status_code in [401, 403]

    def test_google_unlink_requires_authentication(self, http_client: httpx.Client):
        """Test that Google account unlinking requires authentication."""
        response = http_client.delete("/api/v1/auth/google/unlink")
        # API returns 401 or 403 for unauthenticated requests
        assert response.status_code in [401, 403]

    def test_google_unlink_not_linked(self, http_client: httpx.Client, authenticated_user: Dict):
        """Test unlinking Google when no Google account is linked."""
        from config.settings import get_settings
        settings = get_settings()
        
        if not settings.is_google_oauth_configured:
            pytest.skip("Google OAuth not configured")
        
        response = http_client.delete(
            "/api/v1/auth/google/unlink",
            headers={"Authorization": f"Bearer {authenticated_user['token']}"},
        )
        
        # Should fail because no Google account is linked
        assert response.status_code in [400, 404]


# =============================================================================
# SETTINGS CONFIGURATION TESTS
# =============================================================================


class TestGoogleOAuthSettings:
    """Tests for Google OAuth settings configuration."""

    def test_settings_has_google_client_id_field(self):
        """Test that settings model has google_client_id field."""
        from config.settings import get_settings
        settings = get_settings()
        assert hasattr(settings, 'google_client_id')

    def test_settings_has_google_client_secret_field(self):
        """Test that settings model has google_client_secret field."""
        from config.settings import get_settings
        settings = get_settings()
        assert hasattr(settings, 'google_client_secret')

    def test_settings_has_is_google_oauth_configured_property(self):
        """Test that settings has is_google_oauth_configured property."""
        from config.settings import get_settings
        settings = get_settings()
        assert hasattr(settings, 'is_google_oauth_configured')
        assert isinstance(settings.is_google_oauth_configured, bool)

    def test_oauth_configured_when_both_credentials_set(self):
        """Test is_google_oauth_configured logic."""
        from config.settings import get_settings
        settings = get_settings()
        
        if settings.google_client_id and settings.google_client_secret:
            assert settings.is_google_oauth_configured is True
        else:
            assert settings.is_google_oauth_configured is False


# =============================================================================
# USER MODEL GOOGLE ID TESTS
# =============================================================================


class TestUserModelGoogleId:
    """Tests for User model google_id field."""

    def test_user_model_has_google_id_field(self):
        """Test that User model has google_id field."""
        from models.database import User
        assert hasattr(User, 'google_id')

    def test_user_to_dict_includes_has_google_linked(self):
        """Test that User.to_dict() includes has_google_linked."""
        from models.database import User, AuthMethod
        
        user = User(
            id=uuid.uuid4(),
            email="test@example.com",
            password_hash="$2b$12$test",
            auth_method=AuthMethod.LOCAL,
            full_name="Test User",
            google_id=None,
        )
        
        user_dict = user.to_dict()
        assert "has_google_linked" in user_dict
        assert user_dict["has_google_linked"] is False

    def test_user_to_dict_google_linked_true(self):
        """Test that has_google_linked is True when google_id is set."""
        from models.database import User, AuthMethod
        
        user = User(
            id=uuid.uuid4(),
            email="test@example.com",
            password_hash="$2b$12$test",
            auth_method=AuthMethod.LOCAL,
            full_name="Test User",
            google_id="google_123456",
        )
        
        user_dict = user.to_dict()
        assert user_dict["has_google_linked"] is True


# =============================================================================
# AUTH RESPONSE MODEL TESTS
# =============================================================================


class TestAuthResponseWithOAuth:
    """Tests for auth response including OAuth fields."""

    def test_login_response_includes_basic_fields(self, http_client: httpx.Client, unique_email: str):
        """Test that login response includes basic fields."""
        password = "SecurePass123!"
        
        # Register
        http_client.post(
            "/api/auth/register",
            json={
                "email": unique_email,
                "password": password,
                "confirm_password": password,
                "full_name": "Test User",
            },
        )
        
        # Login
        response = http_client.post(
            "/api/auth/login",
            json={
                "email": unique_email,
                "password": password,
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "token_type" in data

    def test_register_response_includes_basic_fields(self, http_client: httpx.Client, unique_email: str):
        """Test that register response includes basic fields."""
        response = http_client.post(
            "/api/auth/register",
            json={
                "email": unique_email,
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
                "full_name": "Test User",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "token_type" in data


# =============================================================================
# EXTENSION AUTH STATUS TESTS
# =============================================================================


class TestExtensionAuthStatus:
    """Tests for the extension auth status endpoint."""

    def test_extension_status_unauthenticated(self, http_client: httpx.Client):
        """Test extension auth status when not authenticated."""
        response = http_client.get("/api/v1/auth/extension-status")
        
        # Should return 401 or 403 for unauthenticated requests
        assert response.status_code in [401, 403]

    def test_extension_status_authenticated(self, http_client: httpx.Client, authenticated_user: Dict):
        """Test extension auth status when authenticated."""
        response = http_client.get(
            "/api/v1/auth/extension-status",
            headers={"Authorization": f"Bearer {authenticated_user['token']}"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("authenticated") is True
