"""Loose format check for Anthropic API keys (sk-ant-)."""

from typing import Final

_MIN_LEN: Final[int] = 20
_MAX_LEN: Final[int] = 512


def validate_anthropic_api_key(api_key: str) -> bool:
    """
    Return True if the string plausibly looks like an Anthropic API key.

    Args:
        api_key: Raw key string from the user

    Returns:
        True when the format looks acceptable
    """
    if not api_key or not api_key.strip():
        return False
    k = api_key.strip()
    if any(c.isspace() for c in k):
        return False
    if len(k) < _MIN_LEN or len(k) > _MAX_LEN:
        return False
    if not k.startswith("sk-ant-"):
        return False
    return all(c.isalnum() or c in "-_" for c in k)
