"""
Targeted coverage tests for api/auth.py — validators, helpers, error paths, OAuth branches.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, select, update

import api.auth as auth_module
from api.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    PasswordChangeRequest,
    ResendVerificationRequest,
    VerifyCodeRequest,
    _bcrypt_safe,
    _consume_reset_token,
    _consume_verification_token,
    _make_jwt,
    _send_verification_email,
    _store_reset_token,
    _store_verification_token,
    _validate_email,
    _validate_password_confirmation,
    _validate_password_strength,
    change_password,
    exchange_oauth_code,
    forgot_password,
    get_email_service_status,
    get_verification_status,
    google_callback,
    google_login,
    link_google_account,
    login_user,
    logout_user,
    refresh_token,
    register_user,
    resend_verification_email,
    reset_password,
    unlink_google_account,
    verify_email,
    verify_email_code,
    pwd_context,
)
from models.database import AuthMethod, User
from tests.test_api.conftest import _NullSessionLocal
from tests.test_api.test_auth_extended import (
    FakeRedis,
    _create_user,
    _delete_user,
    _reg_payload,
)

BASE = "/api/v1/auth"


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def patch_redis(fake_redis: FakeRedis):
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=fake_redis)):
        yield fake_redis


def _mock_request(host: str = "127.0.0.1") -> MagicMock:
    req = MagicMock()
    req.client.host = host
    req.url_for.return_value = "http://localhost/api/v1/auth/google/callback"
    return req


# ---------------------------------------------------------------------------
# Validation helpers and models
# ---------------------------------------------------------------------------


class TestValidationHelpers:
    def test_validate_email_empty(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            _validate_email("")

    def test_validate_email_too_long(self):
        with pytest.raises(ValueError, match="cannot exceed"):
            _validate_email("a" * 250 + "@x.com")

    def test_validate_email_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid email format"):
            _validate_email("not-an-email")

    def test_validate_password_empty(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            _validate_password_strength("")

    def test_validate_password_too_short(self):
        with pytest.raises(ValueError, match="at least"):
            _validate_password_strength("Ab1!")

    def test_validate_password_too_long(self):
        with pytest.raises(ValueError, match="cannot exceed"):
            _validate_password_strength("Aa1!" * 40)

    def test_validate_password_missing_requirements(self):
        with pytest.raises(ValueError, match="uppercase letter"):
            _validate_password_strength("lowercase1!")
        with pytest.raises(ValueError, match="lowercase letter"):
            _validate_password_strength("UPPERCASE1!")
        with pytest.raises(ValueError, match="digit"):
            _validate_password_strength("NoDigits!!")
        with pytest.raises(ValueError, match="special character"):
            _validate_password_strength("NoSpecial1")

    def test_validate_password_confirmation_empty(self):
        with pytest.raises(ValueError, match="confirmation cannot be empty"):
            _validate_password_confirmation("Password1!", "")

    def test_validate_password_confirmation_mismatch(self):
        with pytest.raises(ValueError, match="do not match"):
            _validate_password_confirmation("Password1!", "Password2!")

    def test_bcrypt_safe_truncates_long_password(self):
        long_pw = "x" * 100
        result = _bcrypt_safe(long_pw)
        assert len(result.encode("utf-8")) <= 72

    def test_register_request_full_name_validators(self):
        with pytest.raises(ValidationError):
            RegisterRequest(
                full_name="",
                email="ok@example.com",
                password="SecurePass123!",
                confirm_password="SecurePass123!",
            )
        with pytest.raises(ValidationError):
            RegisterRequest(
                full_name="A",
                email="ok@example.com",
                password="SecurePass123!",
                confirm_password="SecurePass123!",
            )
        with pytest.raises(ValidationError):
            RegisterRequest(
                full_name="A" * 101,
                email="ok@example.com",
                password="SecurePass123!",
                confirm_password="SecurePass123!",
            )
        with pytest.raises(ValidationError):
            RegisterRequest(
                full_name="Bad123",
                email="ok@example.com",
                password="SecurePass123!",
                confirm_password="SecurePass123!",
            )

    def test_login_request_empty_password(self):
        with pytest.raises(ValidationError):
            LoginRequest(email="ok@example.com", password="   ")


# ---------------------------------------------------------------------------
# Redis helper functions
# ---------------------------------------------------------------------------


class TestRedisHelpers:
    @pytest.mark.asyncio
    async def test_store_reset_token_success(self, patch_redis):
        assert await _store_reset_token("u@example.com", "tok123") is True

    @pytest.mark.asyncio
    async def test_store_reset_token_no_redis(self):
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)):
            assert await _store_reset_token("u@example.com", "tok123") is False

    @pytest.mark.asyncio
    async def test_store_reset_token_exception(self):
        with patch(
            "utils.redis_client.get_redis_client",
            AsyncMock(side_effect=RuntimeError("redis down")),
        ):
            assert await _store_reset_token("u@example.com", "tok123") is False

    @pytest.mark.asyncio
    async def test_consume_reset_token_paths(self, patch_redis):
        patch_redis._store["password_reset:tok"] = "u@example.com"
        assert await _consume_reset_token("tok") == "u@example.com"
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)):
            assert await _consume_reset_token("missing") is None
        with patch(
            "utils.redis_client.get_redis_client",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            assert await _consume_reset_token("tok") is None

    @pytest.mark.asyncio
    async def test_store_verification_token_with_old_code(self, patch_redis):
        email = "verify@example.com"
        patch_redis._store[f"email_verification_user:{email}"] = "111111"
        patch_redis._store["email_verification:111111"] = email
        assert await _store_verification_token(email, "222222") is True
        assert "email_verification:111111" not in patch_redis._store

    @pytest.mark.asyncio
    async def test_store_verification_token_no_redis(self):
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)):
            assert await _store_verification_token("a@b.com", "123456") is False

    @pytest.mark.asyncio
    async def test_store_verification_token_exception(self):
        with patch(
            "utils.redis_client.get_redis_client",
            AsyncMock(side_effect=RuntimeError("redis")),
        ):
            assert await _store_verification_token("a@b.com", "123456") is False

    @pytest.mark.asyncio
    async def test_consume_verification_token_cleanup_and_errors(self, patch_redis):
        patch_redis._store["email_verification:654321"] = "user@example.com"
        patch_redis._store["email_verification_user:user@example.com"] = "654321"
        assert await _consume_verification_token("654321") == "user@example.com"

        patch_redis._store["email_verification:111111"] = "x@y.com"

        async def _delete_fail(_key):
            raise RuntimeError("delete failed")

        patch_redis.delete = _delete_fail  # type: ignore[method-assign]
        assert await _consume_verification_token("111111") == "x@y.com"

        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)):
            assert await _consume_verification_token("nope") is None
        with patch(
            "utils.redis_client.get_redis_client",
            AsyncMock(side_effect=RuntimeError("err")),
        ):
            assert await _consume_verification_token("nope") is None

    @pytest.mark.asyncio
    async def test_send_verification_email_paths(self, patch_redis):
        with patch("utils.email_service.get_email_service") as mock_svc:
            svc = MagicMock()
            svc.is_configured.return_value = True
            svc.send_verification_code_email = AsyncMock(return_value=True)
            mock_svc.return_value = svc
            assert await _send_verification_email("a@b.com", "User") is True

        with patch("utils.email_service.get_email_service") as mock_svc:
            svc = MagicMock()
            svc.is_configured.return_value = True
            svc.send_verification_code_email = AsyncMock(return_value=False)
            mock_svc.return_value = svc
            assert await _send_verification_email("a@b.com") is False

        with patch("utils.email_service.get_email_service") as mock_svc, patch.object(
            auth_module.settings, "debug", True
        ):
            svc = MagicMock()
            svc.is_configured.return_value = False
            mock_svc.return_value = svc
            assert await _send_verification_email("a@b.com") is False

        with patch(
            "api.auth._store_verification_token",
            AsyncMock(return_value=False),
        ):
            assert await _send_verification_email("a@b.com") is False

        with patch(
            "api.auth._store_verification_token",
            AsyncMock(return_value=True),
        ), patch(
            "utils.email_service.get_email_service",
            side_effect=RuntimeError("smtp"),
        ):
            assert await _send_verification_email("a@b.com") is False


# ---------------------------------------------------------------------------
# Registration / login direct handler tests
# ---------------------------------------------------------------------------


class TestRegisterLoginHandlers:
    @pytest.mark.asyncio
    async def test_register_user_success_with_verification_email(self):
        payload = _reg_payload("_covreg")
        req = RegisterRequest(**payload)
        request = _mock_request()
        async with _NullSessionLocal() as db:
            with patch.object(auth_module.settings, "disable_email_verification", False), patch(
                "api.auth._send_verification_email", AsyncMock(return_value=True)
            ) as mock_send:
                result = await register_user(request, req, db)
        assert result.access_token
        mock_send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_register_user_duplicate_email(self):
        uid, email = await _create_user()
        try:
            req = RegisterRequest(
                email=email,
                password="SecurePass123!",
                confirm_password="SecurePass123!",
                full_name="Dup User",
            )
            async with _NullSessionLocal() as db:
                with pytest.raises(Exception) as exc:
                    await register_user(_mock_request(), req, db)
            assert exc.value.status_code in (400, 422)
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_register_user_email_send_failure_still_succeeds(self):
        payload = _reg_payload("_emlfail")
        req = RegisterRequest(**payload)
        async with _NullSessionLocal() as db:
            with patch.object(auth_module.settings, "disable_email_verification", False), patch(
                "api.auth._send_verification_email",
                AsyncMock(side_effect=RuntimeError("smtp")),
            ):
                result = await register_user(_mock_request(), req, db)
        assert result.access_token

    @pytest.mark.asyncio
    async def test_register_user_internal_error(self):
        payload = _reg_payload("_regerr")
        req = RegisterRequest(**payload)
        async with _NullSessionLocal() as db:
            with patch.object(db, "execute", AsyncMock(side_effect=RuntimeError("db"))):
                with pytest.raises(Exception) as exc:
                    await register_user(_mock_request(), req, db)
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_login_user_not_found(self):
        with patch("api.auth.record_failed_login", AsyncMock(return_value=(1, False))):
            with pytest.raises(Exception) as exc:
                await login_user(
                    _mock_request(),
                    LoginRequest(email="missing@example.com", password="SecurePass123!"),
                    _NullSessionLocal(),
                )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_login_wrong_password_then_lockout(self):
        uid, email = await _create_user()
        try:
            with patch(
                "api.auth.record_failed_login",
                AsyncMock(return_value=(5, True)),
            ):
                with pytest.raises(Exception) as exc:
                    await login_user(
                        _mock_request(),
                        LoginRequest(email=email, password="WrongPass99!"),
                        _NullSessionLocal(),
                    )
            assert exc.value.status_code == 423
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_login_wrong_password_remaining_attempts(self):
        uid, email = await _create_user()
        try:
            with patch(
                "api.auth.record_failed_login",
                AsyncMock(return_value=(2, False)),
            ):
                with pytest.raises(Exception) as exc:
                    await login_user(
                        _mock_request(),
                        LoginRequest(email=email, password="WrongPass99!"),
                        _NullSessionLocal(),
                    )
            assert exc.value.status_code == 401
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_login_unverified_resend_failure(self):
        uid, email = await _create_user(email_verified=False)
        try:
            async with _NullSessionLocal() as db:
                with patch.object(auth_module.settings, "disable_email_verification", False), patch(
                    "api.auth._send_verification_email",
                    AsyncMock(side_effect=RuntimeError("smtp")),
                ), patch("api.auth.check_account_lockout", AsyncMock(return_value=(False, 0))):
                    with pytest.raises(Exception) as exc:
                        await login_user(
                            _mock_request(),
                            LoginRequest(email=email, password="SecurePass123!"),
                            db,
                        )
            assert exc.value.status_code == 403
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_login_jwt_encoding_error(self):
        uid, email = await _create_user(email_verified=True)
        try:
            async with _NullSessionLocal() as db:
                with patch("api.auth._make_jwt", side_effect=RuntimeError("jwt")), patch(
                    "api.auth.check_account_lockout", AsyncMock(return_value=(False, 0))
                ), patch("api.auth.clear_login_attempts", AsyncMock()):
                    with pytest.raises(Exception) as exc:
                        await login_user(
                            _mock_request(),
                            LoginRequest(email=email, password="SecurePass123!"),
                            db,
                        )
            assert exc.value.status_code == 500
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_login_general_exception(self):
        async with _NullSessionLocal() as db:
            with patch.object(db, "execute", AsyncMock(side_effect=RuntimeError("db"))):
                with pytest.raises(Exception) as exc:
                    await login_user(
                        _mock_request(),
                        LoginRequest(email="a@b.com", password="SecurePass123!"),
                        db,
                    )
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_login_empty_credentials_guard(self):
        req = LoginRequest(email="ok@example.com", password="SecurePass123!")
        req.email = ""
        with pytest.raises(Exception) as exc:
            await login_user(_mock_request(), req, _NullSessionLocal())
        assert exc.value.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Logout / refresh
# ---------------------------------------------------------------------------


class TestLogoutRefreshHandlers:
    @pytest.mark.asyncio
    async def test_logout_revoke_failure_warning(self):
        token = _make_jwt({"sub": "u", "email": "a@b.com"}, expire_hours=1)
        request = MagicMock()
        with patch("utils.auth.extract_token_from_request", return_value=token), patch(
            "utils.auth.revoke_token", AsyncMock(return_value=False)
        ):
            result = await logout_user(request)
        assert result["message"]

    @pytest.mark.asyncio
    async def test_refresh_missing_user_id(self):
        with pytest.raises(Exception) as exc:
            await refresh_token(MagicMock(), {})
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_revoke_old_token_failure(self):
        current = {"id": str(uuid.uuid4()), "email": "a@b.com"}
        with patch("utils.auth.extract_token_from_request", return_value="tok"), patch(
            "utils.auth.revoke_token", AsyncMock(return_value=False)
        ):
            result = await refresh_token(MagicMock(), current)
        assert result.access_token

    @pytest.mark.asyncio
    async def test_refresh_internal_error(self):
        current = {"id": str(uuid.uuid4()), "email": "a@b.com"}
        with patch("api.auth._make_jwt", side_effect=RuntimeError("jwt")):
            with pytest.raises(Exception) as exc:
                await refresh_token(MagicMock(), current)
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------


def _oauth_mock_settings(configured: bool = True) -> MagicMock:
    return MagicMock(
        is_google_oauth_configured=configured,
        google_client_id="cid.apps.googleusercontent.com",
        google_client_secret="secret",
    )


def _oauth_http_mocks(
    token_status: int = 200,
    token_body: Optional[dict] = None,
    userinfo_status: int = 200,
    userinfo_body: Optional[dict] = None,
):
    token_resp = MagicMock(status_code=token_status)
    token_resp.json.return_value = {"access_token": "g-token"} if token_body is None else token_body
    userinfo_resp = MagicMock(status_code=userinfo_status)
    userinfo_resp.json.return_value = (
        {"id": "gid-1", "email": f"oauth_{uuid.uuid4().hex[:8]}@example.com", "name": "OAuth"}
        if userinfo_body is None
        else userinfo_body
    )

    async def _post(*_a, **_k):
        return token_resp

    async def _get(*_a, **_k):
        return userinfo_resp

    mock_client = AsyncMock()
    mock_client.post = _post
    mock_client.get = _get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


class TestOAuthCoverage:
    @pytest.mark.asyncio
    async def test_google_login_not_configured(self):
        with patch.object(auth_module, "settings", _oauth_mock_settings(False)):
            with pytest.raises(Exception) as exc:
                await google_login(_mock_request(), None)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_google_login_redis_store_failure(self):
        with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
            "utils.redis_client.get_redis_client",
            AsyncMock(side_effect=RuntimeError("redis")),
        ):
            with pytest.raises(Exception) as exc:
                await google_login(_mock_request(), "/dashboard")
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_google_login_redis_unavailable(self):
        with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
            "utils.redis_client.get_redis_client", AsyncMock(return_value=None)
        ):
            with pytest.raises(Exception) as exc:
                await google_login(_mock_request(), None)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_google_callback_error_param(self):
        resp = await google_callback(
            _mock_request(), code="x", state="y", error="access_denied", db=_NullSessionLocal()
        )
        assert "oauth_failed" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_google_callback_not_configured(self):
        with patch.object(auth_module, "settings", _oauth_mock_settings(False)):
            resp = await google_callback(
                _mock_request(), code="x", state="y", error=None, db=_NullSessionLocal()
            )
        assert "oauth_not_configured" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_google_callback_redis_unavailable(self, patch_redis):
        with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
            "utils.redis_client.get_redis_client", AsyncMock(return_value=None)
        ):
            resp = await google_callback(
                _mock_request(), code="c", state="s", error=None, db=_NullSessionLocal()
            )
        assert "service_unavailable" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_google_callback_bad_redirect_in_state(self, patch_redis):
        state = "st-bad-redir"
        patch_redis._store[f"oauth_state:{state}"] = json.dumps({"redirect": "//evil.com"})
        with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
            "api.auth.httpx.AsyncClient", return_value=_oauth_http_mocks()
        ), patch("utils.email_service.get_email_service") as mock_email:
            mock_email.return_value.is_configured.return_value = False
            resp = await google_callback(
                _mock_request(), code="c", state=state, error=None, db=_NullSessionLocal()
            )
        assert resp.status_code == 302

    @pytest.mark.asyncio
    async def test_google_callback_state_verification_exception(self, patch_redis):
        state = "st-exc"
        patch_redis._store[f"oauth_state:{state}"] = "not-json"
        with patch.object(auth_module, "settings", _oauth_mock_settings(True)):
            resp = await google_callback(
                _mock_request(), code="c", state=state, error=None, db=_NullSessionLocal()
            )
        assert "service_unavailable" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_google_callback_token_exchange_failed(self, patch_redis):
        state = "st-tok"
        patch_redis._store[f"oauth_state:{state}"] = json.dumps({"redirect": "/dashboard"})
        with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
            "api.auth.httpx.AsyncClient",
            return_value=_oauth_http_mocks(token_status=400),
        ):
            resp = await google_callback(
                _mock_request(), code="c", state=state, error=None, db=_NullSessionLocal()
            )
        assert "token_exchange_failed" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_google_callback_no_access_token(self, patch_redis):
        state = "st-noat"
        patch_redis._store[f"oauth_state:{state}"] = json.dumps({"redirect": "/dashboard"})
        with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
            "api.auth.httpx.AsyncClient",
            return_value=_oauth_http_mocks(token_body={}),
        ):
            resp = await google_callback(
                _mock_request(), code="c", state=state, error=None, db=_NullSessionLocal()
            )
        assert "no_access_token" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_google_callback_userinfo_failed(self, patch_redis):
        state = "st-ui"
        patch_redis._store[f"oauth_state:{state}"] = json.dumps({"redirect": "/dashboard"})
        with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
            "api.auth.httpx.AsyncClient",
            return_value=_oauth_http_mocks(userinfo_status=500),
        ):
            resp = await google_callback(
                _mock_request(), code="c", state=state, error=None, db=_NullSessionLocal()
            )
        assert "userinfo_failed" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_google_callback_missing_user_info(self, patch_redis):
        state = "st-miss"
        patch_redis._store[f"oauth_state:{state}"] = json.dumps({"redirect": "/dashboard"})
        with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
            "api.auth.httpx.AsyncClient",
            return_value=_oauth_http_mocks(userinfo_body={"email": ""}),
        ):
            resp = await google_callback(
                _mock_request(), code="c", state=state, error=None, db=_NullSessionLocal()
            )
        assert "missing_user_info" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_google_callback_existing_google_user(self, patch_redis):
        gid = f"google-{uuid.uuid4().hex[:8]}"
        uid, email = await _create_user(auth_method=AuthMethod.GOOGLE.value, google_id=gid)
        state = "st-existing"
        patch_redis._store[f"oauth_state:{state}"] = json.dumps({"redirect": "/dashboard"})
        try:
            with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
                "api.auth.httpx.AsyncClient",
                return_value=_oauth_http_mocks(
                    userinfo_body={"id": gid, "email": email, "name": "OAuth User"}
                ),
            ), patch("api.auth.check_account_lockout", AsyncMock(return_value=(False, 0))):
                async with _NullSessionLocal() as db:
                    resp = await google_callback(
                        _mock_request(), code="c", state=state, error=None, db=db
                    )
            assert "code=" in resp.headers["location"]
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_google_callback_local_email_requires_link(self, patch_redis):
        uid, email = await _create_user(auth_method=AuthMethod.LOCAL.value)
        state = "st-linkreq"
        patch_redis._store[f"oauth_state:{state}"] = json.dumps({"redirect": "/dashboard"})
        try:
            with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
                "api.auth.httpx.AsyncClient",
                return_value=_oauth_http_mocks(
                    userinfo_body={"id": "new-gid", "email": email, "name": "OAuth User"}
                ),
            ):
                async with _NullSessionLocal() as db:
                    resp = await google_callback(
                        _mock_request(), code="c", state=state, error=None, db=db
                    )
            assert "google_link_required" in resp.headers["location"]
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_google_callback_locked_account(self, patch_redis):
        gid = f"google-{uuid.uuid4().hex[:8]}"
        uid, email = await _create_user(
            auth_method=AuthMethod.GOOGLE.value, google_id=gid, email_verified=True
        )
        state = "st-locked"
        patch_redis._store[f"oauth_state:{state}"] = json.dumps({"redirect": "/dashboard"})
        try:
            with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
                "api.auth.httpx.AsyncClient",
                return_value=_oauth_http_mocks(
                    userinfo_body={"id": gid, "email": email, "name": "OAuth User"}
                ),
            ), patch("api.auth.check_account_lockout", AsyncMock(return_value=(True, 600))):
                async with _NullSessionLocal() as db:
                    resp = await google_callback(
                        _mock_request(), code="c", state=state, error=None, db=db
                    )
            assert "account_locked" in resp.headers["location"]
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_google_callback_link_user_flow(self, patch_redis):
        uid, email = await _create_user()
        state = "st-link"
        patch_redis._store[f"oauth_state:{state}"] = json.dumps(
            {"redirect": "/dashboard/settings", "link_user_id": str(uid)}
        )
        gid = f"link-gid-{uuid.uuid4().hex[:8]}"
        try:
            with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
                "api.auth.httpx.AsyncClient",
                return_value=_oauth_http_mocks(
                    userinfo_body={"id": gid, "email": email, "name": "Linker"}
                ),
            ):
                async with _NullSessionLocal() as db:
                    resp = await google_callback(
                        _mock_request(), code="c", state=state, error=None, db=db
                    )
            assert "code=" in resp.headers["location"]
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_google_callback_link_user_not_found(self, patch_redis):
        state = "st-link-miss"
        patch_redis._store[f"oauth_state:{state}"] = json.dumps(
            {"redirect": "/dashboard/settings", "link_user_id": str(uuid.uuid4())}
        )
        with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
            "api.auth.httpx.AsyncClient",
            return_value=_oauth_http_mocks(userinfo_body={"id": "g1", "email": "x@y.com", "name": "X"}),
        ):
            async with _NullSessionLocal() as db:
                resp = await google_callback(
                    _mock_request(), code="c", state=state, error=None, db=db
                )
        assert "link_user_not_found" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_google_callback_link_conflict_other_user(self, patch_redis):
        uid1, email1 = await _create_user(google_id="conflict-gid")
        uid2, email2 = await _create_user()
        state = "st-conflict"
        patch_redis._store[f"oauth_state:{state}"] = json.dumps(
            {"redirect": "/dashboard/settings", "link_user_id": str(uid2)}
        )
        try:
            with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
                "api.auth.httpx.AsyncClient",
                return_value=_oauth_http_mocks(
                    userinfo_body={"id": "conflict-gid", "email": email1, "name": "Conflict"}
                ),
            ):
                async with _NullSessionLocal() as db:
                    resp = await google_callback(
                        _mock_request(), code="c", state=state, error=None, db=db
                    )
            assert "google_already_linked_to_other" in resp.headers["location"]
        finally:
            await _delete_user(uid1)
            await _delete_user(uid2)

    @pytest.mark.asyncio
    async def test_google_callback_exchange_code_redis_down(self, patch_redis):
        state = "st-rc-down"
        patch_redis._store[f"oauth_state:{state}"] = json.dumps({"redirect": "/dashboard"})
        with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
            "api.auth.httpx.AsyncClient", return_value=_oauth_http_mocks()
        ), patch("utils.email_service.get_email_service") as mock_email, patch(
            "utils.redis_client.get_redis_client", AsyncMock(return_value=None)
        ):
            mock_email.return_value.is_configured.return_value = False
            resp = await google_callback(
                _mock_request(), code="c", state=state, error=None, db=_NullSessionLocal()
            )
        assert "service_unavailable" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_google_callback_general_exception(self, patch_redis):
        state = "st-gen"
        patch_redis._store[f"oauth_state:{state}"] = json.dumps({"redirect": "/dashboard"})
        with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
            "api.auth.httpx.AsyncClient", side_effect=RuntimeError("network")
        ):
            resp = await google_callback(
                _mock_request(), code="c", state=state, error=None, db=_NullSessionLocal()
            )
        assert "oauth_error" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_exchange_code_redis_unavailable(self):
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)):
            with pytest.raises(Exception) as exc:
                await exchange_oauth_code(auth_module.ExchangeCodeRequest(code="abc"))
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_exchange_code_internal_error(self, patch_redis):
        patch_redis.getdel = AsyncMock(side_effect=RuntimeError("redis"))  # type: ignore[method-assign]
        with pytest.raises(Exception) as exc:
            await exchange_oauth_code(auth_module.ExchangeCodeRequest(code="abc"))
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_link_google_not_configured(self):
        with patch.object(auth_module, "settings", _oauth_mock_settings(False)):
            with pytest.raises(Exception) as exc:
                await link_google_account(
                    _mock_request(), {"id": str(uuid.uuid4())}, _NullSessionLocal()
                )
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_link_google_rate_limited(self):
        uid, email = await _create_user()
        try:
            with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
                "api.auth.check_rate_limit", AsyncMock(return_value=(False, 0))
            ):
                with pytest.raises(Exception) as exc:
                    await link_google_account(
                        _mock_request(), {"id": str(uid)}, _NullSessionLocal()
                    )
            assert exc.value.status_code == 429
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_link_google_user_not_found(self):
        with patch.object(auth_module, "settings", _oauth_mock_settings(True)):
            with pytest.raises(Exception) as exc:
                await link_google_account(
                    _mock_request(), {"id": str(uuid.uuid4())}, _NullSessionLocal()
                )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_link_google_already_linked(self):
        uid, email = await _create_user(google_id="already")
        try:
            with patch.object(auth_module, "settings", _oauth_mock_settings(True)):
                with pytest.raises(Exception) as exc:
                    await link_google_account(
                        _mock_request(), {"id": str(uid)}, _NullSessionLocal()
                    )
            assert exc.value.status_code == 422
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_link_google_redis_failure(self):
        uid, email = await _create_user()
        try:
            with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
                "utils.redis_client.get_redis_client", AsyncMock(return_value=None)
            ):
                with pytest.raises(Exception) as exc:
                    await link_google_account(
                        _mock_request(), {"id": str(uid)}, _NullSessionLocal()
                    )
            assert exc.value.status_code == 503
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_unlink_google_success(self):
        uid, email = await _create_user(google_id="g-unlink")
        async with _NullSessionLocal() as db:
            await db.execute(
                update(User).where(User.id == uid).values(
                    auth_method=AuthMethod.GOOGLE.value,
                    password_hash=pwd_context.hash("SecurePass123!"),
                )
            )
            await db.commit()
            result = await unlink_google_account({"id": str(uid)}, db)
        assert "unlinked" in result["message"].lower()
        await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_unlink_google_user_not_found(self):
        with pytest.raises(Exception) as exc:
            await unlink_google_account({"id": str(uuid.uuid4())}, _NullSessionLocal())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_unlink_google_not_linked(self):
        uid, email = await _create_user()
        try:
            with pytest.raises(Exception) as exc:
                await unlink_google_account({"id": str(uid)}, _NullSessionLocal())
            assert exc.value.status_code == 422
        finally:
            await _delete_user(uid)


# ---------------------------------------------------------------------------
# Password reset / change
# ---------------------------------------------------------------------------


class TestPasswordCoverage:
    @pytest.mark.asyncio
    async def test_forgot_password_rate_limited(self):
        """Rate limit raise is caught by forgot_password's broad except — still covers line 1566."""
        with patch("api.auth.check_rate_limit", AsyncMock(return_value=(False, 0))):
            async with _NullSessionLocal() as db:
                result = await forgot_password(
                    ForgotPasswordRequest(email="a@b.com"),
                    _mock_request(),
                    db,
                )
        assert "message" in result

    @pytest.mark.asyncio
    async def test_forgot_password_google_user_generic(self):
        uid, email = await _create_user(auth_method=AuthMethod.GOOGLE.value, google_id="g1")
        try:
            async with _NullSessionLocal() as db:
                await db.execute(
                    update(User).where(User.id == uid).values(password_hash=None)
                )
                await db.commit()
                result = await forgot_password(
                    ForgotPasswordRequest(email=email), _mock_request(), db
                )
            assert "message" in result
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_forgot_password_token_store_failure(self, patch_redis):
        uid, email = await _create_user()
        try:
            with patch("api.auth._store_reset_token", AsyncMock(return_value=False)):
                result = await forgot_password(
                    ForgotPasswordRequest(email=email), _mock_request(), _NullSessionLocal()
                )
            assert result.get("email_sent") == "false"
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_forgot_password_smtp_not_configured_returns_url(self, patch_redis):
        uid, email = await _create_user()
        try:
            with patch("utils.email_service.get_email_service") as mock_svc:
                svc = MagicMock()
                svc.is_configured.return_value = False
                mock_svc.return_value = svc
                result = await forgot_password(
                    ForgotPasswordRequest(email=email), _mock_request(), _NullSessionLocal()
                )
            assert "reset_url" in result
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_forgot_password_email_send_failure(self, patch_redis):
        uid, email = await _create_user()
        try:
            with patch("utils.email_service.get_email_service") as mock_svc:
                svc = MagicMock()
                svc.is_configured.return_value = True
                svc.send_password_reset_email = AsyncMock(return_value=False)
                mock_svc.return_value = svc
                result = await forgot_password(
                    ForgotPasswordRequest(email=email), _mock_request(), _NullSessionLocal()
                )
            assert "message" in result
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_forgot_password_email_exception(self, patch_redis):
        uid, email = await _create_user()
        try:
            with patch("utils.email_service.get_email_service", side_effect=RuntimeError("smtp")):
                result = await forgot_password(
                    ForgotPasswordRequest(email=email), _mock_request(), _NullSessionLocal()
                )
            assert "message" in result
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_forgot_password_top_level_exception(self):
        async with _NullSessionLocal() as db:
            with patch.object(db, "execute", AsyncMock(side_effect=RuntimeError("db"))):
                result = await forgot_password(
                    ForgotPasswordRequest(email="a@b.com"),
                    _mock_request(),
                    db,
                )
        assert "message" in result

    @pytest.mark.asyncio
    async def test_reset_password_rate_limited(self):
        with patch("api.auth.check_rate_limit", AsyncMock(return_value=(False, 0))):
            with pytest.raises(Exception) as exc:
                await reset_password(
                    _mock_request(),
                    ResetPasswordRequest(
                        token="t",
                        new_password="NewSecure99!",
                        confirm_password="NewSecure99!",
                    ),
                    _NullSessionLocal(),
                )
        assert exc.value.status_code == 429

    @pytest.mark.asyncio
    async def test_reset_password_user_missing_after_token(self, patch_redis):
        patch_redis._store["password_reset:orphan"] = "orphan@example.com"
        with pytest.raises(Exception) as exc:
            await reset_password(
                _mock_request(),
                ResetPasswordRequest(
                    token="orphan",
                    new_password="NewSecure99!",
                    confirm_password="NewSecure99!",
                ),
                _NullSessionLocal(),
            )
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_reset_password_invalidate_tokens_warning(self, patch_redis):
        uid, email = await _create_user()
        token = "reset-ok"
        patch_redis._store[f"password_reset:{token}"] = email
        try:
            with patch(
                "api.auth.invalidate_all_user_tokens",
                AsyncMock(side_effect=RuntimeError("redis")),
            ), patch("api.auth.check_account_lockout", AsyncMock(return_value=(False, 0))):
                async with _NullSessionLocal() as db:
                    result = await reset_password(
                        _mock_request(),
                        ResetPasswordRequest(
                            token=token,
                            new_password="NewSecure99!",
                            confirm_password="NewSecure99!",
                        ),
                        db,
                    )
            assert "successfully" in result["message"]
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_reset_password_internal_error(self, patch_redis):
        patch_redis._store["password_reset:bad"] = "a@b.com"
        async with _NullSessionLocal() as db:
            with patch("api.auth.check_account_lockout", AsyncMock(return_value=(False, 0))), patch.object(
                db, "execute", AsyncMock(side_effect=RuntimeError("db"))
            ):
                with pytest.raises(Exception) as exc:
                    await reset_password(
                        _mock_request(),
                        ResetPasswordRequest(
                            token="bad",
                            new_password="NewSecure99!",
                            confirm_password="NewSecure99!",
                        ),
                        db,
                    )
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_change_password_rate_limited(self):
        uid, email = await _create_user()
        response = MagicMock()
        response.headers = {}
        try:
            with patch(
                "api.auth.check_rate_limit_with_headers",
                AsyncMock(
                    return_value=type(
                        "R",
                        (),
                        {
                            "allowed": False,
                            "limit": 5,
                            "remaining": 0,
                            "reset_seconds": 3600,
                        },
                    )()
                ),
            ):
                with pytest.raises(Exception) as exc:
                    await change_password(
                        PasswordChangeRequest(
                            current_password="SecurePass123!",
                            new_password="ChangedPass99!",
                            confirm_password="ChangedPass99!",
                        ),
                        response,
                        {"id": str(uid)},
                        _NullSessionLocal(),
                    )
            assert exc.value.status_code == 429
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_change_password_no_password_set(self):
        uid, email = await _create_user(auth_method=AuthMethod.GOOGLE.value, google_id="g1")
        response = MagicMock()
        response.headers = {}
        try:
            async with _NullSessionLocal() as db:
                await db.execute(
                    update(User).where(User.id == uid).values(password_hash=None)
                )
                await db.commit()
                with pytest.raises(Exception) as exc:
                    await change_password(
                        PasswordChangeRequest(
                            current_password="x",
                            new_password="ChangedPass99!",
                            confirm_password="ChangedPass99!",
                        ),
                        response,
                        {"id": str(uid)},
                        db,
                    )
            assert exc.value.status_code == 422
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_change_password_same_as_current(self):
        uid, email = await _create_user()
        response = MagicMock()
        response.headers = {}
        try:
            with pytest.raises(Exception) as exc:
                await change_password(
                    PasswordChangeRequest(
                        current_password="SecurePass123!",
                        new_password="SecurePass123!",
                        confirm_password="SecurePass123!",
                    ),
                    response,
                    {"id": str(uid)},
                    _NullSessionLocal(),
                )
            assert exc.value.status_code == 422
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_change_password_internal_error(self):
        uid, email = await _create_user()
        response = MagicMock()
        response.headers = {}
        try:
            async with _NullSessionLocal() as db:
                with patch.object(db, "execute", AsyncMock(side_effect=RuntimeError("db"))):
                    with pytest.raises(Exception) as exc:
                        await change_password(
                            PasswordChangeRequest(
                                current_password="SecurePass123!",
                                new_password="ChangedPass99!",
                                confirm_password="ChangedPass99!",
                            ),
                            response,
                            {"id": str(uid)},
                            db,
                        )
            assert exc.value.status_code == 500
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_email_status_exception(self):
        with patch(
            "utils.email_service.get_email_service",
            side_effect=RuntimeError("svc"),
        ):
            result = await get_email_service_status()
        assert result["email_configured"] is False


# ---------------------------------------------------------------------------
# Email verification handlers
# ---------------------------------------------------------------------------


class TestVerificationCoverage:
    @pytest.mark.asyncio
    async def test_verify_code_rate_limited(self):
        with patch("api.auth.check_rate_limit", AsyncMock(return_value=(False, 0))):
            with pytest.raises(Exception) as exc:
                await verify_email_code(
                    _mock_request(),
                    VerifyCodeRequest(email="a@b.com", code="123456"),
                    _NullSessionLocal(),
                )
        assert exc.value.status_code == 429

    @pytest.mark.asyncio
    async def test_verify_code_user_not_found(self):
        with pytest.raises(Exception) as exc:
            await verify_email_code(
                _mock_request(),
                VerifyCodeRequest(email="missing@example.com", code="123456"),
                _NullSessionLocal(),
            )
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_verify_code_jwt_error_fallback(self, patch_redis):
        uid, email = await _create_user(email_verified=False)
        patch_redis._store["email_verification:123456"] = email
        try:
            with patch("api.auth._make_jwt", side_effect=RuntimeError("jwt")), patch(
                "api.auth.check_account_lockout", AsyncMock(return_value=(False, 0))
            ):
                async with _NullSessionLocal() as db:
                    result = await verify_email_code(
                        _mock_request(),
                        VerifyCodeRequest(email=email, code="123456"),
                        db,
                    )
            assert result["redirect"] == "/auth/login"
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_verify_code_welcome_email_failure(self, patch_redis):
        uid, email = await _create_user(email_verified=False)
        patch_redis._store["email_verification:654321"] = email
        try:
            with patch("utils.email_service.get_email_service", side_effect=RuntimeError("smtp")), patch(
                "api.auth.check_account_lockout", AsyncMock(return_value=(False, 0))
            ):
                async with _NullSessionLocal() as db:
                    result = await verify_email_code(
                        _mock_request(),
                        VerifyCodeRequest(email=email, code="654321"),
                        db,
                    )
            assert result["email_verified"] is True
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_verify_code_internal_error(self, patch_redis):
        uid, email = await _create_user(email_verified=False)
        try:
            async with _NullSessionLocal() as db:
                with patch("api.auth.check_account_lockout", AsyncMock(return_value=(False, 0))), patch.object(
                    db, "execute", AsyncMock(side_effect=RuntimeError("db"))
                ):
                    with pytest.raises(Exception) as exc:
                        await verify_email_code(
                            _mock_request(),
                            VerifyCodeRequest(email=email, code="123456"),
                            db,
                        )
            assert exc.value.status_code == 500
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_verify_email_token_user_not_found(self, patch_redis):
        patch_redis._store["email_verification:tok1"] = "ghost@example.com"
        with pytest.raises(Exception) as exc:
            await verify_email(token="tok1", db=_NullSessionLocal())
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_verify_email_already_verified(self, patch_redis):
        uid, email = await _create_user(email_verified=True)
        token = "tok-ver"
        patch_redis._store[f"email_verification:{token}"] = email
        try:
            result = await verify_email(token=token, db=_NullSessionLocal())
            assert result["email_verified"] is True
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_verify_email_welcome_email_failure(self, patch_redis):
        uid, email = await _create_user(email_verified=False)
        token = "tok-wel"
        patch_redis._store[f"email_verification:{token}"] = email
        try:
            with patch("utils.email_service.get_email_service", side_effect=RuntimeError("smtp")):
                async with _NullSessionLocal() as db:
                    result = await verify_email(token=token, db=db)
            assert result["email_verified"] is True
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_verify_email_internal_error(self, patch_redis):
        uid, email = await _create_user(email_verified=False)
        token = "tok-err"
        patch_redis._store[f"email_verification:{token}"] = email
        try:
            async with _NullSessionLocal() as db:
                with patch.object(db, "commit", AsyncMock(side_effect=RuntimeError("db"))):
                    with pytest.raises(Exception) as exc:
                        await verify_email(token=token, db=db)
            assert exc.value.status_code == 500
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_resend_verification_rate_limited(self):
        with patch("api.auth.check_rate_limit", AsyncMock(return_value=(False, 0))):
            async with _NullSessionLocal() as db:
                result = await resend_verification_email(
                    ResendVerificationRequest(email="a@b.com"), db
                )
        assert "message" in result

    @pytest.mark.asyncio
    async def test_resend_verification_already_verified(self):
        uid, email = await _create_user(email_verified=True)
        try:
            result = await resend_verification_email(
                ResendVerificationRequest(email=email), _NullSessionLocal()
            )
            assert "message" in result
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_resend_verification_exception(self):
        async with _NullSessionLocal() as db:
            with patch.object(db, "execute", AsyncMock(side_effect=RuntimeError("db"))):
                result = await resend_verification_email(
                    ResendVerificationRequest(email="a@b.com"), db
                )
        assert "message" in result

    @pytest.mark.asyncio
    async def test_verification_status_user_not_found(self):
        async with _NullSessionLocal() as db:
            with pytest.raises(Exception) as exc:
                await get_verification_status({"id": str(uuid.uuid4())}, db)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_verification_status_internal_error(self):
        uid, email = await _create_user()
        try:
            async with _NullSessionLocal() as db:
                with patch.object(db, "execute", AsyncMock(side_effect=RuntimeError("db"))):
                    with pytest.raises(Exception) as exc:
                        await get_verification_status({"id": str(uid)}, db)
            assert exc.value.status_code == 500
        finally:
            await _delete_user(uid)


# ---------------------------------------------------------------------------
# Remaining line coverage (92% → 100%)
# ---------------------------------------------------------------------------


class TestAuthCoverageRemaining:
    def test_register_full_name_validators_direct(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            RegisterRequest.validate_full_name("")
        with pytest.raises(ValueError, match="at least"):
            RegisterRequest.validate_full_name("A")
        with pytest.raises(ValueError, match="cannot exceed"):
            RegisterRequest.validate_full_name("A" * 101)
        with pytest.raises(ValueError, match="letters"):
            RegisterRequest.validate_full_name("Bad123")

    @pytest.mark.asyncio
    async def test_register_integrity_error_on_commit(self):
        payload = _reg_payload("_integ")
        req = RegisterRequest(**payload)
        async with _NullSessionLocal() as db:
            with patch.object(
                db,
                "commit",
                AsyncMock(side_effect=auth_module._SQLIntegrityError("", "", "")),
            ):
                with pytest.raises(Exception) as exc:
                    await register_user(_mock_request(), req, db)
        assert exc.value.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_register_auto_verified_logs(self):
        payload = _reg_payload("_logauto")
        req = RegisterRequest(**payload)
        async with _NullSessionLocal() as db:
            with patch.object(auth_module.settings, "disable_email_verification", True):
                result = await register_user(_mock_request(), req, db)
        assert result.user["email_verified"] is True

    @pytest.mark.asyncio
    async def test_login_success_returns_full_auth_response(self):
        uid, email = await _create_user(email_verified=True)
        try:
            async with _NullSessionLocal() as db:
                with patch("api.auth.check_account_lockout", AsyncMock(return_value=(False, 0))), patch(
                    "api.auth.clear_login_attempts", AsyncMock()
                ):
                    result = await login_user(
                        _mock_request(),
                        LoginRequest(email=email, password="SecurePass123!"),
                        db,
                    )
            assert result.expires_in > 0
            assert result.access_token
            assert result.user["email"] == email
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_google_callback_new_user_welcome_email(self, patch_redis):
        state = "st-welcome"
        email = f"newoauth_{uuid.uuid4().hex[:8]}@example.com"
        patch_redis._store[f"oauth_state:{state}"] = json.dumps({"redirect": "/dashboard"})
        with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
            "api.auth.httpx.AsyncClient",
            return_value=_oauth_http_mocks(
                userinfo_body={"id": f"gid-{uuid.uuid4().hex[:6]}", "email": email, "name": "New"}
            ),
        ), patch("utils.email_service.get_email_service") as mock_email:
            svc = MagicMock()
            svc.is_configured.return_value = True
            svc.send_welcome_email = AsyncMock(return_value=True)
            mock_email.return_value = svc
            async with _NullSessionLocal() as db:
                resp = await google_callback(
                    _mock_request(), code="c", state=state, error=None, db=db
                )
        assert "code=" in resp.headers["location"]
        async with _NullSessionLocal() as db:
            row = await db.execute(select(User).where(User.email == email))
            user = row.scalar_one_or_none()
            if user:
                await db.execute(delete(User).where(User.id == user.id))
                await db.commit()

    @pytest.mark.asyncio
    async def test_google_callback_exchange_code_store_exception(self, patch_redis):
        state = "st-setex-fail"
        patch_redis._store[f"oauth_state:{state}"] = json.dumps({"redirect": "/dashboard"})

        async def _boom_setex(key, ttl, value):
            if key.startswith("oauth_code:"):
                raise RuntimeError("redis write failed")
            return await FakeRedis.setex(patch_redis, key, ttl, value)

        patch_redis.setex = _boom_setex  # type: ignore[method-assign]
        with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
            "api.auth.httpx.AsyncClient", return_value=_oauth_http_mocks()
        ), patch("utils.email_service.get_email_service") as mock_email:
            mock_email.return_value.is_configured.return_value = False
            async with _NullSessionLocal() as db:
                resp = await google_callback(
                    _mock_request(), code="c", state=state, error=None, db=db
                )
        assert "service_unavailable" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_google_callback_link_exchange_redis_unavailable(self, patch_redis):
        uid, email = await _create_user()
        state = "st-link-redis"
        patch_redis._store[f"oauth_state:{state}"] = json.dumps(
            {"redirect": "/dashboard/settings", "link_user_id": str(uid)}
        )
        call_count = {"n": 0}

        async def _get_redis():
            call_count["n"] += 1
            if call_count["n"] == 1:
                return patch_redis
            return None

        gid = f"link-redis-{uuid.uuid4().hex[:8]}"
        try:
            with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
                "api.auth.httpx.AsyncClient",
                return_value=_oauth_http_mocks(
                    userinfo_body={"id": gid, "email": email, "name": "Linker"}
                ),
            ), patch("utils.redis_client.get_redis_client", side_effect=_get_redis):
                async with _NullSessionLocal() as db:
                    resp = await google_callback(
                        _mock_request(), code="c", state=state, error=None, db=db
                    )
            assert "service_unavailable" in resp.headers["location"]
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_google_callback_link_exchange_store_exception(self, patch_redis):
        uid, email = await _create_user()
        state = "st-link-exc"
        patch_redis._store[f"oauth_state:{state}"] = json.dumps(
            {"redirect": "/dashboard/settings", "link_user_id": str(uid)}
        )
        gid = f"link-exc-{uuid.uuid4().hex[:8]}"

        async def _bad_setex(key, ttl, value):
            if key.startswith("oauth_code:"):
                raise RuntimeError("link store failed")
            return await FakeRedis.setex(patch_redis, key, ttl, value)

        patch_redis.setex = _bad_setex  # type: ignore[method-assign]
        try:
            with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
                "api.auth.httpx.AsyncClient",
                return_value=_oauth_http_mocks(
                    userinfo_body={"id": gid, "email": email, "name": "Linker"}
                ),
            ):
                async with _NullSessionLocal() as db:
                    resp = await google_callback(
                        _mock_request(), code="c", state=state, error=None, db=db
                    )
            assert "service_unavailable" in resp.headers["location"]
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_link_google_success_returns_url(self, patch_redis):
        uid, email = await _create_user()
        try:
            async with _NullSessionLocal() as db:
                with patch.object(auth_module, "settings", _oauth_mock_settings(True)):
                    result = await link_google_account(
                        _mock_request(), {"id": str(uid)}, db
                    )
            assert "oauth_url" in result
            assert "accounts.google.com" in result["oauth_url"]
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_link_google_state_store_exception(self):
        uid, email = await _create_user()
        try:
            async with _NullSessionLocal() as db:
                with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
                    "utils.redis_client.get_redis_client",
                    AsyncMock(side_effect=RuntimeError("redis")),
                ):
                    with pytest.raises(Exception) as exc:
                        await link_google_account(
                            _mock_request(), {"id": str(uid)}, db
                        )
            assert exc.value.status_code == 503
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_unlink_google_no_password(self):
        uid, email = await _create_user(auth_method=AuthMethod.GOOGLE.value, google_id="g-nopw")
        async with _NullSessionLocal() as db:
            await db.execute(
                update(User).where(User.id == uid).values(password_hash=None)
            )
            await db.commit()
            with pytest.raises(Exception) as exc:
                await unlink_google_account({"id": str(uid)}, db)
        assert exc.value.status_code == 422
        assert "password" in str(exc.value.detail).lower()
        await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_forgot_password_nonexistent_email(self):
        async with _NullSessionLocal() as db:
            result = await forgot_password(
                ForgotPasswordRequest(email="missing_fp@example.com"),
                _mock_request(),
                db,
            )
        assert "message" in result

    @pytest.mark.asyncio
    async def test_forgot_password_email_sent_logs(self, patch_redis):
        uid, email = await _create_user()
        try:
            with patch("utils.email_service.get_email_service") as mock_svc:
                svc = MagicMock()
                svc.is_configured.return_value = True
                svc.send_password_reset_email = AsyncMock(return_value=True)
                mock_svc.return_value = svc
                async with _NullSessionLocal() as db:
                    result = await forgot_password(
                        ForgotPasswordRequest(email=email), _mock_request(), db
                    )
            assert "message" in result
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_reset_password_first_local_password(self, patch_redis):
        uid = uuid.uuid4()
        email = f"nopw_{uid.hex[:8]}@example.com"
        token = "first-pw"
        patch_redis._store[f"password_reset:{token}"] = email

        mock_user = MagicMock()
        mock_user.id = uid
        mock_user.email = email
        mock_user.password_hash = None
        mock_user.auth_method = AuthMethod.LOCAL.value
        mock_user.updated_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user

        try:
            with patch("api.auth.check_account_lockout", AsyncMock(return_value=(False, 0))), patch(
                "api.auth.invalidate_all_user_tokens", AsyncMock()
            ):
                async with _NullSessionLocal() as db:
                    with patch.object(db, "execute", AsyncMock(return_value=mock_result)):
                        result = await reset_password(
                            _mock_request(),
                            ResetPasswordRequest(
                                token=token,
                                new_password="NewSecure99!",
                                confirm_password="NewSecure99!",
                            ),
                            db,
                        )
            assert "successfully" in result["message"]
        finally:
            pass

    @pytest.mark.asyncio
    async def test_change_password_user_not_found(self):
        response = MagicMock()
        response.headers = {}
        async with _NullSessionLocal() as db:
            with pytest.raises(Exception) as exc:
                await change_password(
                    PasswordChangeRequest(
                        current_password="SecurePass123!",
                        new_password="ChangedPass99!",
                        confirm_password="ChangedPass99!",
                    ),
                    response,
                    {"id": str(uuid.uuid4())},
                    db,
                )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_change_password_wrong_current(self):
        uid, email = await _create_user()
        response = MagicMock()
        response.headers = {}
        try:
            async with _NullSessionLocal() as db:
                with pytest.raises(Exception) as exc:
                    await change_password(
                        PasswordChangeRequest(
                            current_password="WrongPass99!",
                            new_password="ChangedPass99!",
                            confirm_password="ChangedPass99!",
                        ),
                        response,
                        {"id": str(uid)},
                        db,
                    )
            assert exc.value.status_code == 422
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_change_password_success_full_path(self):
        uid, email = await _create_user()
        response = MagicMock()
        response.headers = {}
        try:
            async with _NullSessionLocal() as db:
                with patch("api.auth.invalidate_all_user_tokens", AsyncMock()):
                    result = await change_password(
                        PasswordChangeRequest(
                            current_password="SecurePass123!",
                            new_password="ChangedPass99!",
                            confirm_password="ChangedPass99!",
                        ),
                        response,
                        {"id": str(uid)},
                        db,
                    )
            assert result["access_token"]
            assert result["message"]
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_verify_code_lockout(self):
        uid, email = await _create_user(email_verified=False)
        try:
            with patch("api.auth.check_account_lockout", AsyncMock(return_value=(True, 300))):
                async with _NullSessionLocal() as db:
                    with pytest.raises(Exception) as exc:
                        await verify_email_code(
                            _mock_request(),
                            VerifyCodeRequest(email=email, code="123456"),
                            db,
                        )
            assert exc.value.status_code == 423
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_verify_code_already_verified_profile_complete(self):
        uid, email = await _create_user(email_verified=True, profile_completed=True)
        try:
            async with _NullSessionLocal() as db:
                result = await verify_email_code(
                    _mock_request(),
                    VerifyCodeRequest(email=email, code="123456"),
                    db,
                )
            assert result["redirect"] == "/dashboard"
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_verify_code_invalid_code(self, patch_redis):
        uid, email = await _create_user(email_verified=False)
        try:
            with patch("api.auth.check_account_lockout", AsyncMock(return_value=(False, 0))):
                async with _NullSessionLocal() as db:
                    with pytest.raises(Exception) as exc:
                        await verify_email_code(
                            _mock_request(),
                            VerifyCodeRequest(email=email, code="123456"),
                            db,
                        )
            assert exc.value.status_code == 422
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_verify_code_welcome_email_sent(self, patch_redis):
        uid, email = await _create_user(email_verified=False)
        patch_redis._store["email_verification:888888"] = email
        try:
            with patch("api.auth.check_account_lockout", AsyncMock(return_value=(False, 0))), patch(
                "utils.email_service.get_email_service"
            ) as mock_svc:
                svc = MagicMock()
                svc.is_configured.return_value = True
                svc.send_welcome_email = AsyncMock(return_value=True)
                mock_svc.return_value = svc
                async with _NullSessionLocal() as db:
                    result = await verify_email_code(
                        _mock_request(),
                        VerifyCodeRequest(email=email, code="888888"),
                        db,
                    )
            assert result["access_token"]
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_verify_email_invalid_token(self, patch_redis):
        async with _NullSessionLocal() as db:
            with pytest.raises(Exception) as exc:
                await verify_email(token="missing-token", db=db)
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_verify_email_welcome_email_sent(self, patch_redis):
        uid, email = await _create_user(email_verified=False)
        token = "wel-tok"
        patch_redis._store[f"email_verification:{token}"] = email
        try:
            with patch("utils.email_service.get_email_service") as mock_svc:
                svc = MagicMock()
                svc.is_configured.return_value = True
                svc.send_welcome_email = AsyncMock(return_value=True)
                mock_svc.return_value = svc
                async with _NullSessionLocal() as db:
                    result = await verify_email(token=token, db=db)
            assert result["email_verified"] is True
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_resend_verification_nonexistent_and_send(self):
        async with _NullSessionLocal() as db:
            missing = await resend_verification_email(
                ResendVerificationRequest(email="missing_resend@example.com"), db
            )
        assert "message" in missing

        uid, email = await _create_user(email_verified=False)
        try:
            with patch("api.auth._send_verification_email", AsyncMock(return_value=True)) as mock_send:
                async with _NullSessionLocal() as db:
                    sent = await resend_verification_email(
                        ResendVerificationRequest(email=email), db
                    )
            assert "message" in sent
            mock_send.assert_awaited_once()
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_verification_status_with_timestamp(self):
        uid, email = await _create_user(email_verified=True)
        try:
            async with _NullSessionLocal() as db:
                result = await get_verification_status({"id": str(uid)}, db)
            assert result["email_verified"] is True
            assert result["email_verified_at"] is not None
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_google_callback_welcome_email_failure(self, patch_redis):
        state = "st-wel-fail"
        email = f"wel_fail_{uuid.uuid4().hex[:8]}@example.com"
        patch_redis._store[f"oauth_state:{state}"] = json.dumps({"redirect": "/dashboard"})
        with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
            "api.auth.httpx.AsyncClient",
            return_value=_oauth_http_mocks(
                userinfo_body={"id": f"gid-{uuid.uuid4().hex[:6]}", "email": email, "name": "New"}
            ),
        ), patch("utils.email_service.get_email_service") as mock_email:
            svc = MagicMock()
            svc.is_configured.return_value = True
            svc.send_welcome_email = AsyncMock(side_effect=RuntimeError("smtp down"))
            mock_email.return_value = svc
            async with _NullSessionLocal() as db:
                resp = await google_callback(
                    _mock_request(), code="c", state=state, error=None, db=db
                )
        assert "code=" in resp.headers["location"]
        async with _NullSessionLocal() as db:
            row = await db.execute(select(User).where(User.email == email))
            user = row.scalar_one_or_none()
            if user:
                await db.execute(delete(User).where(User.id == user.id))
                await db.commit()

    @pytest.mark.asyncio
    async def test_google_callback_final_exchange_redis_unavailable(self, patch_redis):
        state = "st-final-redis"
        patch_redis._store[f"oauth_state:{state}"] = json.dumps({"redirect": "/dashboard"})
        call_count = {"n": 0}

        async def _get_redis():
            call_count["n"] += 1
            # First call: state GETDEL; later calls: exchange-code storage
            if call_count["n"] <= 1:
                return patch_redis
            return None

        with patch.object(auth_module, "settings", _oauth_mock_settings(True)), patch(
            "api.auth.httpx.AsyncClient", return_value=_oauth_http_mocks()
        ), patch("utils.email_service.get_email_service") as mock_email, patch(
            "utils.redis_client.get_redis_client", side_effect=_get_redis
        ):
            mock_email.return_value.is_configured.return_value = False
            async with _NullSessionLocal() as db:
                resp = await google_callback(
                    _mock_request(), code="c", state=state, error=None, db=db
                )
        assert "service_unavailable" in resp.headers["location"]
