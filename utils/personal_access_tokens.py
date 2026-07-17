# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import PersonalAccessToken, User

PAT_PREFIX = "rm_pat_"
DEFAULT_PAT_EXPIRE_DAYS = 90
MAX_PAT_EXPIRE_DAYS = 365
MAX_PATS_PER_USER = 25


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def hash_pat_token(token: str) -> str:
    """Return SHA-256 hex digest of a PAT string."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_pat_secret() -> Tuple[str, str]:
    """Return (full_token, display_prefix) for a new PAT."""
    body = secrets.token_urlsafe(32)
    full = f"{PAT_PREFIX}{body}"
    return full, full[: len(PAT_PREFIX) + 8]


async def authenticate_pat(token: str, db: AsyncSession) -> Optional[Dict[str, Any]]:
    """Validate a PAT and return the same user dict shape as JWT auth."""
    if not token.startswith(PAT_PREFIX):
        return None

    token_hash = hash_pat_token(token)
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(PersonalAccessToken).where(
            PersonalAccessToken.token_hash == token_hash,
            PersonalAccessToken.revoked_at.is_(None),
        )
    )
    pat_row = result.scalar_one_or_none()
    if not pat_row:
        return None

    if pat_row.expires_at and pat_row.expires_at < now:
        return None

    user_result = await db.execute(select(User).where(User.id == pat_row.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        return None

    pat_row.last_used_at = now
    await db.commit()

    return {
        "id": str(user.id),
        "_id": str(user.id),
        "email": user.email,
        "auth_method": user.auth_method,
        "full_name": user.full_name,
        "is_admin": user.is_admin,
        "profile_completed": user.profile_completed,
        "profile_completion_percentage": user.profile_completion_percentage,
        "has_google_linked": user.google_id is not None,
        "has_password": user.password_hash is not None,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "last_login": user.last_login,
        "auth_via_pat": True,
    }


async def create_personal_access_token(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    expires_days: Optional[int] = DEFAULT_PAT_EXPIRE_DAYS,
) -> Tuple[PersonalAccessToken, str]:
    """Create a PAT row and return (row, plaintext_token shown once)."""
    count_result = await db.execute(
        select(PersonalAccessToken).where(
            PersonalAccessToken.user_id == user_id,
            PersonalAccessToken.revoked_at.is_(None),
        )
    )
    active = len(count_result.scalars().all())
    if active >= MAX_PATS_PER_USER:
        raise ValueError(f"Maximum {MAX_PATS_PER_USER} active tokens per user")

    full_token, prefix = generate_pat_secret()
    expires_at: Optional[datetime] = None
    if expires_days is not None and expires_days > 0:
        if expires_days > MAX_PAT_EXPIRE_DAYS:
            expires_days = MAX_PAT_EXPIRE_DAYS
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)

    row = PersonalAccessToken(
        user_id=user_id,
        name=name.strip()[:100] or "CLI token",
        token_prefix=prefix,
        token_hash=hash_pat_token(full_token),
        expires_at=expires_at,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row, full_token


async def list_personal_access_tokens(
    db: AsyncSession, user_id: uuid.UUID
) -> List[PersonalAccessToken]:
    result = await db.execute(
        select(PersonalAccessToken)
        .where(PersonalAccessToken.user_id == user_id)
        .order_by(PersonalAccessToken.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_personal_access_token(
    db: AsyncSession, *, user_id: uuid.UUID, token_id: uuid.UUID
) -> bool:
    result = await db.execute(
        select(PersonalAccessToken).where(
            PersonalAccessToken.id == token_id,
            PersonalAccessToken.user_id == user_id,
            PersonalAccessToken.revoked_at.is_(None),
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        return False
    row.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    return True


async def revoke_all_user_pats(db: AsyncSession, user_id: str) -> int:
    """Revoke every active PAT for a user (password change, account delete)."""
    try:
        uid = uuid.UUID(str(user_id))
    except ValueError:
        return 0
    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(PersonalAccessToken)
        .where(
            PersonalAccessToken.user_id == uid,
            PersonalAccessToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await db.commit()
    return int(result.rowcount or 0)


def pat_to_dict(row: PersonalAccessToken) -> Dict[str, Any]:
    """Serialize PAT metadata (never includes secret)."""
    return {
        "id": str(row.id),
        "name": row.name,
        "token_prefix": row.token_prefix,
        "created_at": row.created_at,
        "expires_at": row.expires_at,
        "last_used_at": row.last_used_at,
        "revoked_at": row.revoked_at,
        "active": row.revoked_at is None
        and (row.expires_at is None or row.expires_at >= datetime.now(timezone.utc)),
    }
