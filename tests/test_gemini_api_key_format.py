"""Unit tests for utils.gemini_api_key_format (BYOK shape check)."""

import pytest

from tests.gemini_test_keys import DUMMY_GEMINI_API_KEY
from utils.gemini_api_key_format import validate_gemini_api_key


@pytest.mark.parametrize(
    "key,expected",
    [
        (DUMMY_GEMINI_API_KEY, True),
        ("Gsk_test_dummy_key_shape_123456789012345678901234567890", True),
        ("AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPpQqRrSsTt", True),
        ("short", False),
        ("", False),
        ("   ", False),
        ("AIzaSy space inside key012345678901234567890", False),
        ("AIzaSy中文字符テストキー12345678901234567890", False),
    ],
)
def test_validate_gemini_api_key(key: str, expected: bool) -> None:
    assert validate_gemini_api_key(key) is expected


def test_validate_rejects_multiline_paste() -> None:
    assert validate_gemini_api_key("AIzaSyFirstLine\nSecondLine0123456789") is False
