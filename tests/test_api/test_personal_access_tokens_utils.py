"""Unit tests for utils.personal_access_tokens (DB-backed)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from models.database import AuthMethod, User
from tests.test_api.conftest import _NullSessionLocal
from utils.personal_access_tokens import (
    MAX_PAT_EXPIRE_DAYS,
    authenticate_pat,
    create_personal_access_token,
    hash_pat_token,
    list_personal_access_tokens,
    pat_to_dict,
    revoke_all_user_pats,
    revoke_personal_access_token,
)


async def _create_user() -> uuid.UUID:
    uid = uuid.uuid4()
    async with _NullSessionLocal() as session:
        session.add(
            User(
                id=uid,
                email=f"patutils_{uid.hex[:8]}@example.com",
                password_hash="$2b$12$placeholder",
                auth_method=AuthMethod.LOCAL.value,
                full_name="PAT Utils User",
                profile_completed=False,
                profile_completion_percentage=0,
            )
        )
        await session.commit()
    return uid


async def _delete_user(uid: uuid.UUID) -> None:
    from sqlalchemy import delete

    from models.database import PersonalAccessToken

    async with _NullSessionLocal() as session:
        await session.execute(delete(PersonalAccessToken).where(PersonalAccessToken.user_id == uid))
        await session.execute(delete(User).where(User.id == uid))
        await session.commit()


@pytest.mark.asyncio
async def test_hash_and_authenticate_pat_success() -> None:
    uid = await _create_user()
    try:
        async with _NullSessionLocal() as session:
            _, plaintext = await create_personal_access_token(
                session, user_id=uid, name="unit-test", expires_days=7
            )
        async with _NullSessionLocal() as session:
            user = await authenticate_pat(plaintext, session)
        assert user is not None
        assert user["auth_via_pat"] is True
        assert user["id"] == str(uid)
        assert hash_pat_token(plaintext) != plaintext
    finally:
        await _delete_user(uid)


@pytest.mark.asyncio
async def test_authenticate_pat_rejects_non_pat_and_revoked() -> None:
    uid = await _create_user()
    try:
        async with _NullSessionLocal() as session:
            row, plaintext = await create_personal_access_token(
                session, user_id=uid, name="revoke-me", expires_days=7
            )
            token_id = row.id

        async with _NullSessionLocal() as session:
            assert await authenticate_pat("not-a-pat", session) is None

        async with _NullSessionLocal() as session:
            ok = await revoke_personal_access_token(session, user_id=uid, token_id=token_id)
            assert ok is True

        async with _NullSessionLocal() as session:
            assert await authenticate_pat(plaintext, session) is None
            assert await revoke_personal_access_token(
                session, user_id=uid, token_id=uuid.uuid4()
            ) is False
    finally:
        await _delete_user(uid)


@pytest.mark.asyncio
async def test_list_pat_to_dict_and_revoke_all() -> None:
    uid = await _create_user()
    try:
        async with _NullSessionLocal() as session:
            row, _ = await create_personal_access_token(
                session, user_id=uid, name="listed", expires_days=30
            )
            tokens = await list_personal_access_tokens(session, uid)
            assert len(tokens) == 1
            meta = pat_to_dict(row)
            assert meta["active"] is True
            assert meta["name"] == "listed"
            row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
            assert pat_to_dict(row)["active"] is False

        async with _NullSessionLocal() as session:
            count = await revoke_all_user_pats(session, str(uid))
            assert count == 1
    finally:
        await _delete_user(uid)


@pytest.mark.asyncio
async def test_revoke_all_invalid_user_id_returns_zero() -> None:
    async with _NullSessionLocal() as session:
        assert await revoke_all_user_pats(session, "not-a-uuid") == 0


@pytest.mark.asyncio
async def test_authenticate_pat_user_missing() -> None:
    from sqlalchemy import delete

    from models.database import PersonalAccessToken

    uid = await _create_user()
    async with _NullSessionLocal() as session:
        _, plaintext = await create_personal_access_token(
            session, user_id=uid, name="orphan", expires_days=7
        )
    async with _NullSessionLocal() as session:
        await session.execute(delete(User).where(User.id == uid))
        await session.commit()
    try:
        async with _NullSessionLocal() as session:
            assert await authenticate_pat(plaintext, session) is None
    finally:
        async with _NullSessionLocal() as session:
            await session.execute(
                delete(PersonalAccessToken).where(PersonalAccessToken.user_id == uid)
            )
            await session.commit()


@pytest.mark.asyncio
async def test_authenticate_pat_expired_and_create_caps() -> None:
    uid = await _create_user()
    try:
        async with _NullSessionLocal() as session:
            row, plaintext = await create_personal_access_token(
                session, user_id=uid, name="   ", expires_days=MAX_PAT_EXPIRE_DAYS + 50
            )
            assert row.name == "CLI token"
            assert row.expires_at is not None
            assert row.expires_at <= datetime.now(timezone.utc) + timedelta(days=MAX_PAT_EXPIRE_DAYS + 1)
            row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            await session.commit()

        async with _NullSessionLocal() as session:
            assert await authenticate_pat(plaintext, session) is None
    finally:
        await _delete_user(uid)
