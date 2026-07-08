"""ASGI integration tests — CLI against real FastAPI app (requires Postgres)."""

from __future__ import annotations

import json
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set — skip ASGI CLI integration tests",
)


def test_doctor_health_against_asgi(invoke, patch_httpx_asgi) -> None:
    result = invoke("--format", "json", "--base-url", "http://localhost", "doctor")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    health = next(c for c in payload["checks"] if c["check"] == "server_health")
    assert health["ok"] is True


def test_auth_whoami_with_real_jwt(invoke, patch_httpx_asgi, cli_user_token, write_credentials) -> None:
    write_credentials(token=cli_user_token["token"], email=cli_user_token["email"])
    result = invoke("--format", "json", "--base-url", "http://localhost", "auth", "whoami")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload.get("success") is True
    assert payload.get("email") == cli_user_token["email"]


def test_profile_status_incomplete_user(invoke, patch_httpx_asgi, cli_user_token, write_credentials) -> None:
    write_credentials(token=cli_user_token["token"], email=cli_user_token["email"])
    result = invoke("--format", "json", "--base-url", "http://localhost", "profile", "status")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload.get("profile_completed") is False


def test_apps_list_requires_complete_profile(invoke, patch_httpx_asgi, cli_user_token, write_credentials) -> None:
    from applypilot_client.errors import ExitCode

    write_credentials(token=cli_user_token["token"], email=cli_user_token["email"])
    result = invoke("--format", "json", "--base-url", "http://localhost", "apps", "list")
    assert result.exit_code == int(ExitCode.AUTH_OR_PROFILE)


def test_tools_followup_stages_authenticated(invoke, patch_httpx_asgi, cli_user_token, write_credentials) -> None:
    write_credentials(token=cli_user_token["token"], email=cli_user_token["email"])
    result = invoke("--format", "json", "--base-url", "http://localhost", "tools", "followup-stages")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert "stages" in payload


def test_pat_create_and_whoami(invoke, patch_httpx_asgi, cli_user_token, write_credentials, applypilot_home) -> None:
    write_credentials(token=cli_user_token["token"], email=cli_user_token["email"])
    create = invoke(
        "--format",
        "json",
        "--base-url",
        "http://localhost",
        "auth",
        "token",
        "create",
        "--name",
        "integration-test",
    )
    assert create.exit_code == 0, create.output
    pat_body = json.loads(create.stdout)
    assert pat_body["token"].startswith("ap_pat_")

    from cli.config import Credentials, save_credentials

    save_credentials(
        Credentials(
            access_token=pat_body["token"],
            email=cli_user_token["email"],
            saved_at="2026-07-08T00:00:00Z",
        )
    )
    whoami = invoke("--format", "json", "--base-url", "http://localhost", "auth", "whoami")
    assert whoami.exit_code == 0, whoami.output
    assert json.loads(whoami.stdout).get("email") == cli_user_token["email"]
