"""preferred_model helpers drop models that do not match the active provider."""

from utils.llm_preferences import preferred_model_from_state


def test_preferred_model_from_state_drops_cross_provider_model() -> None:
    state = {
        "llm_provider": "openai",
        "workflow_preferences": {"preferred_model": "gemini-3.5-flash"},
    }
    assert preferred_model_from_state(state, user_api_key="sk-test") is None


def test_preferred_model_from_state_keeps_matching_model() -> None:
    state = {
        "llm_provider": "openai",
        "workflow_preferences": {"preferred_model": "gpt-5.6-luna"},
    }
    assert (
        preferred_model_from_state(state, user_api_key="sk-test") == "gpt-5.6-luna"
    )
