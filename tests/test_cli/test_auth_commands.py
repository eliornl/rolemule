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
