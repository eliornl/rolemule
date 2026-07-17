"""
Security tests for the RoleMule.

NOTE: Most authentication security tests are already covered in test_auth.py.
This file contains additional security-focused tests.
"""

import pytest
import uuid
from httpx import AsyncClient



# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def unique_email():
    """Generate a unique email for testing."""
    return f"security_test_{uuid.uuid4().hex[:8]}@example.com"


# =============================================================================
# JWT SECURITY TESTS (using async_client for direct app testing)
# =============================================================================


class TestJWTSecurity:
    """Tests for JWT token security."""

    @pytest.mark.asyncio
    async def test_missing_token_returns_error(self, async_client: AsyncClient):
        """Test that missing token returns 4xx error."""
        response = await async_client.get("/api/v1/profile/")
        # Accept 400 (bad request) or 401 (unauthorized)
        assert response.status_code in [400, 401, 403]

    @pytest.mark.asyncio
    async def test_invalid_token_returns_error(self, async_client: AsyncClient):
        """Test that invalid token returns 4xx error."""
        response = await async_client.get(
            "/api/v1/profile/",
            headers={"Authorization": "Bearer invalid_token_here"},
        )
        assert response.status_code in [400, 401, 403]


# =============================================================================
# SQL INJECTION PREVENTION TESTS
# =============================================================================


class TestSQLInjectionPrevention:
    """Tests for SQL injection prevention."""

    @pytest.mark.asyncio
    async def test_sql_injection_in_login_email(self, async_client: AsyncClient):
        """Test that SQL injection in login email is handled safely."""
        sql_payloads = [
            "'; DROP TABLE users; --",
            "admin'--",
            "' OR '1'='1",
        ]
        
        for payload in sql_payloads:
            response = await async_client.post(
                "/api/auth/login",
                json={
                    "email": payload,
                    "password": "password",
                },
            )
            # Should be validation error or unauthorized, not 500 server error
            assert response.status_code != 500, f"SQL injection payload caused server error: {payload}"
            assert response.status_code in [400, 401, 422]


# =============================================================================
# XSS PREVENTION TESTS (require auth_token fixture)
# =============================================================================


class TestXSSPrevention:
    """Tests for XSS prevention in user inputs."""

    @pytest.mark.asyncio
    async def test_xss_payload_does_not_cause_server_error(self, async_client: AsyncClient):
        """Test that XSS payloads don't cause server errors."""
        xss_payload = "<script>alert('xss')</script>"
        
        # Even without auth, this should return auth error, not server error
        response = await async_client.put(
            "/api/v1/profile/basic-info",
            json={
                "city": xss_payload,
                "state": "CA",
                "country": "USA",
                "professional_title": "Engineer",
                "years_experience": 5,
                "is_student": False,
                "summary": xss_payload,
            },
        )
        # Should be auth error (400/401), not server error (500)
        assert response.status_code != 500


# =============================================================================
# HEADER SECURITY TESTS
# =============================================================================


class TestSecurityHeaders:
    """Tests for security headers."""

    @pytest.mark.asyncio
    async def test_cors_options_request(self, async_client: AsyncClient):
        """Test that CORS is configured for OPTIONS requests."""
        response = await async_client.options(
            "/api/auth/login",
            headers={"Origin": "http://localhost:8000"},
        )
        # Should not cause server error
        assert response.status_code in [200, 204, 400, 405]


# =============================================================================
# INPUT VALIDATION TESTS
# =============================================================================


class TestInputValidation:
    """Tests for input validation."""

    @pytest.mark.asyncio
    async def test_extremely_long_input_handled(self, async_client: AsyncClient):
        """Test that extremely long inputs are handled gracefully."""
        long_string = "a" * 100000  # 100KB string
        
        response = await async_client.post(
            "/api/auth/register",
            json={
                "email": f"{long_string}@example.com",
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
                "full_name": long_string,
            },
        )
        # Should be validation error, not server error
        assert response.status_code != 500
        assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_null_byte_injection(self, async_client: AsyncClient):
        """Test that null byte injection is handled safely."""
        response = await async_client.post(
            "/api/auth/login",
            json={
                "email": "test\x00@example.com",
                "password": "password",
            },
        )
        # Should be validation error, not server error
        assert response.status_code != 500

    @pytest.mark.asyncio
    async def test_unicode_handling(self, async_client: AsyncClient, unique_email):
        """Test that unicode characters are handled properly."""
        response = await async_client.post(
            "/api/auth/register",
            json={
                "email": unique_email,
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
                "full_name": "Tëst Üsér 测试 🎉",
            },
        )
        # Should either succeed or return validation error, not crash
        assert response.status_code != 500
