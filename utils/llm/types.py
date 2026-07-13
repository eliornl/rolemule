"""Shared LLM typing helpers."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional, TypedDict

ProviderName = Literal["gemini", "openai", "anthropic", "ollama"]


class GenerateResult(TypedDict, total=False):
    """Normalized generate() payload returned to agents."""

    response: str
    done: bool
    model: str
    filtered: bool
    from_cache: bool


def as_generate_result(
    *,
    response: str,
    model: Optional[str] = None,
    done: bool = True,
    filtered: bool = False,
    from_cache: bool = False,
) -> Dict[str, Any]:
    """
    Build a generate result dict with a stable shape.

    Args:
        response: Model text output
        model: Model id used for the call
        done: Whether generation completed
        filtered: Whether safety filters blocked content
        from_cache: Whether the payload came from Redis cache

    Returns:
        Dict suitable for agent consumption
    """
    result: Dict[str, Any] = {"response": response, "done": done}
    if model is not None:
        result["model"] = model
    if filtered:
        result["filtered"] = True
    if from_cache:
        result["from_cache"] = True
    return result
