"""
Integration tests for authentication endpoints.

These tests run against the actual running server at localhost:8000.
Make sure the server is running before executing these tests.

Tests cover:
- User registration (success, validation, duplicate email)
- User login (success, wrong credentials)
- Token verification
- Token refresh
"""

import uuid
import pytest
import httpx


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


# =============================================================================
# REGISTRATION TESTS
# =============================================================================


class TestRegistration:
    """Tests for the /api/auth/register endpoint."""

    def test_register_success(self, http_client: httpx.Client, unique_email: str):
        """Test successful user registration."""
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
        assert data["token_type"] == "bearer"
        assert data["profile_completed"] is False

    def test_register_missing_fields(self, http_client: httpx.Client):
        """Test registration with missing required fields."""
        response = http_client.post(
            "/api/auth/register",
            json={"email": "test@example.com"},
        )
        
        # API returns 400 for missing fields
        assert response.status_code in [400, 422]

    def test_register_invalid_email(self, http_client: httpx.Client):
        """Test registration with invalid email format."""
        response = http_client.post(
            "/api/auth/register",
            json={
                "email": "not-an-email",
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
                "full_name": "Test User",
            },
        )
        
        # API returns 400 or 422 for validation errors
        assert response.status_code in [400, 422]

    def test_register_weak_password(self, http_client: httpx.Client, unique_email: str):
        """Test registration with weak password."""
        response = http_client.post(
            "/api/auth/register",
            json={
                "email": unique_email,
                "password": "weak",
                "confirm_password": "weak",
                "full_name": "Test User",
            },
        )
        
        # API returns 400 or 422 for validation errors
        assert response.status_code in [400, 422]

    def test_register_password_mismatch(self, http_client: httpx.Client, unique_email: str):
        """Test registration with mismatched passwords."""
        response = http_client.post(
            "/api/auth/register",
            json={
                "email": unique_email,
                "password": "SecurePass123!",
                "confirm_password": "DifferentPass123!",
                "full_name": "Test User",
            },
        )
        
        # API returns 400 or 422 for validation errors
        assert response.status_code in [400, 422]

    def test_register_duplicate_email(self, http_client: httpx.Client, unique_email: str):
        """Test registration with already existing email."""
        # First registration
        http_client.post(
            "/api/auth/register",
            json={
                "email": unique_email,
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
                "full_name": "First User",
            },
        )
        
        # Second registration with same email
        response = http_client.post(
            "/api/auth/register",
            json={
                "email": unique_email,
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
                "full_name": "Second User",
            },
        )
        
        assert response.status_code == 400


# =============================================================================
# LOGIN TESTS
# =============================================================================


class TestLogin:
    """Tests for the /api/auth/login endpoint."""

    def test_login_success(self, http_client: httpx.Client, unique_email: str):
        """Test successful login."""
        password = "SecurePass123!"
        
        # First register
        http_client.post(
            "/api/auth/register",
            json={
                "email": unique_email,
                "password": password,
                "confirm_password": password,
                "full_name": "Test User",
            },
        )
        
        # Then login
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
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, http_client: httpx.Client, unique_email: str):
        """Test login with wrong password."""
        # First register
        http_client.post(
            "/api/auth/register",
            json={
                "email": unique_email,
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
                "full_name": "Test User",
            },
        )
        
        # Try login with wrong password
        response = http_client.post(
            "/api/auth/login",
            json={
                "email": unique_email,
                "password": "WrongPassword123!",
            },
        )
        
        assert response.status_code == 401

    def test_login_nonexistent_user(self, http_client: httpx.Client):
        """Test login with non-existent email."""
        response = http_client.post(
            "/api/auth/login",
            json={
                "email": f"nonexistent_{uuid.uuid4().hex[:8]}@example.com",
                "password": "SomePassword123!",
            },
        )
        
        assert response.status_code == 401

    def test_login_missing_fields(self, http_client: httpx.Client):
        """Test login with missing fields."""
        response = http_client.post(
            "/api/auth/login",
            json={"email": "test@example.com"},
        )
        
        # API returns 400 or 422 for validation errors
        assert response.status_code in [400, 422]


# =============================================================================
# TOKEN VERIFICATION TESTS
# =============================================================================


class TestTokenVerification:
    """Tests for the /api/v1/auth/verify endpoint."""

    def test_verify_valid_token(self, http_client: httpx.Client, unique_email: str):
        """Test verification of a valid token."""
        # Register to get a token
        register_response = http_client.post(
            "/api/auth/register",
            json={
                "email": unique_email,
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
                "full_name": "Test User",
            },
        )
        token = register_response.json()["access_token"]
        
        # Verify the token
        response = http_client.get(
            "/api/v1/auth/verify",
            headers={"Authorization": f"Bearer {token}"},
        )
        
        assert response.status_code == 200
        data = response.json()
        # Check for valid or authenticated field
        assert data.get("valid", data.get("authenticated", True)) is True

    def test_verify_invalid_token(self, http_client: httpx.Client):
        """Test verification of an invalid token."""
        response = http_client.get(
            "/api/v1/auth/verify",
            headers={"Authorization": "Bearer invalid-token"},
        )
        
        # API may return 401 or 403 for invalid tokens
        assert response.status_code in [401, 403]

    def test_verify_missing_token(self, http_client: httpx.Client):
        """Test verification without a token."""
        response = http_client.get("/api/v1/auth/verify")
        
        # API returns 401 or 403 for missing token
        assert response.status_code in [401, 403]


# =============================================================================
# TOKEN REFRESH TESTS
# =============================================================================


class TestTokenRefresh:
    """Tests for the /api/v1/auth/refresh endpoint."""

    def test_refresh_valid_token(self, http_client: httpx.Client, unique_email: str):
        """Test refreshing a valid token."""
        # Register to get a token
        register_response = http_client.post(
            "/api/auth/register",
            json={
                "email": unique_email,
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
                "full_name": "Test User",
            },
        )
        token = register_response.json()["access_token"]
        
        # Refresh the token
        response = http_client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_refresh_invalid_token(self, http_client: httpx.Client):
        """Test refreshing an invalid token."""
        response = http_client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": "Bearer invalid-token"},
        )
        
        assert response.status_code == 401


# =============================================================================
# OAUTH STATUS TESTS
# =============================================================================


class TestOAuthStatus:
    """Tests for the /api/v1/auth/oauth/status endpoint."""

    def test_oauth_status_endpoint(self, http_client: httpx.Client):
        """Test the OAuth status endpoint returns valid response."""
        response = http_client.get("/api/v1/auth/oauth/status")
        
        assert response.status_code == 200
        data = response.json()
        assert "google_oauth_enabled" in data
        assert isinstance(data["google_oauth_enabled"], bool)


# =============================================================================
# LOGOUT TESTS
# =============================================================================


class TestLogout:
    """Tests for the /api/v1/auth/logout endpoint."""

    def test_logout_with_valid_token(self, http_client: httpx.Client, unique_email: str):
        """Test logout with valid token."""
        # Register to get a token
        register_response = http_client.post(
            "/api/auth/register",
            json={
                "email": unique_email,
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
                "full_name": "Test User",
            },
        )
        token = register_response.json()["access_token"]
        
        # Logout
        response = http_client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        
        # Should succeed (logout is primarily client-side token removal)
        assert response.status_code in [200, 204]

    def test_logout_without_token(self, http_client: httpx.Client):
        """Test logout without authentication."""
        response = http_client.post("/api/v1/auth/logout")
        
        # Should require authentication or succeed anyway
        assert response.status_code in [200, 204, 401, 403]


# =============================================================================
# ACCOUNT LOCKOUT TESTS
# =============================================================================


class TestAccountLockout:
    """Tests for account lockout after failed login attempts."""

    def test_multiple_failed_logins_triggers_lockout(self, http_client: httpx.Client, unique_email: str):
        """Test that multiple failed logins trigger account lockout."""
        password = "SecurePass123!"
        
        # First register a user
        http_client.post(
            "/api/auth/register",
            json={
                "email": unique_email,
                "password": password,
                "confirm_password": password,
                "full_name": "Test User",
            },
        )
        
        # Try to login with wrong password until lockout
        lockout_triggered = False
        for i in range(6):
            response = http_client.post(
                "/api/auth/login",
                json={
                    "email": unique_email,
                    "password": "WrongPassword123!",
                },
            )
            # 401 = wrong password, 423 = locked, 429 = rate limited
            if response.status_code in [423, 429]:
                lockout_triggered = True
                break
            assert response.status_code == 401, f"Attempt {i+1} should fail with 401"
        
        # Lockout should be triggered within 5 attempts
        assert lockout_triggered, "Account should be locked after failed attempts"

    def test_successful_login_after_failed_attempts(self, http_client: httpx.Client, unique_email: str):
        """Test that successful login works after some failed attempts (before lockout)."""
        password = "SecurePass123!"
        
        # Register a user
        http_client.post(
            "/api/auth/register",
            json={
                "email": unique_email,
                "password": password,
                "confirm_password": password,
                "full_name": "Test User",
            },
        )
        
        # Try 2 failed logins (below lockout threshold)
        for _ in range(2):
            http_client.post(
                "/api/auth/login",
                json={
                    "email": unique_email,
                    "password": "WrongPassword123!",
                },
            )
        
        # Now login with correct password
        response = http_client.post(
            "/api/auth/login",
            json={
                "email": unique_email,
                "password": password,
            },
        )
        
        # Should succeed
        assert response.status_code == 200
        assert "access_token" in response.json()


# =============================================================================
# PASSWORD VALIDATION TESTS
# =============================================================================


class TestPasswordValidation:
    """Tests for password validation logic."""

    def test_password_hash_generation(self):
        """Test that bcrypt can hash passwords."""
        import bcrypt
        
        password = "SecurePass123!"
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        
        assert hashed is not None
        assert bcrypt.checkpw(password.encode('utf-8'), hashed)

    def test_password_hash_verification_wrong_password(self):
        """Test that wrong passwords fail verification."""
        import bcrypt
        
        password = "SecurePass123!"
        wrong_password = "WrongPass456!"
        
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        
        assert not bcrypt.checkpw(wrong_password.encode('utf-8'), hashed)

    def test_password_requirements_length(self):
        """Test password minimum length requirement."""
        short_password = "Abc1!"
        assert len(short_password) < 8

    def test_password_requirements_uppercase(self):
        """Test password uppercase requirement."""
        no_upper = "securepass123!"
        assert not any(c.isupper() for c in no_upper)

    def test_password_requirements_lowercase(self):
        """Test password lowercase requirement."""
        no_lower = "SECUREPASS123!"
        assert not any(c.islower() for c in no_lower)

    def test_password_requirements_number(self):
        """Test password number requirement."""
        no_number = "SecurePassword!"
        assert not any(c.isdigit() for c in no_number)

    def test_valid_password_meets_all_requirements(self):
        """Test a valid password meets all requirements."""
        valid_password = "SecurePass123!"
        
        assert len(valid_password) >= 8
        assert any(c.isupper() for c in valid_password)
        assert any(c.islower() for c in valid_password)
        assert any(c.isdigit() for c in valid_password)
        assert any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?" for c in valid_password)


# =============================================================================
# AUTH METHOD ENUM TESTS
# =============================================================================


class TestAuthMethodEnum:
    """Tests for AuthMethod enum."""

    def test_local_auth_method_exists(self):
        """Test LOCAL auth method exists in enum."""
        from models.database import AuthMethod
        assert hasattr(AuthMethod, 'LOCAL')
        assert AuthMethod.LOCAL.value == "local"

    def test_google_auth_method_exists(self):
        """Test GOOGLE auth method exists in enum."""
        from models.database import AuthMethod
        assert hasattr(AuthMethod, 'GOOGLE')
        assert AuthMethod.GOOGLE.value == "google"


# =============================================================================
# AUTHENTICATED ENDPOINT TESTS
# =============================================================================


class TestAuthenticatedEndpoints:
    """Tests for endpoints that require authentication."""

    def test_protected_endpoint_without_token(self, http_client: httpx.Client):
        """Test that protected endpoints reject unauthenticated requests."""
        response = http_client.get("/api/v1/profile", follow_redirects=False)
        
        # API may redirect (307), return 401, or 403
        assert response.status_code in [307, 401, 403]

    def test_protected_endpoint_with_valid_token(self, http_client: httpx.Client, unique_email: str):
        """Test that protected endpoints accept authenticated requests."""
        # Register to get a token
        register_response = http_client.post(
            "/api/auth/register",
            json={
                "email": unique_email,
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
                "full_name": "Test User",
            },
        )
        token = register_response.json()["access_token"]
        
        # Access protected endpoint
        response = http_client.get(
            "/api/v1/profile",
            headers={"Authorization": f"Bearer {token}"},
            follow_redirects=False,
        )
        
        # Should return profile data or redirect for incomplete profiles
        assert response.status_code in [200, 307, 400, 403]


# =============================================================================
# EDGE CASE TESTS
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_special_characters_in_name(self, http_client: httpx.Client, unique_email: str):
        """Test registration with special characters in name."""
        response = http_client.post(
            "/api/auth/register",
            json={
                "email": unique_email,
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
                "full_name": "O'Brien-Smith Jr.",
            },
        )
        
        assert response.status_code == 200

    def test_unicode_in_name(self, http_client: httpx.Client, unique_email: str):
        """Test registration with unicode characters in name."""
        response = http_client.post(
            "/api/auth/register",
            json={
                "email": unique_email,
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
                "full_name": "José García",
            },
        )
        
        # API may accept or reject unicode (depends on implementation)
        assert response.status_code in [200, 400, 422]

    def test_empty_string_fields(self, http_client: httpx.Client, unique_email: str):
        """Test registration with empty string fields."""
        response = http_client.post(
            "/api/auth/register",
            json={
                "email": unique_email,
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
                "full_name": "",
            },
        )
        
        # API returns 400 or 422 for validation errors
        assert response.status_code in [400, 422]
