"""Tests for applypilot auth commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from cli.config import load_credentials


def test_login_saves_credentials(invoke, applypilot_home) -> None:
    mock_client = MagicMock()
    mock_client.auth.login.return_value = {
        "access_token": "jwt.login.token",
        "token_type": "bearer",
        "expires_in": 3600,
        "user": {"email": "user@example.com"},
        "profile_completed": True,
    }

    with patch("cli.commands.auth.make_client", return_value=mock_client):
        with patch("cli.commands.auth.getpass.getpass", return_value="secret"):
            with patch("cli.commands.auth._require_tty_for_secret"):
                result = invoke(
                    "--format",
                    "json",
                    "auth",
                    "login",
                    "--email",
                    "user@example.com",
                )
    assert result.exit_code == 0, result.output
    creds = load_credentials()
    assert creds is not None
    assert creds.access_token == "jwt.login.token"


def test_register_does_not_save_token(invoke, applypilot_home) -> None:
    mock_client = MagicMock()
    mock_client.auth.register.return_value = {
        "access_token": "should-not-save",
        "user": {"email": "new@example.com"},
    }

    with patch("cli.commands.auth.make_client", return_value=mock_client):
        with patch("cli.commands.auth.getpass.getpass", side_effect=["pw", "pw"]):
            with patch("cli.commands.auth._require_tty_for_secret"):
                result = invoke(
                    "auth",
                    "register",
                    "--name",
                    "New User",
                    "--email",
                    "new@example.com",
                )
    assert result.exit_code == 0
    assert load_credentials() is None


def test_verify_code_saves_token(invoke, applypilot_home) -> None:
    mock_client = MagicMock()
    mock_client.auth.verify_code.return_value = {
        "access_token": "jwt.verify.token",
        "message": "Verified",
        "user": {"email": "new@example.com"},
    }

    with patch("cli.commands.auth.make_client", return_value=mock_client):
        result = invoke(
            "auth",
            "verify-code",
            "--email",
            "new@example.com",
            "--code",
            "123456",
        )
    assert result.exit_code == 0
    assert load_credentials().access_token == "jwt.verify.token"


def test_logout_clears_credentials(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()

    with patch("cli.commands.auth.make_client", return_value=mock_client):
        result = invoke("auth", "logout")
    assert result.exit_code == 0
    assert load_credentials() is None


def test_whoami_without_token(invoke) -> None:
    result = invoke("--format", "json", "auth", "whoami")
    assert result.exit_code == 2
    assert json.loads(result.stdout)["authenticated"] is False


def test_token_set_from_stdin(invoke, applypilot_home) -> None:
    result = invoke("auth", "token", "set", "--from-stdin", input="my.jwt.token\n")
    assert result.exit_code == 0
    assert load_credentials().access_token == "my.jwt.token"


def test_token_show_masked(invoke, write_credentials) -> None:
    write_credentials(token="abcdefghijklmnop")
    result = invoke("auth", "token", "show")
    assert result.exit_code == 0
    assert "abcd...mnop" in result.stdout


def test_pat_create_shows_secret_once(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.auth.create_pat.return_value = {
        "id": "pat-1",
        "name": "Automation",
        "token_prefix": "ap_pat_ab",
        "token": "ap_pat_full_secret",
        "created_at": "2026-07-08T00:00:00Z",
    }

    with patch("cli.commands.auth.make_client", return_value=mock_client):
        result = invoke("auth", "token", "create", "--name", "Automation")
    assert result.exit_code == 0
    assert "ap_pat_full_secret" in result.output
    mock_client.auth.create_pat.assert_called_once_with("Automation", expires_days=90)


def test_pat_create_save_writes_credentials(invoke, write_credentials, applypilot_home) -> None:
    write_credentials(token="jwt.for.create", email="user@example.com")
    mock_client = MagicMock()
    mock_client.auth.create_pat.return_value = {
        "id": "pat-2",
        "name": "CI",
        "token_prefix": "ap_pat_cd",
        "token": "ap_pat_saved_secret",
        "created_at": "2026-07-08T00:00:00Z",
    }

    with patch("cli.commands.auth.make_client", return_value=mock_client):
        result = invoke("auth", "token", "create", "--name", "CI", "--save")
    assert result.exit_code == 0
    assert "saved" in result.output.lower()
    from cli.config import load_credentials

    creds = load_credentials()
    assert creds is not None
    assert creds.access_token == "ap_pat_saved_secret"
    assert creds.email == "user@example.com"


def test_pat_list(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.auth.list_pats.return_value = {
        "tokens": [{"id": "pat-1", "name": "CLI", "token_prefix": "ap_pat_ab", "active": True}],
    }

    with patch("cli.commands.auth.make_client", return_value=mock_client):
        result = invoke("auth", "token", "list")
    assert result.exit_code == 0
    assert "ap_pat_ab" in result.output


def test_pat_revoke(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.auth.revoke_pat.return_value = {"message": "Token revoked", "id": "pat-1"}

    with patch("cli.commands.auth.make_client", return_value=mock_client):
        result = invoke("auth", "token", "revoke", "pat-1")
    assert result.exit_code == 0
    mock_client.auth.revoke_pat.assert_called_once_with("pat-1")


def test_oauth_status_enabled(invoke) -> None:
    mock_client = MagicMock()
    mock_client.auth.oauth_status.return_value = {"google_oauth_enabled": True}

    with patch("cli.commands.auth.make_client", return_value=mock_client):
        result = invoke("auth", "oauth-status")
    assert result.exit_code == 0
    assert "enabled" in result.output.lower()


def test_oauth_status_disabled_json(invoke) -> None:
    import json

    mock_client = MagicMock()
    mock_client.auth.oauth_status.return_value = {"google_oauth_enabled": False}

    with patch("cli.commands.auth.make_client", return_value=mock_client):
        result = invoke("--format", "json", "auth", "oauth-status")
    assert result.exit_code == 0
    assert json.loads(result.stdout)["google_oauth_enabled"] is False
