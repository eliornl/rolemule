"""Parametrized validation and confirmation error paths."""

from __future__ import annotations

import pytest

from rolemule_client.errors import ExitCode


@pytest.mark.parametrize(
    "args,expected_fragment",
    [
        (("profile", "set", "notifications"), "notification flag"),
        (("profile", "workflow-preferences", "set"), "preference flag"),
        (("apps", "notes", "app-1"), "notes"),
        (("apps", "delete", "app-1"), "confirm"),
        (("profile", "clear-data"), "confirm"),
        (("profile", "delete-account"), "confirm"),
        (("cv", "clear", "sess-1"), "confirm"),
        (("interview", "delete", "sess-1"), "confirm"),
        (
            ("tools", "thank-you"),
            "interviewer",
        ),
        (
            ("tools", "followup"),
            "stage",
        ),
        (
            ("tools", "salary-coach"),
            "title",
        ),
        (
            ("tools", "reference-request"),
            "name",
        ),
        (
            ("tools", "job-comparison"),
            "file",
        ),
        (
            ("tools", "rejection-analysis"),
            "email",
        ),
    ],
    ids=[
        "profile-notifications-no-flags",
        "profile-workflow-prefs-no-flags",
        "apps-notes-missing",
        "apps-delete-no-confirm",
        "profile-clear-no-confirm",
        "profile-delete-no-confirm",
        "cv-clear-no-confirm",
        "interview-delete-no-confirm",
        "tools-thank-you-missing",
        "tools-followup-missing",
        "tools-salary-missing",
        "tools-reference-missing",
        "tools-job-comparison-missing",
        "tools-rejection-missing",
    ],
)
def test_validation_errors(invoke, write_credentials, args: tuple[str, ...], expected_fragment: str) -> None:
    write_credentials()
    result = invoke(*args)
    assert result.exit_code != 0
    combined = (result.stdout + result.stderr).lower()
    assert expected_fragment in combined


def test_workflow_analyze_missing_input(invoke, write_credentials) -> None:
    write_credentials()
    result = invoke("workflow", "analyze")
    assert result.exit_code != 0


def test_profile_api_key_set_empty_key(invoke, write_credentials, monkeypatch: pytest.MonkeyPatch) -> None:
    write_credentials()
    monkeypatch.setattr("cli.commands.profile._require_tty_for_secret", lambda *_: None)
    result = invoke("profile", "api-key", "set", "--api-key", "   ")
    assert result.exit_code == int(ExitCode.ERROR)
    assert "empty" in result.stderr.lower()
