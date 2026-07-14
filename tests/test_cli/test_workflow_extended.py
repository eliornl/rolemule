"""Extended workflow command tests — terminal states and polling branches."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from applypilot_client.errors import ApiClientError, ExitCode
from applypilot_client.polling import WorkflowPollTimeout


def test_analyze_wait_awaiting_confirmation(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.workflow.start.return_value = {"session_id": "sess-gate", "status": "initialized"}
    mock_client.workflow.get_results.return_value = {"session_id": "sess-gate", "status": "awaiting_confirmation"}

    with patch("cli.commands.workflow.require_client", return_value=mock_client):
        with patch("cli.commands.workflow.wait_for_terminal_status") as wait_mock:
            wait_mock.return_value = {
                "session_id": "sess-gate",
                "status": "awaiting_confirmation",
                "match_score": 42,
            }
            result = invoke("workflow", "analyze", "-", "--wait", input="Job text")
    assert result.exit_code == 0
    assert "continue" in result.output.lower() or "42" in result.output


def test_analyze_wait_analysis_complete(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.workflow.start.return_value = {"session_id": "sess-ac", "status": "initialized"}
    mock_client.workflow.get_results.return_value = {"session_id": "sess-ac", "status": "analysis_complete"}

    with patch("cli.commands.workflow.require_client", return_value=mock_client):
        with patch("cli.commands.workflow.wait_for_terminal_status") as wait_mock:
            wait_mock.return_value = {"session_id": "sess-ac", "status": "analysis_complete"}
            result = invoke("workflow", "analyze", "-", "--wait", input="Job text")
    assert result.exit_code == 0
    assert "generate-documents" in result.output.lower() or "analysis" in result.output.lower()


def test_analyze_wait_failed(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.workflow.start.return_value = {"session_id": "sess-fail", "status": "initialized"}
    mock_client.workflow.get_results.side_effect = ApiClientError(
        message="Failed",
        status_code=404,
        error_code="RES_3001",
        exit_code=ExitCode.ERROR,
    )

    with patch("cli.commands.workflow.require_client", return_value=mock_client):
        with patch("cli.commands.workflow.wait_for_terminal_status") as wait_mock:
            wait_mock.return_value = {
                "session_id": "sess-fail",
                "status": "failed",
                "error_messages": ["LLM timeout"],
            }
            result = invoke("workflow", "analyze", "-", "--wait", input="Job text")
    assert result.exit_code == int(ExitCode.ERROR)


def test_analyze_wait_timeout(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.workflow.start.return_value = {"session_id": "sess-to", "status": "initialized"}

    with patch("cli.commands.workflow.require_client", return_value=mock_client):
        with patch("cli.commands.workflow.wait_for_terminal_status") as wait_mock:
            wait_mock.side_effect = WorkflowPollTimeout("sess-to", {"status": "in_progress"})
            result = invoke("--format", "json", "workflow", "analyze", "-", "--wait", input="Job text")
    assert result.exit_code == int(ExitCode.ERROR)
    payload = json.loads(result.stdout)
    assert payload["error"] == "timeout"


def test_workflow_status_json(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.workflow.get_status.return_value = {"session_id": "sess-1", "status": "completed"}
    with patch("cli.commands.workflow.require_client", return_value=mock_client):
        result = invoke("--format", "json", "workflow", "status", "sess-1")
    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "completed"


def test_workflow_continue_declined(invoke, write_credentials) -> None:
    write_credentials()
    with patch("cli.commands.workflow.require_client", return_value=MagicMock()):
        with patch("cli.commands.workflow.typer.confirm", return_value=False):
            result = invoke("workflow", "continue", "sess-1")
    assert result.exit_code == int(ExitCode.ERROR)


def test_interview_generate_exists_with_wait(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.interview_prep.generate.return_value = {"status": "exists", "message": "Already there"}
    mock_client.interview_prep.show.return_value = {
        "has_interview_prep": True,
        "interview_prep": {"confidence_boosters": ["Ready"]},
    }
    with patch("cli.commands.interview.require_client", return_value=mock_client):
        result = invoke("interview", "generate", "sess-1", "--wait")
    assert result.exit_code == 0
    assert "Ready" in result.output or "exists" in result.output.lower()


def test_interview_generate_timeout(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.interview_prep.generate.return_value = {"status": "generating"}
    from applypilot_client.polling import InterviewPollTimeout

    with patch("cli.commands.interview.require_client", return_value=mock_client):
        with patch("cli.commands.interview.wait_for_interview_prep") as wait_mock:
            wait_mock.side_effect = InterviewPollTimeout("sess-1", last_status={"is_generating": True})
            result = invoke("--format", "json", "interview", "generate", "sess-1", "--wait")
    assert result.exit_code == int(ExitCode.ERROR)
    assert json.loads(result.stdout)["error"] == "timeout"


def test_cv_start_cfg_6001(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.cv_optimizer.start.side_effect = ApiClientError(
        message="No API key",
        status_code=422,
        error_code="CFG_6001",
        exit_code=ExitCode.ERROR,
    )
    with patch("cli.commands.cv.require_client", return_value=mock_client):
        result = invoke("cv", "start", "sess-1")
    assert result.exit_code != 0
    assert "api-key" in result.output.lower() or "API key" in result.output


def test_cv_start_wait_timeout(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.cv_optimizer.start.return_value = {"session_id": "sess-1", "status": "started"}
    from applypilot_client.polling import CvPollTimeout

    with patch("cli.commands.cv.require_client", return_value=mock_client):
        with patch("cli.commands.cv.wait_for_cv_optimization") as wait_mock:
            wait_mock.side_effect = CvPollTimeout("sess-1", last_status={"is_running": True})
            result = invoke("--format", "json", "cv", "start", "sess-1", "--wait")
    assert result.exit_code == int(ExitCode.ERROR)


def test_profile_resume_show_requires_out_human(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.profile.download_resume.return_value = (b"%PDF", {})
    with patch("cli.commands.profile.require_client", return_value=mock_client):
        result = invoke("profile", "resume", "show")
    assert result.exit_code == int(ExitCode.ERROR)
    assert "--out" in result.output.lower()


def test_profile_api_key_status_server_key(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.profile.api_key_status.return_value = {
        "has_user_key": False,
        "server_has_key": True,
        "use_vertex_ai": False,
    }
    with patch("cli.commands.profile.require_client", return_value=mock_client):
        result = invoke("profile", "api-key", "status")
    assert result.exit_code == 0
    assert "vertex" in result.output.lower()


@pytest.mark.parametrize("tool", ["thank-you", "followup", "salary-coach", "rejection-analysis", "reference-request", "job-comparison"])
def test_tools_schema_all(invoke, tool: str) -> None:
    result = invoke("tools", "schema", tool)
    assert result.exit_code == 0
    json.loads(result.output)
