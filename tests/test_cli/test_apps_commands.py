"""Tests for applypilot apps commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from applypilot_client.errors import ExitCode


def test_apps_list_with_search(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.applications.list.return_value = {
        "applications": [
            {
                "id": "app-1",
                "job_title": "Python Engineer",
                "company_name": "Acme",
                "status": "completed",
                "match_score": 0.85,
            }
        ],
        "total": 1,
        "page": 1,
        "per_page": 20,
        "has_next": False,
        "has_prev": False,
    }

    with patch("cli.commands.applications.require_client", return_value=mock_client):
        result = invoke("apps", "list", "--search", "python")
    assert result.exit_code == 0
    mock_client.applications.list.assert_called_once()
    assert mock_client.applications.list.call_args.kwargs["search"] == "python"
    assert "Python Engineer" in result.output


def test_apps_list_json(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.applications.list.return_value = {"applications": [], "total": 0}

    with patch("cli.commands.applications.require_client", return_value=mock_client):
        result = invoke("--format", "json", "apps", "list")
    assert result.exit_code == 0
    assert json.loads(result.stdout)["total"] == 0


def test_apps_stats(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.applications.stats.return_value = {
        "total": 5,
        "applied": 2,
        "interviews": 1,
        "response_rate": 50.0,
    }

    with patch("cli.commands.applications.require_client", return_value=mock_client):
        result = invoke("apps", "stats")
    assert result.exit_code == 0
    assert "Response rate" in result.output


def test_apps_status_update(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.applications.update_status.return_value = {"id": "app-1", "status": "applied"}

    with patch("cli.commands.applications.require_client", return_value=mock_client):
        result = invoke("apps", "status", "app-1", "applied")
    assert result.exit_code == 0
    mock_client.applications.update_status.assert_called_once_with("app-1", "applied")


def test_apps_delete_requires_confirm(invoke, write_credentials) -> None:
    write_credentials()
    result = invoke("apps", "delete", "app-1")
    assert result.exit_code == int(ExitCode.ERROR)
    assert "confirm" in result.output.lower()


def test_apps_delete_with_confirm(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.applications.delete.return_value = {"message": "Application deleted successfully"}

    with patch("cli.commands.applications.require_client", return_value=mock_client):
        result = invoke("apps", "delete", "app-1", "--confirm")
    assert result.exit_code == 0
    mock_client.applications.delete.assert_called_once_with("app-1")


def test_apps_download_writes_file(invoke, write_credentials, tmp_path: Path) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.applications.download.return_value = (
        b"Application report content",
        {"content-disposition": 'attachment; filename="Acme_Engineer_Application.txt"'},
    )
    out = tmp_path / "report.txt"

    with patch("cli.commands.applications.require_client", return_value=mock_client):
        result = invoke("apps", "download", "app-1", "--out", str(out))
    assert result.exit_code == 0
    assert out.read_bytes() == b"Application report content"


def test_apps_notes_from_file(invoke, write_credentials, tmp_path: Path) -> None:
    write_credentials()
    notes_file = tmp_path / "notes.txt"
    notes_file.write_text("Follow up next week", encoding="utf-8")
    mock_client = MagicMock()
    mock_client.applications.update_notes.return_value = {"id": "app-1", "notes": "Follow up next week"}

    with patch("cli.commands.applications.require_client", return_value=mock_client):
        result = invoke("apps", "notes", "app-1", "--file", str(notes_file))
    assert result.exit_code == 0
    mock_client.applications.update_notes.assert_called_once_with("app-1", "Follow up next week")


def test_apps_show(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.applications.get.return_value = {
        "id": "app-1",
        "job_title": "Engineer",
        "company_name": "Acme",
        "status": "completed",
        "match_score": 0.85,
        "workflow_session_id": "sess-1",
    }

    with patch("cli.commands.applications.require_client", return_value=mock_client):
        result = invoke("apps", "show", "app-1")
    assert result.exit_code == 0
    assert "Engineer" in result.output
    assert "sess-1" in result.output
    mock_client.applications.get.assert_called_once_with("app-1")
