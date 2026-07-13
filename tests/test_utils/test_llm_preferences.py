"""Unit tests for preferred_model helpers."""

from __future__ import annotations

from utils.llm_preferences import preferred_model_for_byok, preferred_model_from_state


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
