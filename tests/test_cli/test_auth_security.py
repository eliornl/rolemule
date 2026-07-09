"""Security and credential invariant tests for auth commands."""

from __future__ import annotations

import os
import stat
from unittest.mock import MagicMock, patch


from applypilot_client.errors import ApiClientError
from cli.config import credentials_path, load_credentials


def test_logout_clears_credentials_when_api_fails(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.auth.logout.side_effect = ApiClientError("Server error", status_code=500)

    with patch("cli.commands.auth.make_client", return_value=mock_client):
        result = invoke("auth", "logout")
    assert result.exit_code == 0
    assert load_credentials() is None


def test_login_requires_tty(invoke) -> None:
    with patch("cli.commands.auth.sys.stdin.isatty", return_value=False):
        result = invoke("auth", "login", "--email", "u@example.com")
    assert result.exit_code != 0
    assert "interactive terminal" in result.stderr.lower()


def test_register_requires_tty(invoke) -> None:
    with patch("cli.commands.auth.sys.stdin.isatty", return_value=False):
        result = invoke("auth", "register", "--name", "User", "--email", "u@example.com")
    assert result.exit_code != 0


def test_token_set_requires_tty_without_stdin(invoke) -> None:
    with patch("cli.commands.auth.sys.stdin.isatty", return_value=False):
        result = invoke("auth", "token", "set")
    assert result.exit_code != 0


def test_login_saves_credentials_with_mode_0600(invoke, applypilot_home) -> None:
    mock_client = MagicMock()
    mock_client.auth.login.return_value = {
        "access_token": "jwt.login.token",
        "user": {"email": "user@example.com"},
    }

    with patch("cli.commands.auth.make_client", return_value=mock_client):
        with patch("cli.commands.auth.getpass.getpass", return_value="secret"):
            with patch("cli.commands.auth._require_tty_for_secret"):
                result = invoke("auth", "login", "--email", "user@example.com")
    assert result.exit_code == 0
    cred_file = credentials_path()
    assert cred_file.is_file()
    assert stat.S_IMODE(os.stat(cred_file).st_mode) == 0o600


def test_register_never_persists_token_even_if_present(invoke, applypilot_home) -> None:
    mock_client = MagicMock()
    mock_client.auth.register.return_value = {
        "access_token": "must-not-save",
        "user": {"email": "new@example.com"},
    }

    with patch("cli.commands.auth.make_client", return_value=mock_client):
        with patch("cli.commands.auth.getpass.getpass", side_effect=["pw", "pw"]):
            with patch("cli.commands.auth._require_tty_for_secret"):
                result = invoke("auth", "register", "--name", "New", "--email", "new@example.com")
    assert result.exit_code == 0
    assert load_credentials() is None
