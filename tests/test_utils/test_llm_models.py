"""Unit tests for utils.llm.models allowlists and helpers."""

from types import SimpleNamespace

from utils.llm.models import (
    default_model_for_provider,
    is_valid_model_for_provider,
    model_label,
    model_list_for_provider,
    models_labeled_payload,
    models_payload,
    valid_models_for_provider,
)


def test_valid_models_for_provider_known_and_unknown() -> None:
    assert "gemini-3.5-flash" in valid_models_for_provider("gemini")
    assert "gpt-5.6-luna" in valid_models_for_provider("openai")
    assert valid_models_for_provider("unknown") == frozenset()


def test_model_list_and_label() -> None:
    gemini = model_list_for_provider("gemini")
    assert gemini[0] == "gemini-3.5-flash"
    assert model_list_for_provider("nope") == []
    assert "Flash" in model_label("gemini-3.5-flash")
    assert model_label("totally-unknown-model") == "totally-unknown-model"


def test_models_payloads() -> None:
    payload = models_payload()
    assert set(payload.keys()) >= {"anthropic", "gemini", "ollama", "openai"}
    assert payload["ollama"][0] == "qwen3"
    labeled = models_labeled_payload()
    assert labeled["gemini"][0]["id"] == "gemini-3.5-flash"
    assert "label" in labeled["gemini"][0]


def test_is_valid_model_for_provider() -> None:
    assert is_valid_model_for_provider("gemini", None) is True
    assert is_valid_model_for_provider("gemini", "") is True
    assert is_valid_model_for_provider("gemini", "  ") is True
    assert is_valid_model_for_provider("gemini", "gemini-3.5-flash") is True
    assert is_valid_model_for_provider("gemini", "gpt-5.6-luna") is False


def test_default_model_for_provider() -> None:
    settings = SimpleNamespace(
        gemini_model="gemini-2.5-flash",
        openai_model="gpt-5.5",
        anthropic_model="claude-haiku-4-5",
        ollama_model="llama3.3",
    )
    assert default_model_for_provider("gemini", settings) == "gemini-2.5-flash"
    assert default_model_for_provider("openai", settings) == "gpt-5.5"
    assert default_model_for_provider("anthropic", settings) == "claude-haiku-4-5"
    assert default_model_for_provider("ollama", settings) == "llama3.3"
    assert default_model_for_provider("unknown", settings) == "gemini-2.5-flash"
    # settings=None resolves get_settings at call time
    assert isinstance(default_model_for_provider("gemini"), str)
