"""
Extended integration tests for api/auth.py — verify-code, password flows, OAuth,
refresh/logout revocation, account lockout, and registration edge cases.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, update

import api.auth as auth_module
from api.auth import _make_jwt, pwd_context
from config.settings import get_security_settings
from main import app
from models.database import AuthMethod, User
from tests.test_api.conftest import _NullSessionLocal, _make_test_jwt

BASE = "/api/v1/auth"
pwd_ctx = pwd_context


def _make_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost")


def _reg_payload(suffix: str = "") -> dict:
    uid = uuid.uuid4().hex[:8] + suffix
    return {
        "email": f"authext_{uid}@example.com",
        "password": "SecurePass123!",
        "confirm_password": "SecurePass123!",
        "full_name": "Auth Extended Tester",
    }


class FakeRedis:
    """Minimal in-memory Redis stand-in with getdel/pipeline support."""

    def __init__(self) -> None:
        self._store: Dict[str, str] = {}

    async def setex(self, key: str, ttl: int, value: str) -> bool:
        self._store[key] = value
        return True

    async def get(self, key: str) -> Optional[str]:
        return self._store.get(key)

    async def getdel(self, key: str) -> Optional[str]:
        return self._store.pop(key, None)

    async def delete(self, key: str) -> int:
        self._store.pop(key, None)
        return 1

    def pipeline(self) -> "_FakePipeline":
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self._redis = redis
        self._ops: list[tuple[str, str, int, str]] = []

    def setex(self, key: str, ttl: int, value: str) -> "_FakePipeline":
        self._ops.append(("setex", key, ttl, value))
        return self

    async def execute(self) -> list:
        for _, key, _ttl, value in self._ops:
            self._redis._store[key] = value
        return [True] * len(self._ops)


async def _create_user(
    *,
    email: Optional[str] = None,
    password: str = "SecurePass123!",
    email_verified: bool = True,
    profile_completed: bool = False,
    auth_method: str = AuthMethod.LOCAL.value,
    google_id: Optional[str] = None,
) -> tuple[uuid.UUID, str]:
    uid = uuid.uuid4()
    email = email or f"user_{uid.hex[:10]}@example.com"
    password_hash = pwd_ctx.hash(password[:72])
    async with _NullSessionLocal() as session:
        session.add(
            User(
                id=uid,
                email=email,
                password_hash=password_hash if auth_method != AuthMethod.GOOGLE.value else None,
                auth_method=auth_method,
                full_name="Test User",
                profile_completed=profile_completed,
                profile_completion_percentage=100 if profile_completed else 0,
                email_verified=email_verified,
                email_verified_at=datetime.now(timezone.utc) if email_verified else None,
                google_id=google_id,
            )
        )
        await session.commit()
    return uid, email


async def _delete_user(uid: uuid.UUID) -> None:
    async with _NullSessionLocal() as session:
        await session.execute(delete(User).where(User.id == uid))
        await session.commit()


async def _authed_client_for_user(uid: uuid.UUID, email: str, **extra: Any) -> AsyncClient:
    from utils.auth import get_current_user, get_current_user_with_complete_profile

    now = datetime.now(timezone.utc)
    user_dict = {
        "id": str(uid),
        "_id": str(uid),
        "email": email,
        "full_name": "Test User",
        "auth_method": "local",
        "is_admin": False,
        "profile_completed": extra.get("profile_completed", False),
        "profile_completion_percentage": extra.get("profile_completion_percentage", 0),
        "has_google_linked": bool(extra.get("google_id")),
        "has_password": True,
        "created_at": now,
        "updated_at": now,
        "last_login": now,
    }

    async def _mock():
        return user_dict

    app.dependency_overrides[get_current_user] = _mock
    app.dependency_overrides[get_current_user_with_complete_profile] = _mock
    token = _make_test_jwt(str(uid), email)
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://localhost",
        headers={"Authorization": f"Bearer {token}"},
    )


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def patch_redis(fake_redis: FakeRedis):
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=fake_redis)):
        yield fake_redis


# ---------------------------------------------------------------------------
# Registration edge cases
# ---------------------------------------------------------------------------


class TestRegistrationExtended:
    @pytest.mark.asyncio
    async def test_register_auto_verified_when_disabled(self):
        with patch.object(auth_module.settings, "disable_email_verification", True):
            payload = _reg_payload("_autoverify")
            async with _make_client() as client:
                resp = await client.post(f"{BASE}/register", json=payload)
        assert resp.status_code == 200, resp.text
        assert resp.json()["user"]["email_verified"] is True

    @pytest.mark.asyncio
    async def test_register_concurrent_integrity_error_returns_422(self):
        payload = _reg_payload("_race")
        with patch(
            "api.auth._SQLIntegrityError",
            auth_module._SQLIntegrityError,
        ), patch.object(
            auth_module.AsyncSession,
            "commit",
            AsyncMock(side_effect=auth_module._SQLIntegrityError("", "", "")),
        ):
            async with _make_client() as client:
                resp = await client.post(f"{BASE}/register", json=payload)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Login / lockout
# ---------------------------------------------------------------------------


class TestLoginExtended:
    @pytest.mark.asyncio
    async def test_login_success_verified_user(self):
        uid, email = await _create_user(email_verified=True)
        try:
            async with _make_client() as client:
                resp = await client.post(
                    f"{BASE}/login",
                    json={"email": email, "password": "SecurePass123!"},
                )
            assert resp.status_code == 200, resp.text
            assert "access_token" in resp.json()
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_login_account_locked_returns_423(self):
        uid, email = await _create_user(email_verified=True)
        try:
            with patch(
                "api.auth.check_account_lockout",
                AsyncMock(return_value=(True, 600)),
            ):
                async with _make_client() as client:
                    resp = await client.post(
                        f"{BASE}/login",
                        json={"email": email, "password": "SecurePass123!"},
                    )
            assert resp.status_code == 423
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_login_remember_me_extends_expiry(self):
        uid, email = await _create_user(email_verified=True)
        try:
            async with _make_client() as client:
                resp = await client.post(
                    f"{BASE}/login",
                    json={"email": email, "password": "SecurePass123!", "remember_me": True},
                )
            assert resp.status_code == 200
            sec = get_security_settings()
            token = resp.json()["access_token"]
            payload = jwt.decode(
                token,
                sec.jwt_config["secret_key"],
                algorithms=[sec.jwt_config["algorithm"]],
            )
            hours = (payload["exp"] - payload["iat"]) / 3600
            assert hours > sec.jwt_config["expire_hours"]
        finally:
            await _delete_user(uid)


# ---------------------------------------------------------------------------
# Logout / refresh
# ---------------------------------------------------------------------------


class TestLogoutRefresh:
    @pytest.mark.asyncio
    async def test_logout_revokes_token_jti(self, patch_redis):
        uid, email = await _create_user()
        token = _make_jwt({"sub": str(uid), "email": email}, expire_hours=24)
        try:
            with patch("utils.auth.revoke_token", AsyncMock(return_value=True)) as mock_revoke:
                async with _make_client() as client:
                    resp = await client.post(
                        f"{BASE}/logout",
                        headers={"Authorization": f"Bearer {token}"},
                    )
            assert resp.status_code == 200
            mock_revoke.assert_awaited_once()
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_refresh_returns_new_token(self):
        uid, email = await _create_user()
        client = await _authed_client_for_user(uid, email)
        try:
            with patch("api.auth.revoke_token", AsyncMock(return_value=True)):
                resp = await client.post(f"{BASE}/refresh")
            assert resp.status_code == 200, resp.text
            assert "access_token" in resp.json()
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_refresh_rate_limited_returns_429(self):
        uid, email = await _create_user()
        client = await _authed_client_for_user(uid, email)
        try:
            with patch("api.auth.check_rate_limit", AsyncMock(return_value=(False, 0))):
                resp = await client.post(f"{BASE}/refresh")
            assert resp.status_code == 429
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_verify_valid_token(self):
        uid, email = await _create_user()
        client = await _authed_client_for_user(uid, email)
        try:
            resp = await client.get(f"{BASE}/verify")
            assert resp.status_code == 200
            assert resp.json()["success"] is True
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user(uid)


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------


class TestVerifyCode:
    @pytest.mark.asyncio
    async def test_verify_code_success(self, patch_redis):
        uid, email = await _create_user(email_verified=False)
        code = "123456"
        patch_redis._store[f"email_verification:{code}"] = email
        try:
            with patch.object(auth_module.settings, "disable_email_verification", False):
                async with _make_client() as client:
                    resp = await client.post(
                        f"{BASE}/verify-code",
                        json={"email": email, "code": code},
                    )
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["email_verified"] is True
            assert "access_token" in data
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_verify_code_invalid_returns_422(self, patch_redis):
        uid, email = await _create_user(email_verified=False)
        try:
            async with _make_client() as client:
                resp = await client.post(
                    f"{BASE}/verify-code",
                    json={"email": email, "code": "999999"},
                )
            assert resp.status_code == 422
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_verify_code_already_verified(self):
        uid, email = await _create_user(email_verified=True)
        try:
            async with _make_client() as client:
                resp = await client.post(
                    f"{BASE}/verify-code",
                    json={"email": email, "code": "123456"},
                )
            assert resp.status_code == 200
            assert resp.json()["email_verified"] is True
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_verify_code_lockout_returns_423(self):
        uid, email = await _create_user(email_verified=False)
        try:
            with patch(
                "api.auth.check_account_lockout",
                AsyncMock(return_value=(True, 300)),
            ):
                async with _make_client() as client:
                    resp = await client.post(
                        f"{BASE}/verify-code",
                        json={"email": email, "code": "123456"},
                    )
            assert resp.status_code == 423
        finally:
            await _delete_user(uid)


class TestResendVerification:
    @pytest.mark.asyncio
    async def test_resend_verification_generic_response(self):
        async with _make_client() as client:
            resp = await client.post(
                f"{BASE}/resend-verification",
                json={"email": "nobody_resend@example.com"},
            )
        assert resp.status_code == 200
        assert "message" in resp.json()

    @pytest.mark.asyncio
    async def test_resend_verification_existing_unverified_user(self):
        uid, email = await _create_user(email_verified=False)
        try:
            with patch("api.auth._send_verification_email", AsyncMock(return_value=True)):
                async with _make_client() as client:
                    resp = await client.post(
                        f"{BASE}/resend-verification",
                        json={"email": email},
                    )
            assert resp.status_code == 200
        finally:
            await _delete_user(uid)


class TestVerifyEmailToken:
    @pytest.mark.asyncio
    async def test_verify_email_token_success(self, patch_redis):
        uid, email = await _create_user(email_verified=False)
        token = "verify-token-abc"
        patch_redis._store[f"email_verification:{token}"] = email
        try:
            async with _make_client() as client:
                resp = await client.get(f"{BASE}/verify-email", params={"token": token})
            assert resp.status_code == 200
            assert resp.json()["email_verified"] is True
        finally:
            await _delete_user(uid)


class TestVerificationStatus:
    @pytest.mark.asyncio
    async def test_verification_status_returns_fields(self):
        uid, email = await _create_user(email_verified=True)
        client = await _authed_client_for_user(uid, email)
        try:
            resp = await client.get(f"{BASE}/verification-status")
            assert resp.status_code == 200
            body = resp.json()
            assert body["email"] == email
            assert body["email_verified"] is True
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user(uid)


# ---------------------------------------------------------------------------
# Password reset / change
# ---------------------------------------------------------------------------


class TestPasswordFlows:
    @pytest.mark.asyncio
    async def test_forgot_password_existing_user_stores_token(self, patch_redis):
        uid, email = await _create_user()
        try:
            with patch("utils.email_service.get_email_service") as mock_svc:
                svc = MagicMock()
                svc.is_configured.return_value = True
                svc.send_password_reset_email = AsyncMock(return_value=True)
                mock_svc.return_value = svc
                async with _make_client() as client:
                    resp = await client.post(f"{BASE}/forgot-password", json={"email": email})
            assert resp.status_code == 200
            assert any(k.startswith("password_reset:") for k in patch_redis._store)
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_reset_password_success(self, patch_redis):
        uid, email = await _create_user()
        reset_token = "reset-token-xyz"
        patch_redis._store[f"password_reset:{reset_token}"] = email
        try:
            async with _make_client() as client:
                resp = await client.post(
                    f"{BASE}/reset-password",
                    json={
                        "token": reset_token,
                        "new_password": "NewSecure99!",
                        "confirm_password": "NewSecure99!",
                    },
                )
            assert resp.status_code == 200, resp.text
            async with _make_client() as client:
                login = await client.post(
                    f"{BASE}/login",
                    json={"email": email, "password": "NewSecure99!"},
                )
            assert login.status_code == 200
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_reset_password_invalid_token_returns_422(self, patch_redis):
        async with _make_client() as client:
            resp = await client.post(
                f"{BASE}/reset-password",
                json={
                    "token": "bad-token",
                    "new_password": "NewSecure99!",
                    "confirm_password": "NewSecure99!",
                },
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_reset_password_lockout_returns_423(self, patch_redis):
        uid, email = await _create_user()
        reset_token = "locked-reset"
        patch_redis._store[f"password_reset:{reset_token}"] = email
        try:
            with patch(
                "api.auth.check_account_lockout",
                AsyncMock(return_value=(True, 900)),
            ):
                async with _make_client() as client:
                    resp = await client.post(
                        f"{BASE}/reset-password",
                        json={
                            "token": reset_token,
                            "new_password": "NewSecure99!",
                            "confirm_password": "NewSecure99!",
                        },
                    )
            assert resp.status_code == 423
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_change_password_success(self):
        uid, email = await _create_user()
        client = await _authed_client_for_user(uid, email)
        try:
            with patch("api.auth.invalidate_all_user_tokens", AsyncMock(return_value=True)):
                resp = await client.put(
                    f"{BASE}/change-password",
                    json={
                        "current_password": "SecurePass123!",
                        "new_password": "ChangedPass99!",
                        "confirm_password": "ChangedPass99!",
                    },
                )
            assert resp.status_code == 200, resp.text
            assert "access_token" in resp.json()
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_change_password_wrong_current_returns_422(self):
        uid, email = await _create_user()
        client = await _authed_client_for_user(uid, email)
        try:
            resp = await client.put(
                f"{BASE}/change-password",
                json={
                    "current_password": "WrongPass99!",
                    "new_password": "ChangedPass99!",
                    "confirm_password": "ChangedPass99!",
                },
            )
            assert resp.status_code == 422
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user(uid)


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------


class TestOAuth:
    @pytest.mark.asyncio
    async def test_oauth_status_returns_flag(self):
        async with _make_client() as client:
            resp = await client.get(f"{BASE}/oauth/status")
        assert resp.status_code == 200
        assert "google_oauth_enabled" in resp.json()

    @pytest.mark.asyncio
    async def test_google_login_redirect_when_configured(self, patch_redis):
        mock_settings = MagicMock(
            is_google_oauth_configured=True,
            google_client_id="test-client-id.apps.googleusercontent.com",
            google_client_secret="secret",
        )
        with patch.object(auth_module, "settings", mock_settings):
            async with _make_client() as client:
                resp = await client.get(
                    f"{BASE}/google",
                    params={"redirect_url": "/dashboard"},
                    follow_redirects=False,
                )
        assert resp.status_code == 302
        assert "accounts.google.com" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_google_login_rejects_open_redirect(self, patch_redis):
        mock_settings = MagicMock(
            is_google_oauth_configured=True,
            google_client_id="test-client-id.apps.googleusercontent.com",
            google_client_secret="secret",
        )
        with patch.object(auth_module, "settings", mock_settings):
            async with _make_client() as client:
                resp = await client.get(
                    f"{BASE}/google",
                    params={"redirect_url": "https://evil.com"},
                    follow_redirects=False,
                )
        assert resp.status_code == 302
        assert "accounts.google.com" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_oauth_callback_new_user_success(self, patch_redis):
        state = "oauth-state-token"
        patch_redis._store[f"oauth_state:{state}"] = json.dumps({"redirect": "/dashboard"})

        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"access_token": "google-access-token"}
        userinfo_resp = MagicMock(status_code=200)
        userinfo_resp.json.return_value = {
            "id": "google-123",
            "email": f"oauth_{uuid.uuid4().hex[:8]}@example.com",
            "name": "OAuth User",
        }

        mock_settings = MagicMock(
            is_google_oauth_configured=True,
            google_client_id="cid",
            google_client_secret="secret",
        )

        async def _mock_post(*_a, **_k):
            return token_resp

        async def _mock_get(*_a, **_k):
            return userinfo_resp

        mock_client = AsyncMock()
        mock_client.post = _mock_post
        mock_client.get = _mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(auth_module, "settings", mock_settings), patch(
            "api.auth.httpx.AsyncClient", return_value=mock_client
        ), patch("utils.email_service.get_email_service") as mock_email:
            svc = MagicMock()
            svc.is_configured.return_value = False
            mock_email.return_value = svc
            async with _make_client() as client:
                resp = await client.get(
                    f"{BASE}/google/callback",
                    params={"code": "auth-code", "state": state},
                    follow_redirects=False,
                )
        assert resp.status_code == 302
        assert "code=" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_oauth_callback_invalid_state(self, patch_redis):
        mock_settings = MagicMock(is_google_oauth_configured=True)
        with patch.object(auth_module, "settings", mock_settings):
            async with _make_client() as client:
                resp = await client.get(
                    f"{BASE}/google/callback",
                    params={"code": "auth-code", "state": "missing-state"},
                    follow_redirects=False,
                )
        assert resp.status_code == 302
        assert "invalid_state" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_exchange_code_success(self, patch_redis):
        code = "exchange-code-abc"
        jwt_token = _make_jwt({"sub": str(uuid.uuid4()), "email": "x@y.com"}, expire_hours=24)
        patch_redis._store[f"oauth_code:{code}"] = jwt_token
        async with _make_client() as client:
            resp = await client.post(f"{BASE}/oauth/exchange-code", json={"code": code})
        assert resp.status_code == 200
        assert resp.json()["access_token"] == jwt_token

    @pytest.mark.asyncio
    async def test_exchange_code_invalid_returns_422(self, patch_redis):
        async with _make_client() as client:
            resp = await client.post(
                f"{BASE}/oauth/exchange-code",
                json={"code": "does-not-exist"},
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_google_link_returns_oauth_url(self, patch_redis):
        uid, email = await _create_user()
        client = await _authed_client_for_user(uid, email)
        mock_settings = MagicMock(
            is_google_oauth_configured=True,
            google_client_id="cid",
            google_client_secret="secret",
        )
        try:
            with patch.object(auth_module, "settings", mock_settings):
                resp = await client.post(f"{BASE}/google/link")
            assert resp.status_code == 200
            assert "oauth_url" in resp.json()
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_google_unlink_requires_password(self):
        uid, email = await _create_user(auth_method=AuthMethod.GOOGLE.value, google_id="g-1")
        client = await _authed_client_for_user(uid, email, google_id="g-1")
        try:
            async with _NullSessionLocal() as session:
                await session.execute(
                    update(User).where(User.id == uid).values(password_hash=None)
                )
                await session.commit()
            resp = await client.delete(f"{BASE}/google/unlink")
            assert resp.status_code == 422
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user(uid)


# ---------------------------------------------------------------------------
# Misc authenticated endpoints
# ---------------------------------------------------------------------------


class TestMiscAuthEndpoints:
    @pytest.mark.asyncio
    async def test_extension_status(self):
        uid, email = await _create_user(profile_completed=True)
        client = await _authed_client_for_user(uid, email, profile_completed=True)
        try:
            resp = await client.get(f"{BASE}/extension-status")
            assert resp.status_code == 200
            assert resp.json()["authenticated"] is True
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_email_status(self):
        async with _make_client() as client:
            resp = await client.get(f"{BASE}/email-status")
        assert resp.status_code == 200
        assert "email_configured" in resp.json()
