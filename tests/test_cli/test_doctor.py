"""Tests for rolemule doctor command."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from rolemule_client.errors import ApiClientError


def test_doctor_json_ok(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.health.return_value = {"status": "healthy"}
    mock_client.verify_token.return_value = {
        "success": True,
        "email": "user@example.com",
        "profile_completed": True,
    }

    with patch("cli.commands.doctor.RoleMuleClient", return_value=mock_client):
        result = invoke("--format", "json", "--base-url", "http://localhost:8000", "doctor")
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert any(c["check"] == "server_health" and c["ok"] for c in payload["checks"])


def test_doctor_server_down(invoke, rolemule_home) -> None:
    mock_client = MagicMock()
    mock_client.health.side_effect = ApiClientError(message="Cannot connect", status_code=0)

    with patch("cli.commands.doctor.RoleMuleClient", return_value=mock_client):
        result = invoke("--format", "json", "--base-url", "http://localhost:8000", "doctor")
        assert result.exit_code == 1
        payload = json.loads(result.stdout)
        assert payload["ok"] is False


def test_version(invoke) -> None:
    result = invoke("version")
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.0.0"
