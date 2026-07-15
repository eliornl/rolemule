"""Unit tests for preferred_model helpers."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from utils.llm_preferences import (
    load_preferred_model,
    preferred_model_for_byok,
    preferred_model_for_context,
    preferred_model_from_state,
)


def test_preferred_model_for_byok_requires_user_key() -> None:
    assert preferred_model_for_byok("gemini-2.5-flash", None) is None
    assert preferred_model_for_byok("gemini-2.5-flash", "") is None
    assert preferred_model_for_byok("gemini-2.5-flash", "user-key") == "gemini-2.5-flash"
    assert preferred_model_for_byok("  gemini-2.5-flash  ", "user-key") == "gemini-2.5-flash"
    assert preferred_model_for_byok(None, "user-key") is None
    assert preferred_model_for_byok("   ", "user-key") is None


def test_preferred_model_from_state() -> None:
    state = {"workflow_preferences": {"preferred_model": "gemini-3.5-flash"}}
    assert preferred_model_from_state(state, "user-key") == "gemini-3.5-flash"
    assert preferred_model_from_state(state, None) is None
    assert preferred_model_from_state({}, "user-key") is None
    assert preferred_model_from_state(None, "user-key") is None


def test_preferred_model_for_context_vertex() -> None:
    assert preferred_model_for_context("m", has_credentials=True, use_vertex_ai=True) is None
    assert preferred_model_for_context("m", has_credentials=False) is None


@pytest.mark.asyncio
async def test_load_preferred_model_not_ready() -> None:
    assert await load_preferred_model(AsyncMock(), uuid.uuid4(), None) is None


@pytest.mark.asyncio
async def test_load_preferred_model_row_paths() -> None:
    uid = uuid.uuid4()
    mock_db = AsyncMock()

    # no row
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=result)
    assert await load_preferred_model(mock_db, uid, "key", has_credentials=True) is None

    # valid ollama model
    row = SimpleNamespace(preferred_model="qwen3.6", preferred_provider="ollama")
    result.scalar_one_or_none.return_value = row
    assert await load_preferred_model(mock_db, uid, None, has_credentials=True) == "qwen3.6"

    # stale model for provider
    row.preferred_model = "gemini-3.5-flash"
    row.preferred_provider = "ollama"
    assert await load_preferred_model(mock_db, uid, None, has_credentials=True) is None

    # empty preferred_model
    row.preferred_model = None
    assert await load_preferred_model(mock_db, uid, None, has_credentials=True) is None
