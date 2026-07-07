"""Tests for utils/llm_parsing.py."""

from utils.llm_parsing import (
    _fix_json_strings,
    _repair_truncated_json,
    parse_json_from_llm_response,
)


def test_fix_json_strings_escapes_control_chars() -> None:
    raw = '{"text": "line1\nline2\ttab"}'
    fixed = _fix_json_strings(raw)
    assert "\\n" in fixed
    assert "\\t" in fixed


def test_fix_json_strings_escapes_carriage_return() -> None:
    raw = '{"text": "a\rb"}'
    fixed = _fix_json_strings(raw)
    assert "\\r" in fixed


def test_repair_truncated_json_closes_open_string() -> None:
    repaired = _repair_truncated_json('{"items": ["a", "b')
    parsed = parse_json_from_llm_response(repaired)
    assert isinstance(parsed, dict)


def test_parse_json_from_fenced_block() -> None:
    response = 'Here is data:\n```json\n{"key": "value"}\n```\nThanks'
    parsed = parse_json_from_llm_response(response)
    assert parsed == {"key": "value"}


def test_parse_json_from_embedded_object() -> None:
    response = 'Analysis: {"score": 8, "notes": "good"} end'
    parsed = parse_json_from_llm_response(response)
    assert parsed["score"] == 8


def test_parse_json_truncated_without_closing_brace() -> None:
    response = '{"items": ["a", "b", "c'
    parsed = parse_json_from_llm_response(response)
    assert "items" in parsed or parsed == {}


def test_parse_json_returns_empty_dict_on_failure() -> None:
    assert parse_json_from_llm_response("not json at all") == {}
