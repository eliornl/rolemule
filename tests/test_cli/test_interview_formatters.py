"""Tests for cli.formatters.interview."""

from __future__ import annotations

from cli.formatters.interview import format_interview_prep


def test_format_questions_array() -> None:
    text = format_interview_prep(
        {
            "session_id": "abc",
            "interview_prep": {
                "predicted_questions": {
                    "behavioral": [{"question": "Describe a challenge."}],
                    "technical": [{"question": "Explain caching."}],
                },
            },
        }
    )
    assert "## Questions" in text
    assert "Describe a challenge" in text
    assert "Explain caching" in text


def test_format_checklist_and_boosters() -> None:
    text = format_interview_prep(
        {
            "session_id": "abc",
            "interview_prep": {
                "day_before_checklist": ["Sleep well", "Print resume"],
                "confidence_boosters": ["10 years experience"],
            },
        }
    )
    assert "Day-before checklist" in text
    assert "Confidence boosters" in text
