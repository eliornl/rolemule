"""Provider-specific model allowlists and defaults for BYOK Settings.

IDs verified against provider docs (as of 2026-07):
- Gemini: https://ai.google.dev/gemini-api/docs/models
- OpenAI: https://developers.openai.com/api/docs/models
- Anthropic: https://platform.claude.com/docs/en/about-claude/models/overview
- Ollama: https://ollama.com/library (pull tags; user must `ollama pull` locally)
"""

from __future__ import annotations

from typing import Dict, FrozenSet, List, Optional

from utils.llm.constants import VALID_LLM_PROVIDERS

# Gemini — AI Studio / Gemini API (stable + useful preview)
VALID_GEMINI_MODELS: FrozenSet[str] = frozenset(
    {
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-3.1-pro-preview",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    }
)

# OpenAI — current GPT-5.x family (Chat Completions + Responses)
VALID_OPENAI_MODELS: FrozenSet[str] = frozenset(
    {
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-5.5",
        "gpt-5.4-mini",
    }
)

# Anthropic — current Claude API aliases / IDs
VALID_ANTHROPIC_MODELS: FrozenSet[str] = frozenset(
    {
        "claude-sonnet-5",
        "claude-opus-4-8",
        "claude-haiku-4-5",
        "claude-fable-5",
        "claude-sonnet-4-6",
    }
)

# Ollama — local library pull tags only (no :cloud). User must `ollama pull`.
VALID_OLLAMA_MODELS: FrozenSet[str] = frozenset(
    {
        "qwen3.6",
        "gemma4",
        "glm-4.7-flash",
        "granite4.1",
        "nemotron3",
        "phi4",
    }
)

_MODELS_BY_PROVIDER: Dict[str, FrozenSet[str]] = {
    "gemini": VALID_GEMINI_MODELS,
    "openai": VALID_OPENAI_MODELS,
    "anthropic": VALID_ANTHROPIC_MODELS,
    "ollama": VALID_OLLAMA_MODELS,
}

# Display order for Settings dropdowns (recommended first)
_MODEL_ORDER: Dict[str, List[str]] = {
    "gemini": [
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-3.1-pro-preview",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    ],
    "openai": [
        "gpt-5.6-luna",
        "gpt-5.6-terra",
        "gpt-5.6-sol",
        "gpt-5.5",
        "gpt-5.4-mini",
    ],
    "anthropic": [
        "claude-sonnet-5",
        "claude-opus-4-8",
        "claude-haiku-4-5",
        "claude-fable-5",
        "claude-sonnet-4-6",
    ],
    "ollama": [
        "qwen3.6",
        "gemma4",
        "glm-4.7-flash",
        "granite4.1",
        "nemotron3",
        "phi4",
    ],
}

# Human-readable labels for Settings UI
MODEL_LABELS: Dict[str, str] = {
    "gemini-3.5-flash": "Gemini 3.5 Flash — best speed & quality (recommended)",
    "gemini-3.1-flash-lite": "Gemini 3.1 Flash-Lite — fastest & lightest",
    "gemini-3.1-pro-preview": "Gemini 3.1 Pro (preview) — most capable",
    "gemini-2.5-flash": "Gemini 2.5 Flash — fast & efficient",
    "gemini-2.5-pro": "Gemini 2.5 Pro — deep reasoning",
    "gpt-5.6-luna": "GPT-5.6 Luna — cost-efficient high volume (recommended)",
    "gpt-5.6-terra": "GPT-5.6 Terra — balanced intelligence & cost",
    "gpt-5.6-sol": "GPT-5.6 Sol — flagship reasoning & coding",
    "gpt-5.5": "GPT-5.5 — frontier professional work",
    "gpt-5.4-mini": "GPT-5.4 mini — fast high-volume mini",
    "claude-sonnet-5": "Claude Sonnet 5 — best speed & intelligence (recommended)",
    "claude-opus-4-8": "Claude Opus 4.8 — complex agentic & enterprise",
    "claude-haiku-4-5": "Claude Haiku 4.5 — fastest near-frontier",
    "claude-fable-5": "Claude Fable 5 — highest capability agents",
    "claude-sonnet-4-6": "Claude Sonnet 4.6 — previous Sonnet generation",
    "qwen3.6": "Qwen 3.6 — strong local general & tools (recommended)",
    "gemma4": "Gemma 4 — newest Google open family",
    "glm-4.7-flash": "GLM-4.7 Flash — efficient 30B-class MoE",
    "granite4.1": "Granite 4.1 — IBM enterprise / RAG / tools",
    "nemotron3": "Nemotron 3 — NVIDIA multimodal (heavy)",
    "phi4": "Phi-4 — compact high quality (light)",
}


def valid_models_for_provider(provider: str) -> FrozenSet[str]:
    """Return the allowlist of model ids for a provider."""
    return _MODELS_BY_PROVIDER.get(provider, frozenset())


def model_list_for_provider(provider: str) -> List[str]:
    """Ordered model ids for Settings UI dropdowns."""
    return list(_MODEL_ORDER.get(provider, []))


def model_label(model_id: str) -> str:
    """Return a human-readable label for a model id."""
    return MODEL_LABELS.get(model_id, model_id)


def models_payload() -> Dict[str, List[str]]:
    """All provider → model lists for GET /api-key/status."""
    return {name: model_list_for_provider(name) for name in sorted(VALID_LLM_PROVIDERS)}


def models_labeled_payload() -> Dict[str, List[Dict[str, str]]]:
    """Provider → [{id, label}] for richer Settings dropdowns."""
    out: Dict[str, List[Dict[str, str]]] = {}
    for name in sorted(VALID_LLM_PROVIDERS):
        out[name] = [
            {"id": mid, "label": model_label(mid)} for mid in model_list_for_provider(name)
        ]
    return out


def is_valid_model_for_provider(provider: str, model: Optional[str]) -> bool:
    """
    Return True when model is None/empty (system default) or in the allowlist.

    Args:
        provider: Canonical provider name
        model: Preferred model id or None

    Returns:
        True when the model is acceptable for the provider
    """
    if model is None or (isinstance(model, str) and not model.strip()):
        return True
    return model.strip() in valid_models_for_provider(provider)


def default_model_for_provider(provider: str, settings: object = None) -> str:
    """
    Return the server default model string for a provider.

    Args:
        provider: Canonical provider name
        settings: Optional Settings instance

    Returns:
        Default model id
    """
    if settings is None:
        from config.settings import get_settings

        settings = get_settings()
    mapping = {
        "gemini": getattr(settings, "gemini_model", "gemini-3.5-flash"),
        "openai": getattr(settings, "openai_model", "gpt-5.6-luna"),
        "anthropic": getattr(settings, "anthropic_model", "claude-sonnet-5"),
        "ollama": getattr(settings, "ollama_model", "qwen3.6"),
    }
    return str(mapping.get(provider, mapping["gemini"]))
