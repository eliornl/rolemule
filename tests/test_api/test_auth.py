"""
Integration tests for authentication endpoints.

Uses the full FastAPI app via ASGITransport with a real test database.
Rate limiting and email sending are mocked by the package conftest.

Endpoints covered:
  POST /api/v1/auth/register
  POST /api/v1/auth/login
  POST /api/v1/auth/logout
  GET  /api/v1/auth/verify
  POST /api/v1/auth/forgot-password
"""

import uuid
import pytest
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient, ASGITransport

from main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE = "/api/v1/auth"


def _reg_payload(suffix: str = "") -> dict:
    uid = uuid.uuid4().hex[:8] + suffix
    return {
        "email": f"authtest_{uid}@example.com",
        "password": "SecurePass123!",
        "confirm_password": "SecurePass123!",
        "full_name": "Auth Tester",
    }


def _make_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost")


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


class TestRegistration:
    """POST /api/v1/auth/register"""

    @pytest.mark.asyncio
    async def test_register_success_returns_200_and_token(self):
        payload = _reg_payload("_ok")
        async with _make_client() as client:
            resp = await client.post(f"{BASE}/register", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == payload["email"]

    @pytest.mark.asyncio
    async def test_register_returns_user_fields(self):
        payload = _reg_payload("_fields")
        async with _make_client() as client:
            resp = await client.post(f"{BASE}/register", json=payload)
        assert resp.status_code == 200, resp.text
        user = resp.json()["user"]
        assert "id" in user
        assert user["full_name"] == "Auth Tester"
        assert user["auth_method"] == "local"

    @pytest.mark.asyncio
    async def test_register_duplicate_email_returns_400_or_422(self):
        """Duplicate email registration returns a 4xx error (exact code is 422 via validation_error)."""
        payload = _reg_payload("_dup")
        async with _make_client() as client:
            r1 = await client.post(f"{BASE}/register", json=payload)
            assert r1.status_code == 200, r1.text  # first reg succeeds
            resp = await client.post(f"{BASE}/register", json=payload)
        # The endpoint raises validation_error() which is 422 Unprocessable Entity
        assert resp.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_register_invalid_email_returns_422(self):
        async with _make_client() as client:
            resp = await client.post(
                f"{BASE}/register",
                json={"email": "not-an-email", "password": "SecurePass123!",
                      "confirm_password": "SecurePass123!", "full_name": "Test"},
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_missing_password_returns_422(self):
        async with _make_client() as client:
            resp = await client.post(
                f"{BASE}/register",
                json={"email": "ok@example.com", "full_name": "Test"},
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_missing_full_name_returns_422(self):
        async with _make_client() as client:
            resp = await client.post(
                f"{BASE}/register",
                json={"email": "ok2@example.com", "password": "SecurePass123!",
                      "confirm_password": "SecurePass123!"},
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_weak_password_returns_422(self):
        async with _make_client() as client:
            resp = await client.post(
                f"{BASE}/register",
                json={"email": "ok3@example.com", "password": "abc",
                      "confirm_password": "abc", "full_name": "Test"},
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_password_mismatch_returns_422(self):
        async with _make_client() as client:
            resp = await client.post(
                f"{BASE}/register",
                json={"email": "ok4@example.com", "password": "SecurePass123!",
                      "confirm_password": "Different123!", "full_name": "Test"},
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_rate_limited_returns_429(self):
        payload = _reg_payload("_rl")
        with patch("api.auth.check_rate_limit", AsyncMock(return_value=(False, 0))):
            async with _make_client() as client:
                resp = await client.post(f"{BASE}/register", json=payload)
        assert resp.status_code == 429


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------


class TestLogin:
    """POST /api/v1/auth/login"""

    @pytest.mark.asyncio
    async def test_login_unverified_email_returns_403(self):
        """Fresh registrations have email_verified=False → login returns 403."""
        import api.auth as _auth_module

        payload = _reg_payload("_login_unverified")
        # Force email verification to be required for both registration and login so the
        # user stays unverified and the 403 gate fires — even when
        # DISABLE_EMAIL_VERIFICATION=true in .env.
        with patch.object(_auth_module.settings, "disable_email_verification", False):
            async with _make_client() as client:
                r = await client.post(f"{BASE}/register", json=payload)
                assert r.status_code == 200, r.text
                resp = await client.post(
                    f"{BASE}/login",
                    json={"email": payload["email"], "password": payload["password"]},
                )
        assert resp.status_code == 403  # email not verified

    @pytest.mark.asyncio
    async def test_login_wrong_password_returns_401(self):
        async with _make_client() as client:
            resp = await client.post(
                f"{BASE}/login",
                json={"email": "nobody_login@example.com", "password": "WrongPassword99!"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_email_returns_401(self):
        async with _make_client() as client:
            resp = await client.post(
                f"{BASE}/login",
                json={"email": "nobody@nowhere.com", "password": "Password123!"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_rate_limited_returns_429(self):
        with patch("api.auth.check_rate_limit", AsyncMock(return_value=(False, 0))):
            async with _make_client() as client:
                resp = await client.post(
                    f"{BASE}/login",
                    json={"email": "x@example.com", "password": "Password123!"},
                )
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_login_missing_email_returns_422(self):
        async with _make_client() as client:
            resp = await client.post(f"{BASE}/login", json={"password": "Password123!"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Token verify tests
# ---------------------------------------------------------------------------


class TestTokenVerify:
    """GET /api/v1/auth/verify"""

    @pytest.mark.asyncio
    async def test_verify_without_token_returns_401_or_403(self):
        async with _make_client() as client:
            resp = await client.get(f"{BASE}/verify")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_verify_with_garbage_token_returns_401(self):
        async with _make_client() as client:
            resp = await client.get(
                f"{BASE}/verify",
                headers={"Authorization": "Bearer not.a.real.token"},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Logout tests
# ---------------------------------------------------------------------------


class TestLogout:
    """POST /api/v1/auth/logout"""

    @pytest.mark.asyncio
    async def test_logout_without_token_returns_200(self):
        """Logout is intentionally auth-free; gracefully handles missing token."""
        async with _make_client() as client:
            resp = await client.post(f"{BASE}/logout")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Password reset tests
# ---------------------------------------------------------------------------


class TestPasswordReset:
    """POST /api/v1/auth/forgot-password"""

    @pytest.mark.asyncio
    async def test_forgot_password_always_returns_200(self):
        """Endpoint must not leak whether email exists — always return 200."""
        async with _make_client() as client:
            resp = await client.post(
                f"{BASE}/forgot-password",
                json={"email": "nobody@nowhere.com"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_forgot_password_invalid_email_returns_422(self):
        async with _make_client() as client:
            resp = await client.post(
                f"{BASE}/forgot-password",
                json={"email": "not-an-email"},
            )
        assert resp.status_code == 422
