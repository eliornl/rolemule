"""Tests for applypilot profile commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from applypilot_client.errors import ExitCode


def test_profile_show(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.profile.show.return_value = {"user_info": {"email": "user@example.com"}}

    with patch("cli.commands.profile.require_client", return_value=mock_client):
        result = invoke("--format", "json", "profile", "show")
    assert result.exit_code == 0
    assert json.loads(result.stdout)["user_info"]["email"] == "user@example.com"


def test_profile_show_requires_auth(invoke) -> None:
    result = invoke("--format", "json", "profile", "show")
    assert result.exit_code == int(ExitCode.AUTH_OR_PROFILE)


def test_set_basic_info_from_flags(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.profile.update_basic_info.return_value = {"updated": True}

    with patch("cli.commands.profile.require_client", return_value=mock_client):
        result = invoke(
            "profile",
            "set",
            "basic-info",
            "--city",
            "Austin",
            "--state",
            "TX",
            "--country",
            "USA",
            "--title",
            "Engineer",
            "--years",
            "5",
            "--summary",
            "Experienced builder.",
        )
    assert result.exit_code == 0
    mock_client.profile.update_basic_info.assert_called_once()
    payload = mock_client.profile.update_basic_info.call_args[0][0]
    assert payload["city"] == "Austin"
    assert payload["years_experience"] == 5


def test_set_basic_info_from_file(invoke, write_credentials, tmp_path: Path) -> None:
    write_credentials()
    data_file = tmp_path / "basic.json"
    data_file.write_text(
        json.dumps(
            {
                "city": "NYC",
                "state": "NY",
                "country": "USA",
                "professional_title": "PM",
                "years_experience": 3,
                "summary": "Product leader.",
            }
        ),
        encoding="utf-8",
    )
    mock_client = MagicMock()
    mock_client.profile.update_basic_info.return_value = {}

    with patch("cli.commands.profile.require_client", return_value=mock_client):
        result = invoke("profile", "set", "basic-info", "--file", str(data_file))
    assert result.exit_code == 0
    assert mock_client.profile.update_basic_info.call_args[0][0]["city"] == "NYC"


def test_resume_upload(invoke, write_credentials, tmp_path: Path) -> None:
    write_credentials()
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4 test")
    mock_client = MagicMock()
    mock_client.profile.parse_resume.return_value = {"skills_extracted": 3}

    with patch("cli.commands.profile.require_client", return_value=mock_client):
        result = invoke("profile", "resume", "upload", str(resume))
    assert result.exit_code == 0
    mock_client.profile.parse_resume.assert_called_once_with(str(resume))


def test_api_key_set_uses_getpass(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.profile.api_key_set.return_value = {"has_user_key": True}

    with patch("cli.commands.profile.require_client", return_value=mock_client):
        with patch("cli.commands.profile.getpass.getpass", return_value="Gsk-test-key-1234567890"):
            with patch("cli.commands.profile._require_tty_for_secret"):
                result = invoke("profile", "api-key", "set")
    assert result.exit_code == 0
    mock_client.profile.api_key_set.assert_called_once_with("Gsk-test-key-1234567890")


def test_clear_data_without_confirm_fails(invoke, write_credentials) -> None:
    write_credentials()
    result = invoke("profile", "clear-data")
    assert result.exit_code == int(ExitCode.ERROR)
    assert "confirm" in result.output.lower()


def test_clear_data_with_confirm(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.profile.clear_data.return_value = {"cleared": True}

    with patch("cli.commands.profile.require_client", return_value=mock_client):
        result = invoke("profile", "clear-data", "--confirm")
    assert result.exit_code == 0
    mock_client.profile.clear_data.assert_called_once()


def test_delete_account_prompts_password(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.profile.delete_account.return_value = {"deleted": True}

    with patch("cli.commands.profile.require_client", return_value=mock_client):
        with patch("cli.commands.profile.getpass.getpass", return_value="secret"):
            with patch("cli.commands.profile._require_tty_for_secret"):
                result = invoke("profile", "delete-account", "--confirm")
    assert result.exit_code == 0
    mock_client.profile.delete_account.assert_called_once_with("secret")


def test_work_experience_stdin(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.profile.update_work_experience.return_value = {}

    payload = json.dumps([{"company": "Co", "job_title": "Dev", "start_date": "2020-01"}])
    with patch("cli.commands.profile.require_client", return_value=mock_client):
        result = invoke("profile", "set", "work-experience", "--file", "-", input=payload)
    assert result.exit_code == 0
    sent = mock_client.profile.update_work_experience.call_args[0][0]
    assert "work_experience" in sent


def test_api_key_status_human_no_key(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.profile.api_key_status.return_value = {
        "has_user_key": False,
        "server_has_key": False,
        "use_vertex_ai": False,
    }

    with patch("cli.commands.profile.require_client", return_value=mock_client):
        result = invoke("profile", "api-key", "status")
    assert result.exit_code == 0
    assert "api-key set" in result.output.lower()
