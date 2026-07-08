"""Extended doctor command tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from applypilot_client.errors import ApiClientError


def test_doctor_fails_on_loose_credentials_permissions(invoke, write_credentials) -> None:
    cred_path = write_credentials()
    cred_path.chmod(0o644)

    mock_client = MagicMock()
    mock_client.health.return_value = {"status": "healthy"}
    mock_client.verify_token.return_value = {
        "success": True,
        "email": "user@example.com",
        "profile_completed": True,
    }

    with patch("cli.commands.doctor.ApplyPilotClient", return_value=mock_client):
        result = invoke("--format", "json", "doctor")
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    perms = next(c for c in payload["checks"] if c["check"] == "credentials_permissions")
    assert perms["ok"] is False


def test_doctor_human_shows_masked_token(invoke, write_credentials) -> None:
    write_credentials(token="abcdefghijklmnop")
    mock_client = MagicMock()
    mock_client.health.return_value = {"status": "healthy"}
    mock_client.verify_token.return_value = {
        "success": True,
        "email": "user@example.com",
        "profile_completed": True,
    }

    with patch("cli.commands.doctor.ApplyPilotClient", return_value=mock_client):
        result = invoke("doctor")
    assert result.exit_code == 0
    assert "abcd...mnop" in result.stdout


def test_doctor_reports_invalid_token(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.health.return_value = {"status": "healthy"}
    mock_client.verify_token.side_effect = ApiClientError("Invalid token", status_code=401)

    with patch("cli.commands.doctor.ApplyPilotClient", return_value=mock_client):
        result = invoke("--format", "json", "doctor")
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    auth_check = next(c for c in payload["checks"] if c["check"] == "auth_token")
    assert auth_check["ok"] is False


def test_doctor_pat_token_type_and_metadata(invoke, write_credentials) -> None:
    write_credentials(token="ap_pat_test_secret_value_here")
    mock_client = MagicMock()
    mock_client.health.return_value = {"status": "healthy"}
    mock_client.verify_token.return_value = {
        "success": True,
        "email": "user@example.com",
        "profile_completed": True,
    }
    mock_client.auth.list_pats.return_value = {
        "tokens": [
            {
                "id": "pat-1",
                "name": "CI",
                "token_prefix": "ap_pat_test",
                "active": True,
                "expires_at": "2026-12-01T00:00:00Z",
            }
        ]
    }

    with patch("cli.commands.doctor.ApplyPilotClient", return_value=mock_client):
        result = invoke("--format", "json", "doctor")
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    auth = next(c for c in payload["checks"] if c["check"] == "auth_token")
    assert "token_type=pat" in auth["detail"]
    pat_meta = next(c for c in payload["checks"] if c["check"] == "pat_metadata")
    assert "expires_at=" in pat_meta["detail"]
