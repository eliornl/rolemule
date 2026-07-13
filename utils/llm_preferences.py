"""Helpers for reading per-user LLM preferences (Settings → preferred model)."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def preferred_model_for_byok(
    preferred_model: Optional[str],
    user_api_key: Optional[str],
) -> Optional[str]:
    """
    Return preferred Gemini model only when BYOK is active.

    Vertex / server-key mode always uses ``settings.gemini_model``.
    """
    if not user_api_key:
        return None
    if isinstance(preferred_model, str) and preferred_model.strip():
        return preferred_model.strip()
    return None


def preferred_model_from_state(
    state: Optional[Dict[str, Any]],
    user_api_key: Optional[str],
) -> Optional[str]:
    """
    Return Settings → preferred model from workflow state when BYOK is active.

    Args:
        state: Workflow state (or any dict with ``workflow_preferences``)
        user_api_key: Decrypted BYOK key, if any

    Returns:
        Model id string, or None to use the system default
    """
    prefs = (state or {}).get("workflow_preferences") or {}
    model = prefs.get("preferred_model")
    return preferred_model_for_byok(
        model if isinstance(model, str) else None,
        user_api_key,
    )


async def load_preferred_model(
    db: "AsyncSession",
    user_id: uuid.UUID,
    user_api_key: Optional[str],
) -> Optional[str]:
    """
    Load ``preferred_model`` from ``UserWorkflowPreferences`` for BYOK callers.

    Used by standalone agents (interview prep, CV optimizer, career tools)
    that do not receive ``workflow_preferences`` in LangGraph state.
    """
    if not user_api_key:
        return None

    from sqlalchemy import select

    from models.database import UserWorkflowPreferences

    result = await db.execute(
        select(UserWorkflowPreferences).where(
            UserWorkflowPreferences.user_id == user_id
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        return None
    return preferred_model_for_byok(row.preferred_model, user_api_key)
