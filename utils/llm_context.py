"""Shared helper to resolve per-user LLM context for API endpoints."""

from __future__ import annotations

from typing import Any, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import User, UserWorkflowPreferences
from utils.error_responses import no_api_key_error, not_found_error
from utils.llm.availability import UserLLMContext, resolve_user_llm_context


async def require_user_llm_context(
    db: AsyncSession,
    user_id: UUID,
    *,
    user: Optional[User] = None,
) -> Tuple[User, UserLLMContext, Optional[UserWorkflowPreferences]]:
    """
    Load user + prefs, resolve LLM context, or raise CFG_6001 / not found.

    Args:
        db: Async DB session
        user_id: Authenticated user id
        user: Optional pre-loaded User row

    Returns:
        (user, context, prefs_row)

    Raises:
        APIError: not_found or no_api_key_error
    """
    if user is None:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
    if not user:
        raise not_found_error("User not found")

    prefs_result = await db.execute(
        select(UserWorkflowPreferences).where(
            UserWorkflowPreferences.user_id == user_id
        )
    )
    prefs = prefs_result.scalar_one_or_none()
    ctx = resolve_user_llm_context(user, prefs)
    if not ctx.ready:
        raise no_api_key_error()
    return user, ctx, prefs
