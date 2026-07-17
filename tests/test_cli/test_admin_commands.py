"""Tests for rolemule admin commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from rolemule_client.errors import ApiClientError, ExitCode
from cli.admin_visibility import admin_help_visible


def test_admin_hidden_from_default_help(invoke) -> None:
    result = invoke("--help")
    assert result.exit_code == 0
    assert "admin" not in result.output


def test_admin_help_visible_when_env_set(monkeypatch) -> None:
    monkeypatch.setenv("ROLEMULE_ADMIN", "1")
    assert admin_help_visible() is True
    monkeypatch.delenv("ROLEMULE_ADMIN", raising=False)
    assert admin_help_visible() is False


def test_admin_maintenance_show_forbidden(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.admin.maintenance_status.side_effect = ApiClientError(
        message="Admin access required",
        status_code=403,
        error_code="AUTH_1003",
        exit_code=ExitCode.ERROR,
    )

    with patch("cli.commands.admin.require_client", return_value=mock_client):
        result = invoke("admin", "maintenance", "show")
    assert result.exit_code != 0
    assert "Admin" in result.output or "403" in result.output or "required" in result.output.lower()


def test_admin_maintenance_show(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.admin.maintenance_status.return_value = {
        "enabled": False,
        "message": None,
        "estimated_end": None,
    }

    with patch("cli.commands.admin.require_client", return_value=mock_client):
        result = invoke("admin", "maintenance", "show")
    assert result.exit_code == 0
    assert "OFF" in result.output


def test_admin_maintenance_on_requires_confirm(invoke, write_credentials) -> None:
    write_credentials()
    result = invoke("admin", "maintenance", "on")
    assert result.exit_code == int(ExitCode.ERROR)


def test_admin_maintenance_on_with_confirm(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.admin.set_maintenance.return_value = {
        "enabled": True,
        "message": "Deploying",
        "estimated_end": "30m",
    }

    with patch("cli.commands.admin.require_client", return_value=mock_client):
        result = invoke(
            "admin",
            "maintenance",
            "on",
            "--confirm",
            "--message",
            "Deploying",
            "--estimated-end",
            "30m",
        )
    assert result.exit_code == 0
    assert "ON" in result.output
    mock_client.admin.set_maintenance.assert_called_once_with(
        enabled=True,
        message="Deploying",
        estimated_end="30m",
    )


def test_admin_maintenance_off_with_confirm(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.admin.clear_maintenance.return_value = {"message": "Maintenance mode disabled successfully"}

    with patch("cli.commands.admin.require_client", return_value=mock_client):
        result = invoke("admin", "maintenance", "off", "--confirm")
    assert result.exit_code == 0
    mock_client.admin.clear_maintenance.assert_called_once()


def test_admin_metrics_json(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.admin.metrics.return_value = {
        "generated_at": "2026-07-08T16:00:00+00:00",
        "users": {"total": 10, "new_last_30d": 2, "active_last_7d": 5, "email_verified": 9},
        "workflows": {
            "total": 20,
            "completed": 15,
            "failed": 2,
            "in_progress": 3,
            "success_rate_pct": 75.0,
        },
        "applications": {"total": 18, "new_last_30d": 4},
    }

    with patch("cli.commands.admin.require_client", return_value=mock_client):
        result = invoke("--format", "json", "admin", "metrics")
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["users"]["total"] == 10


def test_admin_cache_stats(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.admin.cache_stats.return_value = {"status": "ok", "redis_connected": True}

    with patch("cli.commands.admin.require_client", return_value=mock_client):
        result = invoke("admin", "cache-stats")
    assert result.exit_code == 0
