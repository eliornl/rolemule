"""Tests for utils/text_processing.py."""

from unittest.mock import patch

from utils.text_processing import MAX_LENGTH, calculate_similarity, clean_text


def test_clean_text_empty() -> None:
    assert clean_text("   ") == ""


def test_clean_text_strips_html_and_normalizes() -> None:
    raw = "  Hello   <b>world</b>  \n\n  foo  "
    out = clean_text(raw)
    assert "<b>" not in out
    assert "Hello" in out
    assert "world" in out


def test_clean_text_html_entities() -> None:
    assert "&nbsp;" not in clean_text("Price &amp; value")


def test_calculate_similarity_both_empty() -> None:
    assert calculate_similarity("  ", " ") == 1.0


def test_calculate_similarity_one_empty() -> None:
    assert calculate_similarity("hello", "") == 0.0
    assert calculate_similarity("", "world") == 0.0


def test_calculate_similarity_identical() -> None:
    assert calculate_similarity("Hello World", "hello   world") == 1.0


def test_calculate_similarity_different() -> None:
    score = calculate_similarity("abc", "xyz")
    assert 0.0 <= score < 1.0


def test_calculate_similarity_truncates_long_text() -> None:
    a = "a" * (MAX_LENGTH + 100)
    b = "a" * (MAX_LENGTH + 100)
    assert calculate_similarity(a, b) == 1.0


def test_clean_text_regex_failure_fallback() -> None:
    with patch("utils.text_processing.re.sub", side_effect=RuntimeError("regex fail")):
        assert clean_text("  hello world  ") == "hello world"


def test_calculate_similarity_matcher_failure_fallback() -> None:
    with patch("utils.text_processing.SequenceMatcher", side_effect=RuntimeError("fail")):
        assert calculate_similarity("Hello", "hello") == 1.0
        assert calculate_similarity("abc", "xyz") == 0.0
