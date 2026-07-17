"""Tests for rolemule cv commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from rolemule_client.errors import ApiClientError, ExitCode


def test_cv_start_wait(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.cv_optimizer.start.return_value = {
        "session_id": "sess-1",
        "status": "started",
        "message": "Started",
    }
    mock_client.cv_optimizer.show.return_value = {
        "session_id": "sess-1",
        "has_result": True,
        "result": {
            "best_score": 8.5,
            "status": "completed",
            "iteration_history": [{"iteration": 1, "score": 7.5}, {"iteration": 2, "score": 8.5}],
        },
    }

    with patch("cli.commands.cv.require_client", return_value=mock_client):
        with patch("cli.commands.cv.wait_for_cv_optimization") as wait_mock:
            wait_mock.return_value = {"session_id": "sess-1", "has_result": True, "is_running": False}
            result = invoke("cv", "start", "sess-1", "--wait")
    assert result.exit_code == 0
    assert "8.5" in result.output


def test_cv_start_already_running_409(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.cv_optimizer.start.side_effect = ApiClientError(
        message="CV optimization is already running for this session.",
        status_code=409,
        error_code="RES_3003",
        exit_code=ExitCode.ERROR,
    )

    with patch("cli.commands.cv.require_client", return_value=mock_client):
        result = invoke("cv", "start", "sess-1")
    assert result.exit_code != 0


def test_cv_download_saves_file(invoke, write_credentials, tmp_path: Path) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.cv_optimizer.download_cv.return_value = (
        b"odt-bytes",
        {"content-disposition": 'attachment; filename="optimized-cv.odt"'},
    )
    out = tmp_path / "cv.odt"

    with patch("cli.commands.cv.require_client", return_value=mock_client):
        result = invoke("cv", "download", "sess-1", "--out", str(out))
    assert result.exit_code == 0
    assert out.read_bytes() == b"odt-bytes"


def test_cv_download_rate_limit(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.cv_optimizer.download_cv.side_effect = ApiClientError(
        message="Rate limit exceeded",
        status_code=429,
        error_code="RATE_4001",
        exit_code=ExitCode.RATE_LIMITED,
    )

    with patch("cli.commands.cv.require_client", return_value=mock_client):
        result = invoke("cv", "download", "sess-1")
    assert result.exit_code == int(ExitCode.RATE_LIMITED)


def test_cv_clear_requires_confirm(invoke, write_credentials) -> None:
    write_credentials()
    result = invoke("cv", "clear", "sess-1")
    assert result.exit_code == int(ExitCode.ERROR)


def test_cv_show_partial_result(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.cv_optimizer.show.return_value = {
        "session_id": "sess-1",
        "has_result": True,
        "result": {"status": "partial", "best_score": 7.8, "stop_reason": "api_rate_limit"},
    }

    with patch("cli.commands.cv.require_client", return_value=mock_client):
        result = invoke("cv", "show", "sess-1")
    assert result.exit_code == 0
    assert "Partial result" in result.output


def test_cv_show_json(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.cv_optimizer.show.return_value = {"session_id": "sess-1", "has_result": False, "result": None}

    with patch("cli.commands.cv.require_client", return_value=mock_client):
        result = invoke("--format", "json", "cv", "show", "sess-1")
    assert result.exit_code == 0
    assert json.loads(result.stdout)["has_result"] is False
