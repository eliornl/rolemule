"""Cross-cutting CLI error-path tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from rolemule_client.errors import ApiClientError, ExitCode


@pytest.mark.parametrize(
    "module,patch_target,args,error",
    [
        (
            "cli.commands.applications",
            "require_client",
            ("apps", "list"),
            ApiClientError("Profile incomplete", 403, "AUTH_1006", exit_code=ExitCode.AUTH_OR_PROFILE),
        ),
        (
            "cli.commands.profile",
            "require_client",
            ("profile", "show"),
            ApiClientError("Profile incomplete", 403, "AUTH_1006", exit_code=ExitCode.AUTH_OR_PROFILE),
        ),
        (
            "cli.commands.extension",
            "require_client",
            ("extension", "autofill", "map", "--file", "PLACEHOLDER"),
            ApiClientError("Profile incomplete", 403, "AUTH_1006", exit_code=ExitCode.AUTH_OR_PROFILE),
        ),
        (
            "cli.commands.cv",
            "require_client",
            ("cv", "start", "sess-1"),
            ApiClientError("No API key", 422, "CFG_6001", exit_code=ExitCode.ERROR),
        ),
        (
            "cli.commands.tools",
            "require_client",
            (
                "tools",
                "thank-you",
                "--interviewer",
                "Jane",
                "--interview-type",
                "video",
                "--company",
                "Acme",
                "--title",
                "Eng",
            ),
            ApiClientError("Rate limited", 429, "RATE_4001", exit_code=ExitCode.RATE_LIMITED),
        ),
    ],
)
def test_error_exit_codes(
    module,
    patch_target,
    args,
    error,
    invoke,
    write_credentials,
    tmp_path,
) -> None:
    write_credentials()
    mock_client = MagicMock()
    # Set side effect on the resource that will be called
    if args[0] == "apps":
        mock_client.applications.list.side_effect = error
    elif args[0] == "profile":
        mock_client.profile.show.side_effect = error
    elif args[0] == "extension":
        from tests.test_cli.helpers import write_json_file

        body = {
            "page_url": "https://careers.example.com/apply",
            "fields": [{"field_uid": "0", "tag": "input", "label_text": "Name"}],
        }
        path = write_json_file(tmp_path / "f.json", body)
        args = tuple(str(path) if a == "PLACEHOLDER" else a for a in args)
        mock_client.extension.autofill_map.side_effect = error
    elif args[0] == "cv":
        mock_client.cv_optimizer.start.side_effect = error
    elif args[0] == "tools":
        mock_client.tools.thank_you.side_effect = error

    full_patch = f"{module}.{patch_target}"
    with patch(full_patch, return_value=mock_client):
        result = invoke(*args)

    if error.error_code == "RES_3002":
        assert result.exit_code == 0
    elif error.error_code == "RATE_4001":
        assert result.exit_code == int(ExitCode.RATE_LIMITED)
    elif error.status_code in (401, 403):
        assert result.exit_code == int(ExitCode.AUTH_OR_PROFILE)
    else:
        assert result.exit_code != 0


def test_workflow_invalid_section(invoke, write_credentials) -> None:
    write_credentials()
    with patch("cli.commands.workflow.require_client", return_value=MagicMock()):
        result = invoke("workflow", "analyze", "-", "--section", "invalid", input="job")
    assert result.exit_code == int(ExitCode.ERROR)


def test_profile_set_basic_info_missing_flags(invoke, write_credentials) -> None:
    write_credentials()
    with patch("cli.commands.profile.require_client", return_value=MagicMock()):
        result = invoke("profile", "set", "basic-info", "--city", "Austin")
    assert result.exit_code == int(ExitCode.ERROR)


def test_profile_set_skills_missing_input(invoke, write_credentials) -> None:
    write_credentials()
    result = invoke("profile", "set", "skills")
    assert result.exit_code == int(ExitCode.ERROR)


def test_apps_notes_missing_input(invoke, write_credentials) -> None:
    write_credentials()
    result = invoke("apps", "notes", "app-1")
    assert result.exit_code == int(ExitCode.ERROR)


def test_admin_maintenance_off_requires_confirm(invoke, write_credentials) -> None:
    write_credentials()
    result = invoke("admin", "maintenance", "off")
    assert result.exit_code == int(ExitCode.ERROR)


def test_extension_missing_page_url(invoke, write_credentials, tmp_path) -> None:
    write_credentials()
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"fields": [{"field_uid": "0", "tag": "input", "label_text": "X"}]}), encoding="utf-8")
    result = invoke("extension", "autofill", "map", "--file", str(path))
    assert result.exit_code != 0


def test_tools_thank_you_missing_flags(invoke, write_credentials) -> None:
    write_credentials()
    result = invoke("tools", "thank-you")
    assert result.exit_code != 0


def test_auth_refresh_without_login(invoke) -> None:
    result = invoke("auth", "refresh")
    assert result.exit_code == int(ExitCode.AUTH_OR_PROFILE)


def test_auth_whoami_logged_in(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.auth.verify.return_value = {"email": "user@example.com", "profile_completed": True}
    with patch("cli.commands.auth.make_client", return_value=mock_client):
        result = invoke("auth", "whoami")
    assert result.exit_code == 0
    assert "user@example.com" in result.output


def test_auth_refresh_persists_token(invoke, write_credentials, rolemule_home) -> None:
    write_credentials(token="old.jwt.token")
    mock_client = MagicMock()
    mock_client.auth.refresh.return_value = {"access_token": "new.jwt.token", "expires_in": 3600}
    with patch("cli.commands.auth.make_client", return_value=mock_client):
        result = invoke("auth", "refresh")
    assert result.exit_code == 0
    saved = json.loads((rolemule_home / "credentials.json").read_text())
    assert saved["access_token"] == "new.jwt.token"
