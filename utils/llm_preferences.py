"""Helpers for reading per-user LLM preferences (provider + model)."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def preferred_model_for_context(
    preferred_model: Optional[str],
    *,
    has_credentials: bool,
    use_vertex_ai: bool = False,
) -> Optional[str]:
    """
    Return preferred model when the user may choose one.

    Vertex always uses the server model. Ollama/BYOK honor preferred_model
    when credentials are ready.

    Args:
        preferred_model: Stored preference or None
        has_credentials: Whether LLM context is ready
        use_vertex_ai: When True, ignore user model choice

    Returns:
        Model id string, or None for system default
    """
    if use_vertex_ai or not has_credentials:
        return None
    if isinstance(preferred_model, str) and preferred_model.strip():
        return preferred_model.strip()
    return None


def preferred_model_for_byok(
    preferred_model: Optional[str],
    user_api_key: Optional[str],
) -> Optional[str]:
    """
    Backward-compatible: return model when a BYOK key string is present.

    Ollama (no key) should use ``preferred_model_for_context`` instead.
    """
    return preferred_model_for_context(
        preferred_model,
        has_credentials=bool(user_api_key),
        use_vertex_ai=False,
    )


def preferred_model_from_state(
    state: Optional[Dict[str, Any]],
    user_api_key: Optional[str],
    *,
    has_credentials: Optional[bool] = None,
) -> Optional[str]:
    """
    Return Settings → preferred model from workflow state.

    Args:
        state: Workflow state (or any dict with ``workflow_preferences``)
        user_api_key: Decrypted BYOK key, if any
        has_credentials: Override readiness (True for Ollama / Vertex)

    Returns:
        Model id string, or None to use the system default
    """
    prefs = (state or {}).get("workflow_preferences") or {}
    model = prefs.get("preferred_model")
    ready = (
        has_credentials
        if has_credentials is not None
        else bool(user_api_key) or (state or {}).get("llm_provider") == "ollama"
    )
    resolved = preferred_model_for_context(
        model if isinstance(model, str) else None,
        has_credentials=bool(ready),
    )
    if not resolved:
        return None
    provider = (state or {}).get("llm_provider") or prefs.get("preferred_provider")
    if provider:
        from utils.llm.models import is_valid_model_for_provider

        if not is_valid_model_for_provider(str(provider), resolved):
            return None
    return resolved


async def load_preferred_model(
    db: "AsyncSession",
    user_id: uuid.UUID,
    user_api_key: Optional[str],
    *,
    has_credentials: Optional[bool] = None,
) -> Optional[str]:
    """
    Load ``preferred_model`` from ``UserWorkflowPreferences``.

    Used by standalone agents (interview prep, CV optimizer, career tools)
    that do not receive ``workflow_preferences`` in LangGraph state.
    """
    ready = has_credentials if has_credentials is not None else bool(user_api_key)
    if not ready:
        return None

    from sqlalchemy import select

    from models.database import UserWorkflowPreferences
    from utils.llm.models import is_valid_model_for_provider

    result = await db.execute(
        select(UserWorkflowPreferences).where(
            UserWorkflowPreferences.user_id == user_id
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        return None
    resolved = preferred_model_for_context(
        row.preferred_model,
        has_credentials=True,
    )
    if not resolved:
        return None
    if row.preferred_provider and not is_valid_model_for_provider(
        row.preferred_provider, resolved
    ):
        return None
    return resolved


async def load_workflow_preferences(
    db: "AsyncSession",
    user_id: uuid.UUID,
) -> Optional[Any]:
    """Load the user's workflow preferences row, or None."""
    from sqlalchemy import select

    from models.database import UserWorkflowPreferences

    result = await db.execute(
        select(UserWorkflowPreferences).where(
            UserWorkflowPreferences.user_id == user_id
        )
    )
    return result.scalar_one_or_none()
