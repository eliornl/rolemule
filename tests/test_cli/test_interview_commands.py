"""Tests for applypilot interview commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from applypilot_client.errors import ApiClientError, ExitCode


def test_interview_show_formats_questions(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.interview_prep.show.return_value = {
        "session_id": "sess-1",
        "has_interview_prep": True,
        "interview_prep": {
            "predicted_questions": {
                "behavioral": [{"question": "Tell me about a conflict you resolved."}],
            },
            "day_before_checklist": ["Review job description", "Prepare questions"],
            "confidence_boosters": ["Strong Python background"],
        },
    }

    with patch("cli.commands.interview.require_client", return_value=mock_client):
        result = invoke("interview", "show", "sess-1")
    assert result.exit_code == 0
    assert "## Questions" in result.output
    assert "conflict" in result.output.lower()
    assert "Day-before checklist" in result.output


def test_interview_generate_wait(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.interview_prep.generate.return_value = {
        "session_id": "sess-2",
        "status": "generating",
        "message": "Started",
    }
    mock_client.interview_prep.show.return_value = {
        "session_id": "sess-2",
        "has_interview_prep": True,
        "interview_prep": {"confidence_boosters": ["You got this"]},
    }

    with patch("cli.commands.interview.require_client", return_value=mock_client):
        with patch("cli.commands.interview.wait_for_interview_prep") as wait_mock:
            wait_mock.return_value = {"session_id": "sess-2", "has_interview_prep": True, "is_generating": False}
            result = invoke("--format", "json", "interview", "generate", "sess-2", "--wait")
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["has_interview_prep"] is True


def test_interview_show_404(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.interview_prep.show.side_effect = ApiClientError(
        message="Workflow session not found",
        status_code=404,
        error_code="RES_3001",
        exit_code=ExitCode.ERROR,
    )

    with patch("cli.commands.interview.require_client", return_value=mock_client):
        result = invoke("interview", "show", "missing")
    assert result.exit_code != 0


def test_interview_delete_requires_confirm(invoke, write_credentials) -> None:
    write_credentials()
    result = invoke("interview", "delete", "sess-1")
    assert result.exit_code == int(ExitCode.ERROR)


def test_interview_delete_with_confirm(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()

    with patch("cli.commands.interview.require_client", return_value=mock_client):
        result = invoke("interview", "delete", "sess-1", "--confirm")
    assert result.exit_code == 0
    mock_client.interview_prep.delete.assert_called_once_with("sess-1")
