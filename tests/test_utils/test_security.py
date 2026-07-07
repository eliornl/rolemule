"""Tests for utils/security.py."""

from unittest.mock import patch

from utils.security import (
    MAX_TEXT_LENGTH,
    sanitize_cover_letter,
    sanitize_dict,
    sanitize_html,
    sanitize_job_analysis,
    sanitize_llm_output,
    sanitize_name,
    sanitize_resume_recommendations,
    sanitize_text,
)


def test_sanitize_html_empty() -> None:
    assert sanitize_html("") == ""
    assert sanitize_html(None) == ""  # type: ignore[arg-type]


def test_sanitize_html_strips_script_and_escapes() -> None:
    raw = '<script>alert(1)</script>Hello <b onclick="x()">World</b>'
    out = sanitize_html(raw)
    assert "<script" not in out.lower()
    assert "onclick" not in out


def test_sanitize_html_truncates_long_content() -> None:
    long = "x" * (MAX_TEXT_LENGTH + 500)
    out = sanitize_html(long)
    assert len(out) <= MAX_TEXT_LENGTH


def test_sanitize_html_allow_basic_formatting_with_bleach() -> None:
    raw = "<p>Hello <strong>world</strong></p><script>x</script>"
    out = sanitize_html(raw, allow_basic_formatting=True)
    assert "Hello" in out
    assert "<script" not in out


def test_sanitize_html_fallback_without_bleach() -> None:
    raw = "<p>Hi</p>"
    with patch("utils.security._BLEACH_AVAILABLE", False):
        out = sanitize_html(raw, allow_basic_formatting=True)
        assert "&lt;p&gt;" in out


def test_sanitize_text_strips_controls() -> None:
    assert sanitize_text("  hello\x00world  ") == "helloworld"


def test_sanitize_text_truncates() -> None:
    assert len(sanitize_text("a" * 200, max_length=10)) == 10


def test_sanitize_name() -> None:
    assert sanitize_name("<script>Acme</script>") == "&lt;script&gt;Acme&lt;/script&gt;"


def test_sanitize_dict_recursive() -> None:
    data = {
        "id": "keep-me",
        "title": "<script>x</script>Title",
        "nested": {"body": "javascript:alert(1)"},
        "items": ["<b>ok</b>"],
    }
    out = sanitize_dict(data, html_fields=["body"], skip_fields=["id"])
    assert out["id"] == "keep-me"
    assert "<script" not in out["title"].lower()
    assert out["nested"]["body"]  # sanitized html field


def test_sanitize_llm_output_types() -> None:
    assert sanitize_llm_output({"a": "<script>x</script>"})["a"] != "<script>x</script>"
    assert isinstance(sanitize_llm_output(["<script>a</script>"]), list)
    assert sanitize_llm_output(123) == 123
    assert sanitize_llm_output("") == ""


def test_sanitize_llm_output_preserves_code_blocks() -> None:
    raw = "Intro\n```html\n<script>safe in code</script>\n```\n`inline`"
    out = sanitize_llm_output(raw)
    assert "```" in out


def test_sanitize_job_analysis() -> None:
    analysis = {
        "job_title": "Engineer",
        "summary": "<script>bad</script>Summary",
        "source": "llm",
    }
    out = sanitize_job_analysis(analysis)
    assert out["source"] == "llm"
    assert "<script" not in out["summary"].lower()


def test_sanitize_cover_letter_fields() -> None:
    cl = {"content": "<script>x</script>", "letter": "Hi", "body": "Body"}
    out = sanitize_cover_letter(cl)
    assert "content" in out


def test_sanitize_html_non_string_coerced() -> None:
    assert "42" in sanitize_html(42)  # type: ignore[arg-type]


def test_sanitize_text_non_string_and_empty() -> None:
    assert sanitize_text("") == ""
    assert sanitize_text(99) == "99"  # type: ignore[arg-type]


def test_sanitize_name_empty() -> None:
    assert sanitize_name("") == ""


def test_sanitize_dict_empty_returns_same() -> None:
    assert sanitize_dict({}) == {}
    assert sanitize_dict(None) is None  # type: ignore[arg-type]


def test_sanitize_dict_non_string_passthrough() -> None:
    out = sanitize_dict({"count": 3, "flag": True})
    assert out["count"] == 3
    assert out["flag"] is True


def test_sanitize_cover_letter_empty() -> None:
    assert sanitize_cover_letter({}) == {}
    assert sanitize_cover_letter(None) is None  # type: ignore[arg-type]


def test_sanitize_resume_recommendations_empty() -> None:
    assert sanitize_resume_recommendations({}) == {}
    assert sanitize_resume_recommendations(None) is None  # type: ignore[arg-type]


def test_sanitize_resume_recommendations_text_and_list_fields() -> None:
    recs = {
        "summary_recommendation": "<script>bad</script>Improve summary",
        "experience_recommendations": ["<b>Tip 1</b>", {"keep": "dict"}],
        "skills_recommendations": "Add Python",
        "education_recommendations": ["Highlight degree"],
        "overall_feedback": "Strong candidate",
    }
    out = sanitize_resume_recommendations(recs)
    assert "<script" not in out["summary_recommendation"].lower()
    assert isinstance(out["experience_recommendations"], list)
    assert out["overall_feedback"] == "Strong candidate"
