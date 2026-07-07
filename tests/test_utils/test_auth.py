"""Tests for utils/auth.py."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import Request

from config.settings import get_security_settings
from utils.auth import (
    create_access_token,
    extract_token_from_request,
    get_current_user,
    get_current_user_with_complete_profile,
    invalidate_all_user_tokens,
    require_admin,
    revoke_token,
)
from utils.error_responses import APIError


def _make_request(path: str = "/api/v1/test", auth: str | None = None, token_qs: str | None = None) -> Request:
    headers = []
    if auth:
        headers.append((b"authorization", auth.encode()))
    qs = f"?token={token_qs}" if token_qs else ""
    scope = {
        "type": "http",
        "method": "GET",
        "path": path + ("" if not token_qs else ""),
        "headers": headers,
        "query_string": qs.encode().lstrip(b"?") if token_qs else b"",
        "client": ("127.0.0.1", 8000),
        "server": ("test", 80),
    }
    return Request(scope)


def test_extract_token_from_header() -> None:
    req = _make_request(auth="Bearer my.jwt.token")
    assert extract_token_from_request(req) == "my.jwt.token"


def test_extract_token_websocket_query_param() -> None:
    req = _make_request(path="/api/ws/workflow", token_qs="ws-token")
    assert extract_token_from_request(req) == "ws-token"


def test_extract_token_rejects_query_on_http() -> None:
    req = _make_request(path="/api/v1/profile", token_qs="should-not-work")
    assert extract_token_from_request(req) is None


def test_create_access_token_has_jti_and_exp() -> None:
    sec = get_security_settings()
    token = create_access_token({"sub": str(uuid.uuid4()), "email": "a@b.com"})
    payload = jwt.decode(
        token,
        sec.jwt_config["secret_key"],
        algorithms=[sec.jwt_config["algorithm"]],
    )
    assert "jti" in payload
    assert "iat" in payload
    assert "exp" in payload


@pytest.mark.asyncio
async def test_revoke_token_success(mock_redis) -> None:
    get_security_settings()
    token = create_access_token({"sub": "u1", "email": "a@b.com"})
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_redis)):
        assert await revoke_token(token) is True
        mock_redis.setex.assert_awaited()


@pytest.mark.asyncio
async def test_revoke_token_no_redis() -> None:
    token = create_access_token({"sub": "u1", "email": "a@b.com"})
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)):
        assert await revoke_token(token) is False


@pytest.mark.asyncio
async def test_revoke_expired_token_noop() -> None:
    sec = get_security_settings()
    payload = {
        "sub": "u1",
        "jti": str(uuid.uuid4()),
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
    }
    token = jwt.encode(payload, sec.jwt_config["secret_key"], algorithm=sec.jwt_config["algorithm"])
    assert await revoke_token(token) is True


@pytest.mark.asyncio
async def test_invalidate_all_user_tokens(mock_redis) -> None:
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_redis)):
        assert await invalidate_all_user_tokens(str(uuid.uuid4())) is True


@pytest.mark.asyncio
async def test_get_current_user_no_token() -> None:
    req = _make_request()
    db = AsyncMock()
    with pytest.raises(APIError) as exc:
        await get_current_user(req, credentials=None, db=db)  # type: ignore[arg-type]
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_expired_token() -> None:
    sec = get_security_settings()
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "a@b.com",
        "type": "access",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
        "iat": datetime.now(timezone.utc) - timedelta(hours=1),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, sec.jwt_config["secret_key"], algorithm=sec.jwt_config["algorithm"])
    req = _make_request(auth=f"Bearer {token}")
    creds = MagicMock(credentials=token)
    with pytest.raises(APIError):
        await get_current_user(req, credentials=creds, db=AsyncMock())


@pytest.mark.asyncio
async def test_require_admin_forbidden() -> None:
    with pytest.raises(APIError) as exc:
        await require_admin({"is_admin": False})
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_admin_ok() -> None:
    user = await require_admin({"is_admin": True, "email": "admin@x.com"})
    assert user["is_admin"] is True


@pytest.mark.asyncio
async def test_get_current_user_with_complete_profile_forbidden() -> None:
    with pytest.raises(APIError) as exc:
        await get_current_user_with_complete_profile({"profile_completed": False})
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_current_user_uses_header_when_no_query_token(mock_redis) -> None:
    from models.database import User, AuthMethod
    from sqlalchemy.engine import Result

    uid = uuid.uuid4()
    user = User(
        id=uid,
        email="ok@example.com",
        password_hash="hash",
        auth_method=AuthMethod.LOCAL.value,
        full_name="Ok User",
        profile_completed=True,
        profile_completion_percentage=100,
    )
    mock_result = MagicMock(spec=Result)
    mock_result.scalar_one_or_none.return_value = user
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)

    token = create_access_token({"sub": str(uid), "email": "ok@example.com"})
    req = _make_request()
    creds = MagicMock(credentials=token)

    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_redis)):
        info = await get_current_user(req, credentials=creds, db=db)
    assert info["email"] == "ok@example.com"


@pytest.mark.asyncio
async def test_get_current_user_invalid_credentials() -> None:
    req = _make_request(auth="Bearer not.a.valid.jwt")
    creds = MagicMock(credentials="not.a.valid.jwt")
    with pytest.raises(APIError):
        await get_current_user(req, credentials=creds, db=AsyncMock())


@pytest.mark.asyncio
async def test_get_current_user_unexpected_error() -> None:
    token = create_access_token({"sub": str(uuid.uuid4()), "email": "a@b.com"})
    req = _make_request(auth=f"Bearer {token}")
    creds = MagicMock(credentials=token)
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=RuntimeError("db down"))
    with patch("utils.auth._validate_jwt_token", AsyncMock(side_effect=RuntimeError("boom"))):
        with pytest.raises(APIError) as exc:
            await get_current_user(req, credentials=creds, db=db)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_revoke_token_missing_jti() -> None:
    sec = get_security_settings()
    payload = {"sub": "u1", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    token = jwt.encode(payload, sec.jwt_config["secret_key"], algorithm=sec.jwt_config["algorithm"])
    assert await revoke_token(token) is False


@pytest.mark.asyncio
async def test_invalidate_all_user_tokens_no_redis() -> None:
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)):
        assert await invalidate_all_user_tokens(str(uuid.uuid4())) is False


@pytest.mark.asyncio
async def test_invalidate_all_user_tokens_redis_error() -> None:
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(side_effect=RuntimeError("fail"))
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_redis)):
        assert await invalidate_all_user_tokens(str(uuid.uuid4())) is False


@pytest.mark.asyncio
async def test_get_current_user_invalid_token_payload() -> None:
    token = create_access_token({"sub": str(uuid.uuid4()), "email": "a@b.com"})
    req = _make_request(auth=f"Bearer {token}")
    creds = MagicMock(credentials=token)
    with patch("utils.auth._validate_jwt_token", AsyncMock(return_value=None)):
        with pytest.raises(APIError) as exc:
            await get_current_user(req, credentials=creds, db=AsyncMock())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_with_complete_profile_ok() -> None:
    user = await get_current_user_with_complete_profile({"profile_completed": True, "email": "ok@x.com"})
    assert user["profile_completed"] is True


@pytest.mark.asyncio
async def test_is_token_revoked_when_redis_unavailable() -> None:
    from utils.auth import _is_token_revoked

    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)):
        assert await _is_token_revoked("jti-123") is True


@pytest.mark.asyncio
async def test_validate_jwt_rejects_wrong_token_type() -> None:
    from utils.auth import _validate_jwt_token

    sec = get_security_settings()
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "a@b.com",
        "type": "password_reset",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, sec.jwt_config["secret_key"], algorithm=sec.jwt_config["algorithm"])
    with patch("utils.auth._is_token_revoked", AsyncMock(return_value=False)):
        assert await _validate_jwt_token(token, AsyncMock()) is None


@pytest.mark.asyncio
async def test_validate_jwt_rejects_revoked_token(mock_redis) -> None:
    from utils.auth import _validate_jwt_token

    uid = uuid.uuid4()
    token = create_access_token({"sub": str(uid), "email": "a@b.com"})
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_redis)):
        mock_redis.get = AsyncMock(return_value="1")
        assert await _validate_jwt_token(token, AsyncMock()) is None


@pytest.mark.asyncio
async def test_validate_jwt_rejects_pre_invalidation_token(mock_redis) -> None:
    from utils.auth import _validate_jwt_token

    uid = uuid.uuid4()
    token = create_access_token({"sub": str(uid), "email": "a@b.com"})
    with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_redis)):
        mock_redis.get = AsyncMock(side_effect=[None, str(int(datetime.now(timezone.utc).timestamp()) + 100)])
        assert await _validate_jwt_token(token, AsyncMock()) is None


@pytest.mark.asyncio
async def test_validate_jwt_skips_invalidation_check_on_redis_error() -> None:
    from models.database import User, AuthMethod
    from utils.auth import _validate_jwt_token

    uid = uuid.uuid4()
    user = User(
        id=uid,
        email="ok@example.com",
        password_hash="hash",
        auth_method=AuthMethod.LOCAL.value,
        full_name="Ok User",
        profile_completed=True,
        profile_completion_percentage=100,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)

    token = create_access_token({"sub": str(uid), "email": "ok@example.com"})
    with patch("utils.auth._is_token_revoked", AsyncMock(return_value=False)), \
         patch("utils.redis_client.get_redis_client", AsyncMock(side_effect=RuntimeError("redis down"))):
        info = await _validate_jwt_token(token, db)
    assert info is not None
    assert info["email"] == "ok@example.com"


@pytest.mark.asyncio
async def test_validate_jwt_missing_user_id() -> None:
    from utils.auth import _validate_jwt_token

    sec = get_security_settings()
    payload = {
        "email": "a@b.com",
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, sec.jwt_config["secret_key"], algorithm=sec.jwt_config["algorithm"])
    assert await _validate_jwt_token(token, AsyncMock()) is None


@pytest.mark.asyncio
async def test_validate_jwt_invalid_uuid() -> None:
    from utils.auth import _validate_jwt_token

    sec = get_security_settings()
    payload = {
        "sub": "not-a-uuid",
        "email": "a@b.com",
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, sec.jwt_config["secret_key"], algorithm=sec.jwt_config["algorithm"])
    with patch("utils.auth._is_token_revoked", AsyncMock(return_value=False)):
        assert await _validate_jwt_token(token, AsyncMock()) is None


@pytest.mark.asyncio
async def test_validate_jwt_user_not_found() -> None:
    from utils.auth import _validate_jwt_token

    uid = uuid.uuid4()
    token = create_access_token({"sub": str(uid), "email": "a@b.com"})
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    with patch("utils.auth._is_token_revoked", AsyncMock(return_value=False)), \
         patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)):
        assert await _validate_jwt_token(token, db) is None


@pytest.mark.asyncio
async def test_revoke_token_generic_exception() -> None:
    with patch("utils.auth.jwt.decode", side_effect=RuntimeError("decode failed")):
        assert await revoke_token("not-a-real-token") is False


@pytest.mark.asyncio
async def test_is_token_revoked_on_redis_error() -> None:
    from utils.auth import _is_token_revoked

    with patch("utils.redis_client.get_redis_client", AsyncMock(side_effect=RuntimeError("redis fail"))):
        assert await _is_token_revoked("jti-abc") is True


@pytest.mark.asyncio
async def test_validate_jwt_unexpected_error() -> None:
    from utils.auth import _validate_jwt_token

    token = create_access_token({"sub": str(uuid.uuid4()), "email": "a@b.com"})
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=RuntimeError("db down"))
    with patch("utils.auth._is_token_revoked", AsyncMock(return_value=False)), \
         patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)):
        assert await _validate_jwt_token(token, db) is None
