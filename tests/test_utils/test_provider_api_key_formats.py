"""Format validators for OpenAI / Anthropic BYOK keys."""

from utils.anthropic_api_key_format import validate_anthropic_api_key
from utils.openai_api_key_format import validate_openai_api_key


def test_openai_key_format() -> None:
    assert validate_openai_api_key("") is False
    assert validate_openai_api_key("   ") is False
    assert validate_openai_api_key("sk- short") is False
    assert validate_openai_api_key("nope" + "x" * 30) is False
    assert validate_openai_api_key("sk-" + "a" * 10) is False  # too short
    assert validate_openai_api_key("sk-" + "a" * 600) is False  # too long
    assert validate_openai_api_key("sk-" + "a" * 40) is True


def test_anthropic_key_format() -> None:
    assert validate_anthropic_api_key("") is False
    assert validate_anthropic_api_key("sk-ant- has space") is False
    assert validate_anthropic_api_key("sk-" + "a" * 40) is False
    assert validate_anthropic_api_key("sk-ant-" + "a" * 10) is False
    assert validate_anthropic_api_key("sk-ant-" + "a" * 600) is False
    assert validate_anthropic_api_key("sk-ant-" + "a" * 40) is True
