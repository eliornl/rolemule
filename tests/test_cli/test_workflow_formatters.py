"""Tests for cli.formatters.workflow."""

from __future__ import annotations

from cli.formatters.workflow import format_workflow_results


def test_format_fit_section_heading() -> None:
    text = format_workflow_results(
        {
            "session_id": "abc",
            "status": "completed",
            "profile_matching": {
                "final_scores": {"overall_match_score": 0.82},
                "match_summary": "Strong alignment on Python and APIs.",
            },
        },
        section="fit",
    )
    assert "## Fit Score" in text
    assert "82" in text
    assert "Strong alignment" in text


def test_format_cover_letter_section() -> None:
    text = format_workflow_results(
        {
            "session_id": "abc",
            "status": "completed",
            "cover_letter": {"content": "Dear hiring team,"},
        },
        section="cover-letter",
    )
    assert "## Cover Letter" in text
    assert "Dear hiring team" in text


def test_format_resume_tips_bullets() -> None:
    text = format_workflow_results(
        {
            "session_id": "abc",
            "status": "completed",
            "resume_recommendations": {
                "comprehensive_advice": {"quick_wins": ["Add metrics", "Lead with impact"]},
            },
        },
        section="resume",
    )
    assert "## Resume Tips" in text
    assert "- Add metrics" in text


def test_format_all_includes_errors() -> None:
    text = format_workflow_results(
        {
            "session_id": "abc",
            "status": "failed",
            "error_messages": ["Job analyzer failed"],
        },
        section="all",
    )
    assert "## Errors" in text
    assert "Job analyzer failed" in text
