"""Tests for cli.formatters.cv."""

from __future__ import annotations

from cli.formatters.cv import format_cv_result


def test_format_partial_notice() -> None:
    text = format_cv_result(
        {
            "session_id": "abc",
            "result": {
                "status": "partial",
                "best_score": 7.5,
                "stop_reason": "api_rate_limit",
                "iteration_history": [{"iteration": 1, "score": 7.5}],
            },
        }
    )
    assert "Partial result" in text
    assert "7.5" in text
    assert "## Iterations" in text
