"""Tests for utils/gemini_api_key_format.py."""

from utils.gemini_api_key_format import validate_gemini_api_key


def test_validate_empty_or_whitespace() -> None:
    assert validate_gemini_api_key("") is False
    assert validate_gemini_api_key("   ") is False
    assert validate_gemini_api_key(None) is False  # type: ignore[arg-type]


def test_validate_rejects_embedded_whitespace() -> None:
    assert validate_gemini_api_key("AIzaSy1234567890\nextra") is False
    assert validate_gemini_api_key("key with spaces") is False


def test_validate_accepts_plausible_keys() -> None:
    assert validate_gemini_api_key("AIzaSyABCDEFghijklmnop") is True
    assert validate_gemini_api_key("a" * 12) is True


def test_validate_rejects_too_short() -> None:
    assert validate_gemini_api_key("short") is False


def test_validate_rejects_invalid_characters() -> None:
    assert validate_gemini_api_key("invalid@key!!!!!!!!") is False
