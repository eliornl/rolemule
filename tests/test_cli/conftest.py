"""Shared fixtures for CLI tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli.main import app


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def applypilot_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ~/.applypilot to a temp directory."""
    home = tmp_path / "applypilot_home"
    home.mkdir()
    monkeypatch.setenv("APPLYPILOT_CONFIG_DIR", str(home))
    return home


@pytest.fixture
def invoke(cli_runner: CliRunner):
    def _invoke(*args: str, env: dict | None = None, input: str | None = None):
        return cli_runner.invoke(app, list(args), env=env, input=input)

    return _invoke


@pytest.fixture
def write_credentials(applypilot_home: Path):
    def _write(token: str = "test.jwt.token", email: str = "user@example.com") -> Path:
        path = applypilot_home / "credentials.json"
        path.write_text(
            json.dumps(
                {
                    "access_token": token,
                    "token_type": "bearer",
                    "email": email,
                    "saved_at": "2026-07-08T12:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        path.chmod(0o600)
        return path

    return _write
