"""
Comprehensive tests for API Key Management (BYOK) endpoints.

These tests cover the complete BYOK (Bring Your Own Key) functionality:
- GET /api/v1/profile/api-key/status - Check if user has API key configured
- POST /api/v1/profile/api-key - Save/update API key
- DELETE /api/v1/profile/api-key - Delete API key
- POST /api/v1/profile/api-key/validate - Validate key before saving

Tests run against the actual running server at localhost:8000.
Make sure the server is running before executing these tests.
"""

import uuid
import pytest
import httpx
from typing import Dict

from tests.gemini_test_keys import DUMMY_GEMINI_API_KEY
from tests.live_server_helpers import real_gemini_api_key, skip_unless_real_gemini


# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_URL = "http://localhost:8000"

# Prefer a real env key for live validate calls; otherwise use format-valid dummy.
VALID_TEST_API_KEY = real_gemini_api_key() or DUMMY_GEMINI_API_KEY

# Fake keys for testing validation failures (non-AIzaSy shapes to avoid secret scanning)
FAKE_API_KEY_VALID_FORMAT = "Gsk_NotARealKeyThisIsFakeFakeFakeFake12"
FAKE_API_KEY_TOO_SHORT = "Gsk_Short"
FAKE_API_KEY_WITH_SPACES = "Gsk_invalid key with spaces herexx"
FAKE_API_KEY_WITH_SPECIAL_CHARS = "Gsk_!@#$%^&*()_+=[]{}|;':\",./<>?"


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def unique_email():
    """Generate a unique email for testing."""
    return f"test_apikey_{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture
def http_client():
    """Create a sync HTTP client for testing."""
    with httpx.Client(base_url=BASE_URL, timeout=30.0, follow_redirects=True) as client:
        yield client


@pytest.fixture
def authenticated_user(http_client: httpx.Client, unique_email: str):
    """Create and authenticate a test user, return headers with token."""
    # Register a new user
    register_response = http_client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
            "full_name": "API Key Test User",
        },
    )
    assert register_response.status_code == 200, f"Registration failed: {register_response.text}"
    
    token = register_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def second_authenticated_user(http_client: httpx.Client):
    """Create a second authenticated user for isolation tests."""
    unique_email = f"test_apikey_second_{uuid.uuid4().hex[:8]}@example.com"
    register_response = http_client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
            "full_name": "Second API Key Test User",
        },
    )
    assert register_response.status_code == 200
    
    token = register_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# =============================================================================
# API KEY STATUS TESTS
# =============================================================================


class TestApiKeyStatus:
    """Tests for GET /api/v1/profile/api-key/status endpoint."""

    def test_get_status_no_key_initially(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that new users have no API key configured."""
        response = http_client.get(
            "/api/v1/profile/api-key/status",
            headers=authenticated_user,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "has_api_key" in data
        assert "key_preview" in data
        assert data["has_api_key"] is False
        assert data["key_preview"] is None

    def test_get_status_without_auth(self, http_client: httpx.Client):
        """Test that unauthenticated requests are rejected."""
        response = http_client.get("/api/v1/profile/api-key/status")
        
        assert response.status_code in [401, 403]
        data = response.json()
        assert "error_code" in data or "detail" in data

    def test_get_status_with_invalid_token(self, http_client: httpx.Client):
        """Test that invalid tokens are rejected."""
        response = http_client.get(
            "/api/v1/profile/api-key/status",
            headers={"Authorization": "Bearer invalid_token_here"},
        )
        
        assert response.status_code in [401, 403]

    def test_get_status_with_malformed_auth_header(self, http_client: httpx.Client):
        """Test that malformed authorization headers are rejected."""
        # Missing Bearer prefix
        response = http_client.get(
            "/api/v1/profile/api-key/status",
            headers={"Authorization": "some_token_without_bearer"},
        )
        
        assert response.status_code in [401, 403]

    def test_get_status_with_expired_token(self, http_client: httpx.Client):
        """Test that expired tokens are rejected."""
        # This is a valid format JWT but expired (exp in the past)
        expired_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0IiwiZXhwIjoxfQ.signature"
        
        response = http_client.get(
            "/api/v1/profile/api-key/status",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        
        assert response.status_code in [401, 403]


# =============================================================================
# API KEY SET/UPDATE TESTS
# =============================================================================


class TestApiKeySet:
    """Tests for POST /api/v1/profile/api-key endpoint."""

    def test_set_api_key_success(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test successfully setting an API key."""
        response = http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "saved successfully" in data["message"].lower()

    def test_set_api_key_persists(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that saved API key persists and can be verified."""
        # Set the API key
        set_response = http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        assert set_response.status_code == 200
        
        # Verify it's saved
        status_response = http_client.get(
            "/api/v1/profile/api-key/status",
            headers=authenticated_user,
        )
        
        assert status_response.status_code == 200
        data = status_response.json()
        assert data["has_api_key"] is True
        assert data["key_preview"] is not None

    def test_set_api_key_preview_format(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that key preview shows first 4 and last 4 characters."""
        # Set the API key
        http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        
        # Get status and verify preview format
        status_response = http_client.get(
            "/api/v1/profile/api-key/status",
            headers=authenticated_user,
        )
        
        data = status_response.json()
        key_preview = data["key_preview"]
        
        # Preview should be in format "XXXX...YYYY"
        assert "..." in key_preview
        vk = VALID_TEST_API_KEY
        if len(vk) > 8:
            assert key_preview == f"{vk[:4]}...{vk[-4:]}"

    def test_set_api_key_update_existing(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test updating an existing API key."""
        # Set initial key
        http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        
        # Update with same key (should succeed)
        update_response = http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        
        assert update_response.status_code == 200
        
        # Verify key is still set
        status_response = http_client.get(
            "/api/v1/profile/api-key/status",
            headers=authenticated_user,
        )
        assert status_response.json()["has_api_key"] is True

    def test_set_api_key_too_short(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that keys shorter than 20 characters are rejected."""
        response = http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": FAKE_API_KEY_TOO_SHORT},
        )
        
        assert response.status_code in [400, 422]
        data = response.json()
        # Should indicate string too short
        assert "error" in data or "detail" in data or "message" in data

    def test_set_api_key_too_long(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that keys longer than 512 characters are rejected."""
        long_key = "Gsk_" + ("a" * 520)
        
        response = http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": long_key},
        )
        
        assert response.status_code in [400, 422]

    def test_set_api_key_with_spaces(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that keys with spaces are rejected."""
        response = http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": FAKE_API_KEY_WITH_SPACES},
        )
        
        assert response.status_code in [400, 422]

    def test_set_api_key_with_special_characters(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that keys with special characters are rejected."""
        response = http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": FAKE_API_KEY_WITH_SPECIAL_CHARS},
        )
        
        assert response.status_code in [400, 422]

    def test_set_api_key_empty_string(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that empty string is rejected."""
        response = http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": ""},
        )
        
        assert response.status_code in [400, 422]

    def test_set_api_key_missing_field(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that missing api_key field is rejected."""
        response = http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={},
        )
        
        assert response.status_code in [400, 422]

    def test_set_api_key_without_auth(self, http_client: httpx.Client):
        """Test that unauthenticated requests are rejected."""
        response = http_client.post(
            "/api/v1/profile/api-key",
            json={"api_key": VALID_TEST_API_KEY},
        )
        
        assert response.status_code in [401, 403]

    def test_set_api_key_whitespace_trimmed(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that whitespace around key is trimmed."""
        # Add whitespace around valid key
        key_with_whitespace = f"  {VALID_TEST_API_KEY}  "
        
        response = http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": key_with_whitespace},
        )
        
        # Should succeed after trimming whitespace
        assert response.status_code == 200


# =============================================================================
# API KEY DELETE TESTS
# =============================================================================


class TestApiKeyDelete:
    """Tests for DELETE /api/v1/profile/api-key endpoint."""

    def test_delete_api_key_success(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test successfully deleting an API key."""
        # First set a key
        http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        
        # Delete the key
        delete_response = http_client.delete(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
        )
        
        assert delete_response.status_code == 200
        data = delete_response.json()
        assert "message" in data
        assert "deleted successfully" in data["message"].lower()

    def test_delete_api_key_removes_from_storage(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that deleting actually removes the key."""
        # Set a key
        http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        
        # Verify key exists
        status_before = http_client.get(
            "/api/v1/profile/api-key/status",
            headers=authenticated_user,
        )
        assert status_before.json()["has_api_key"] is True
        
        # Delete the key
        http_client.delete(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
        )
        
        # Verify key is gone
        status_after = http_client.get(
            "/api/v1/profile/api-key/status",
            headers=authenticated_user,
        )
        assert status_after.json()["has_api_key"] is False
        assert status_after.json()["key_preview"] is None

    def test_delete_api_key_when_none_exists(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test deleting when no key exists (should succeed gracefully)."""
        response = http_client.delete(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
        )
        
        # Should succeed even if no key exists
        assert response.status_code == 200

    def test_delete_api_key_idempotent(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that deleting multiple times is safe."""
        # Set a key first
        http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        
        # Delete multiple times
        for _ in range(3):
            response = http_client.delete(
                "/api/v1/profile/api-key",
                headers=authenticated_user,
            )
            assert response.status_code == 200

    def test_delete_api_key_without_auth(self, http_client: httpx.Client):
        """Test that unauthenticated deletes are rejected."""
        response = http_client.delete("/api/v1/profile/api-key")
        
        assert response.status_code in [401, 403]


# =============================================================================
# API KEY VALIDATION TESTS
# =============================================================================


class TestApiKeyValidate:
    """Tests for POST /api/v1/profile/api-key/validate endpoint."""

    def test_validate_valid_key(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test validating a real, working API key."""
        skip_unless_real_gemini()
        response = http_client.post(
            "/api/v1/profile/api-key/validate",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY, "provider": "gemini"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert "message" in data
        assert "models_available" in data
        assert data["models_available"] > 0

    def test_validate_fake_key(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test validating a fake key with valid format."""
        response = http_client.post(
            "/api/v1/profile/api-key/validate",
            headers=authenticated_user,
            json={"api_key": FAKE_API_KEY_VALID_FORMAT},
        )
        
        assert response.status_code in [400, 422]
        data = response.json()
        # Should indicate validation failed
        assert "validation failed" in data.get("message", "").lower() or \
               "error" in data or "detail" in data

    def test_validate_invalid_format(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test validating a key with invalid format."""
        response = http_client.post(
            "/api/v1/profile/api-key/validate",
            headers=authenticated_user,
            json={"api_key": FAKE_API_KEY_TOO_SHORT},
        )
        
        assert response.status_code in [400, 422]

    def test_validate_empty_key(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test validating an empty key."""
        response = http_client.post(
            "/api/v1/profile/api-key/validate",
            headers=authenticated_user,
            json={"api_key": ""},
        )
        
        assert response.status_code in [400, 422]

    def test_validate_missing_field(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test validating without api_key field."""
        response = http_client.post(
            "/api/v1/profile/api-key/validate",
            headers=authenticated_user,
            json={},
        )
        
        assert response.status_code in [400, 422]

    def test_validate_without_auth(self, http_client: httpx.Client):
        """Test that unauthenticated validation is rejected."""
        response = http_client.post(
            "/api/v1/profile/api-key/validate",
            json={"api_key": VALID_TEST_API_KEY},
        )
        
        assert response.status_code in [401, 403]

    def test_validate_does_not_save(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that validation does not save the key."""
        # Validate a key (but don't save)
        http_client.post(
            "/api/v1/profile/api-key/validate",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        
        # Check status - should NOT have the key saved
        status_response = http_client.get(
            "/api/v1/profile/api-key/status",
            headers=authenticated_user,
        )
        
        data = status_response.json()
        # Key should not be saved just from validation
        assert data["has_api_key"] is False


# =============================================================================
# API KEY LIFECYCLE TESTS
# =============================================================================


class TestApiKeyLifecycle:
    """Tests for complete API key lifecycle (CRUD operations)."""

    def test_full_crud_lifecycle(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test complete Create, Read, Update, Delete lifecycle."""
        # CREATE - Set initial key
        create_response = http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        assert create_response.status_code == 200
        
        # READ - Verify key exists
        read_response = http_client.get(
            "/api/v1/profile/api-key/status",
            headers=authenticated_user,
        )
        assert read_response.status_code == 200
        assert read_response.json()["has_api_key"] is True
        
        # UPDATE - Update with same key
        update_response = http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        assert update_response.status_code == 200
        
        # DELETE - Remove key
        delete_response = http_client.delete(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
        )
        assert delete_response.status_code == 200
        
        # Verify deletion
        final_status = http_client.get(
            "/api/v1/profile/api-key/status",
            headers=authenticated_user,
        )
        assert final_status.json()["has_api_key"] is False

    def test_validate_then_save(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test typical workflow: validate first, then save."""
        skip_unless_real_gemini()
        # Step 1: Validate the key
        validate_response = http_client.post(
            "/api/v1/profile/api-key/validate",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        assert validate_response.status_code == 200
        assert validate_response.json()["valid"] is True
        
        # Step 2: Save the key
        save_response = http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        assert save_response.status_code == 200
        
        # Step 3: Verify saved
        status_response = http_client.get(
            "/api/v1/profile/api-key/status",
            headers=authenticated_user,
        )
        assert status_response.json()["has_api_key"] is True

    def test_set_delete_set_again(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test setting, deleting, and setting key again."""
        # Set initial key
        http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        assert http_client.get(
            "/api/v1/profile/api-key/status",
            headers=authenticated_user,
        ).json()["has_api_key"] is True
        
        # Delete key
        http_client.delete(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
        )
        assert http_client.get(
            "/api/v1/profile/api-key/status",
            headers=authenticated_user,
        ).json()["has_api_key"] is False
        
        # Set key again
        http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        assert http_client.get(
            "/api/v1/profile/api-key/status",
            headers=authenticated_user,
        ).json()["has_api_key"] is True


# =============================================================================
# API KEY ISOLATION TESTS
# =============================================================================


class TestApiKeyIsolation:
    """Tests to verify user API keys are properly isolated."""

    def test_keys_isolated_between_users(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        second_authenticated_user: Dict[str, str],
    ):
        """Test that one user's key doesn't affect another user."""
        # User 1 sets a key
        http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        
        # User 2 should NOT have a key
        user2_status = http_client.get(
            "/api/v1/profile/api-key/status",
            headers=second_authenticated_user,
        )
        assert user2_status.json()["has_api_key"] is False
        
        # User 1 should still have key
        user1_status = http_client.get(
            "/api/v1/profile/api-key/status",
            headers=authenticated_user,
        )
        assert user1_status.json()["has_api_key"] is True

    def test_user_cannot_delete_others_key(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        second_authenticated_user: Dict[str, str],
    ):
        """Test that one user cannot delete another user's key."""
        # User 1 sets a key
        http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        
        # User 2 tries to delete (their own, which doesn't exist)
        http_client.delete(
            "/api/v1/profile/api-key",
            headers=second_authenticated_user,
        )
        
        # User 1's key should still exist
        user1_status = http_client.get(
            "/api/v1/profile/api-key/status",
            headers=authenticated_user,
        )
        assert user1_status.json()["has_api_key"] is True


# =============================================================================
# API KEY EDGE CASES AND SECURITY TESTS
# =============================================================================


class TestApiKeyEdgeCases:
    """Tests for edge cases and security considerations."""

    def test_key_not_exposed_in_status(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that the full key is never exposed in status response."""
        # Set the key
        http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        
        # Get status
        status_response = http_client.get(
            "/api/v1/profile/api-key/status",
            headers=authenticated_user,
        )
        
        data = status_response.json()
        
        # Full key should NOT be in response
        response_text = str(data)
        assert VALID_TEST_API_KEY not in response_text
        
        # Preview should be masked
        if data["key_preview"]:
            assert len(data["key_preview"]) < len(VALID_TEST_API_KEY)
            assert "..." in data["key_preview"]

    def test_key_not_exposed_in_profile(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that API key is not exposed in profile data."""
        # Set the key
        http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        
        # Get full profile
        profile_response = http_client.get(
            "/api/v1/profile",
            headers=authenticated_user,
        )
        
        # Full key should NOT appear anywhere in profile
        response_text = str(profile_response.json())
        assert VALID_TEST_API_KEY not in response_text

    def test_multiple_rapid_updates(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test rapid consecutive updates don't cause issues."""
        for i in range(5):
            response = http_client.post(
                "/api/v1/profile/api-key",
                headers=authenticated_user,
                json={"api_key": VALID_TEST_API_KEY},
            )
            assert response.status_code == 200
        
        # Verify final state
        status = http_client.get(
            "/api/v1/profile/api-key/status",
            headers=authenticated_user,
        )
        assert status.json()["has_api_key"] is True

    def test_key_with_only_numbers(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test key with only numbers (valid format but likely invalid key)."""
        numeric_key = "12345678901234567890123456789012345678901"  # 41 chars
        
        response = http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": numeric_key},
        )
        
        # Should pass format validation but might fail actual validation
        assert response.status_code in [200, 400]

    def test_key_with_underscores_and_hyphens(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test key with valid characters (underscores and hyphens)."""
        key_with_chars = "AIzaSy_valid-key_format-test123456"
        
        response = http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": key_with_chars},
        )
        
        # Format should be valid (underscores/hyphens allowed)
        # Actual key validation might fail since it's fake
        assert response.status_code in [200, 400]

    def test_unicode_in_key_rejected(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that unicode characters in key are rejected."""
        unicode_key = "AIzaSy中文字符テストキー1234567890"
        
        response = http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": unicode_key},
        )
        
        assert response.status_code in [400, 422]

    def test_null_api_key_rejected(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that null api_key value is rejected."""
        response = http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": None},
        )
        
        assert response.status_code in [400, 422]


# =============================================================================
# API KEY RESPONSE FORMAT TESTS
# =============================================================================


class TestApiKeyResponseFormat:
    """Tests for correct response format and structure."""

    def test_status_response_structure(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test status response has correct structure."""
        response = http_client.get(
            "/api/v1/profile/api-key/status",
            headers=authenticated_user,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        assert "has_api_key" in data
        assert "key_preview" in data
        
        # Type checks
        assert isinstance(data["has_api_key"], bool)
        assert data["key_preview"] is None or isinstance(data["key_preview"], str)

    def test_save_response_structure(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test save response has correct structure."""
        response = http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "message" in data
        assert isinstance(data["message"], str)

    def test_delete_response_structure(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test delete response has correct structure."""
        response = http_client.delete(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "message" in data
        assert isinstance(data["message"], str)

    def test_validate_success_response_structure(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test successful validation response structure."""
        skip_unless_real_gemini()
        response = http_client.post(
            "/api/v1/profile/api-key/validate",
            headers=authenticated_user,
            json={"api_key": VALID_TEST_API_KEY},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "valid" in data
        assert "message" in data
        assert "models_available" in data
        
        assert isinstance(data["valid"], bool)
        assert isinstance(data["message"], str)
        assert isinstance(data["models_available"], int)

    def test_error_response_structure(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test error response has correct structure."""
        response = http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": "short"},  # Too short - should fail
        )
        
        assert response.status_code in [400, 422]
        data = response.json()
        
        # Error response should have these fields
        assert "success" in data or "error_code" in data or "detail" in data
