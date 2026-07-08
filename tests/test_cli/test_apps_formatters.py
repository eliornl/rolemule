"""Tests for cli.formatters.applications."""

from __future__ import annotations

from cli.formatters.applications import format_applications_table, format_stats_human


def test_table_includes_columns() -> None:
    text = format_applications_table(
        {
            "applications": [
                {
                    "id": "uuid-123",
                    "status": "completed",
                    "match_score": 0.9,
                    "company_name": "Acme Corp",
                    "job_title": "Backend Engineer",
                }
            ],
            "total": 1,
            "page": 1,
            "per_page": 20,
        }
    )
    assert "STATUS" in text
    assert "Acme Corp" in text
    assert "90%" in text
    assert "uuid-123" in text


def test_stats_human_format() -> None:
    text = format_stats_human({"total": 10, "applied": 4, "interviews": 2, "response_rate": 25.0})
    assert "Total: 10" in text
    assert "Response rate: 25.0%" in text
