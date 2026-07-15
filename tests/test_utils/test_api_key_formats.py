"""Tests for OpenAI / Anthropic API key format validators."""

from utils.anthropic_api_key_format import validate_anthropic_api_key
from utils.openai_api_key_format import validate_openai_api_key


def test_openai_key_accepts_sk_and_sk_proj() -> None:
    assert validate_openai_api_key("sk-" + ("a" * 40)) is True
    assert validate_openai_api_key("sk-proj-" + ("b" * 40)) is True


def test_openai_key_rejects_bad_format() -> None:
    assert validate_openai_api_key("") is False
    assert validate_openai_api_key("AIzaSy-not-openai") is False
    assert validate_openai_api_key("sk- short") is False


def test_anthropic_key_accepts_sk_ant() -> None:
    assert validate_anthropic_api_key("sk-ant-" + ("c" * 40)) is True


def test_anthropic_key_rejects_openai_shape() -> None:
    assert validate_anthropic_api_key("sk-" + ("d" * 40)) is False
    assert validate_anthropic_api_key("") is False
