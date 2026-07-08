"""Tests for applypilot workflow commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from applypilot_client.errors import ApiClientError, ExitCode


def test_analyze_from_file(invoke, write_credentials, tmp_path: Path) -> None:
    write_credentials()
    job = tmp_path / "job.txt"
    job.write_text("Senior Python Engineer at Acme Corp", encoding="utf-8")

    mock_client = MagicMock()
    mock_client.workflow.start.return_value = {
        "session_id": "sess-file",
        "status": "initialized",
        "message": "ok",
    }

    with patch("cli.commands.workflow.require_client", return_value=mock_client):
        result = invoke("workflow", "analyze", str(job))
    assert result.exit_code == 0
    mock_client.workflow.start.assert_called_once()
    kwargs = mock_client.workflow.start.call_args.kwargs
    assert "Senior Python Engineer" in kwargs["job_text"]


def test_analyze_wait_until_completed(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.workflow.start.return_value = {"session_id": "sess-wait", "status": "initialized"}
    mock_client.workflow.get_status.return_value = {
        "session_id": "sess-wait",
        "status": "completed",
        "progress_percentage": 100,
    }
    mock_client.workflow.get_results.return_value = {
        "session_id": "sess-wait",
        "status": "completed",
        "cover_letter": {"content": "Hello"},
    }

    with patch("cli.commands.workflow.require_client", return_value=mock_client):
        with patch("cli.commands.workflow.wait_for_terminal_status") as wait_mock:
            wait_mock.return_value = {"session_id": "sess-wait", "status": "completed"}
            result = invoke("--format", "json", "workflow", "analyze", "-", "--wait", input="Job text here")
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["session_id"] == "sess-wait"


def test_analyze_duplicate_exits_zero(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.workflow.start.side_effect = ApiClientError(
        message="Duplicate application",
        status_code=409,
        error_code="RES_3002",
        details=[
            {"field": "application_id", "message": "app-123", "code": "DUPLICATE_APPLICATION"},
            {"field": "session_id", "message": "sess-dup", "code": "DUPLICATE_APPLICATION"},
        ],
        exit_code=ExitCode.ERROR,
    )

    with patch("cli.commands.workflow.require_client", return_value=mock_client):
        result = invoke("--format", "json", "workflow", "analyze", "-", input="Same job")
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["warning"] is True
    assert payload["application_id"] == "app-123"


def test_analyze_no_api_key_message(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.workflow.start.side_effect = ApiClientError(
        message="No API key configured",
        status_code=422,
        error_code="CFG_6001",
        exit_code=ExitCode.ERROR,
    )

    with patch("cli.commands.workflow.require_client", return_value=mock_client):
        result = invoke("workflow", "analyze", "-", input="Job")
    assert result.exit_code != 0
    assert "api-key set" in result.output.lower()


def test_continue_with_confirm(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.workflow.continue_workflow.return_value = {
        "session_id": "sess-gate",
        "status": "in_progress",
        "message": "Resumed",
    }

    with patch("cli.commands.workflow.require_client", return_value=mock_client):
        result = invoke("workflow", "continue", "sess-gate", "--confirm")
    assert result.exit_code == 0
    mock_client.workflow.continue_workflow.assert_called_once_with("sess-gate")


def test_analyze_requires_input(invoke, write_credentials) -> None:
    write_credentials()
    with patch("cli.commands.workflow.require_client", return_value=MagicMock()):
        result = invoke("workflow", "analyze")
    assert result.exit_code == int(ExitCode.ERROR)
