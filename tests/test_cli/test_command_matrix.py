"""Parametrized happy-path tests for CLI leaf commands."""

from __future__ import annotations

import json
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional
from unittest.mock import patch

import pytest

from tests.test_cli.helpers import build_mock_client, write_json_file


@dataclass
class CommandCase:
    id: str
    args: tuple[str, ...]
    patch_target: str
    needs_auth: bool = True
    input: Optional[str] = None
    extra_patches: dict[str, object] = field(default_factory=dict)


COMMAND_CASES: list[CommandCase] = [
    CommandCase("auth-whoami", ("auth", "whoami"), "cli.commands.auth.make_client"),
    CommandCase("auth-refresh", ("auth", "refresh"), "cli.commands.auth.make_client"),
    CommandCase("auth-logout", ("auth", "logout"), "cli.commands.auth.make_client"),
    CommandCase(
        "auth-verify-code",
        ("auth", "verify-code", "--email", "u@example.com", "--code", "123456"),
        "cli.commands.auth.make_client",
        needs_auth=False,
    ),
    CommandCase(
        "auth-resend",
        ("auth", "resend-verification", "--email", "u@example.com"),
        "cli.commands.auth.make_client",
        needs_auth=False,
    ),
    CommandCase("auth-verification-status", ("auth", "verification-status"), "cli.commands.auth.make_client"),
    CommandCase("auth-extension-status", ("auth", "extension-status"), "cli.commands.auth.make_client"),
    CommandCase("auth-email-status", ("auth", "email-status"), "cli.commands.auth.make_client", needs_auth=False),
    CommandCase("auth-oauth-status", ("auth", "oauth-status"), "cli.commands.auth.make_client", needs_auth=False),
    CommandCase(
        "auth-login",
        ("auth", "login", "--email", "user@example.com"),
        "cli.commands.auth.make_client",
        extra_patches={
            "cli.commands.auth.getpass.getpass": lambda *_: "secret",
            "cli.commands.auth._require_tty_for_secret": lambda *_: None,
        },
    ),
    CommandCase(
        "auth-register",
        ("auth", "register", "--name", "New", "--email", "new@example.com"),
        "cli.commands.auth.make_client",
        needs_auth=False,
        extra_patches={
            "cli.commands.auth.getpass.getpass": lambda *_: "pw",
            "cli.commands.auth._require_tty_for_secret": lambda *_: None,
        },
    ),
    CommandCase(
        "auth-token-set-flag",
        ("auth", "token", "set", "--token", "header.payload.sig"),
        "cli.commands.auth.make_client",
        needs_auth=False,
    ),
    CommandCase(
        "auth-change-password",
        ("auth", "change-password"),
        "cli.commands.auth.make_client",
        extra_patches={
            "cli.commands.auth.getpass.getpass": lambda *_: "pw",
            "cli.commands.auth._require_tty_for_secret": lambda *_: None,
        },
    ),
    CommandCase(
        "auth-token-set-stdin",
        ("auth", "token", "set", "--from-stdin"),
        "cli.commands.auth.make_client",
        needs_auth=False,
        input="header.payload.sig",
    ),
    CommandCase("auth-token-show", ("auth", "token", "show"), "cli.commands.auth.make_client"),
    CommandCase(
        "auth-token-create",
        ("auth", "token", "create", "--name", "Automation"),
        "cli.commands.auth.make_client",
    ),
    CommandCase("auth-token-list", ("auth", "token", "list"), "cli.commands.auth.make_client"),
    CommandCase(
        "auth-token-revoke",
        ("auth", "token", "revoke", "pat-1"),
        "cli.commands.auth.make_client",
    ),
    CommandCase("profile-show", ("profile", "show"), "cli.commands.profile.require_client"),
    CommandCase("profile-status", ("profile", "status"), "cli.commands.profile.require_client"),
    CommandCase("profile-complete", ("profile", "complete"), "cli.commands.profile.require_client"),
    CommandCase(
        "profile-set-preferences",
        ("profile", "set", "preferences", "--file", "-"),
        "cli.commands.profile.require_client",
        input=json.dumps({"salary_expectation_min": 100000}),
    ),
    CommandCase(
        "profile-set-basic-info",
        (
            "profile",
            "set",
            "basic-info",
            "--city",
            "Austin",
            "--state",
            "TX",
            "--country",
            "USA",
            "--title",
            "Engineer",
            "--years",
            "3",
            "--summary",
            "Builder.",
        ),
        "cli.commands.profile.require_client",
    ),
    CommandCase(
        "profile-set-work-experience",
        ("profile", "set", "work-experience", "--file", "-"),
        "cli.commands.profile.require_client",
        input=json.dumps([{"company": "Acme", "title": "Dev"}]),
    ),
    CommandCase(
        "profile-resume-show",
        ("--format", "json", "profile", "resume", "show"),
        "cli.commands.profile.require_client",
    ),
    CommandCase("profile-api-key-status", ("profile", "api-key", "status"), "cli.commands.profile.require_client"),
    CommandCase(
        "profile-api-key-set",
        ("profile", "api-key", "set", "--api-key", "Gsk-test-key"),
        "cli.commands.profile.require_client",
        extra_patches={"cli.commands.profile._require_tty_for_secret": lambda *_: None},
    ),
    CommandCase(
        "profile-clear-data",
        ("profile", "clear-data", "--confirm"),
        "cli.commands.profile.require_client",
    ),
    CommandCase(
        "profile-delete-account",
        ("profile", "delete-account", "--confirm"),
        "cli.commands.profile.require_client",
        extra_patches={
            "cli.commands.profile.getpass.getpass": lambda *_: "pw",
            "cli.commands.profile._require_tty_for_secret": lambda *_: None,
        },
    ),
    CommandCase(
        "profile-set-education",
        ("profile", "set", "education", "--file", "-"),
        "cli.commands.profile.require_client",
        input=json.dumps([{"institution": "MIT"}]),
    ),
    CommandCase(
        "profile-set-skills",
        ("profile", "set", "skills", "--skills", "Python,SQL"),
        "cli.commands.profile.require_client",
    ),
    CommandCase(
        "profile-set-notifications",
        ("profile", "set", "notifications", "--email-notifications"),
        "cli.commands.profile.require_client",
    ),
    CommandCase("profile-resume-delete", ("profile", "resume", "delete", "--confirm"), "cli.commands.profile.require_client"),
    CommandCase("profile-api-key-delete", ("profile", "api-key", "delete", "--confirm"), "cli.commands.profile.require_client"),
    CommandCase(
        "profile-api-key-validate",
        ("profile", "api-key", "validate"),
        "cli.commands.profile.require_client",
        extra_patches={
            "cli.commands.profile.getpass.getpass": lambda *_: "Gsk-test-key",
            "cli.commands.profile._require_tty_for_secret": lambda *_: None,
        },
    ),
    CommandCase(
        "profile-workflow-prefs-show",
        ("profile", "workflow-preferences", "show"),
        "cli.commands.profile.require_client",
    ),
    CommandCase(
        "profile-workflow-prefs-set",
        ("profile", "workflow-preferences", "set", "--gate-threshold", "60"),
        "cli.commands.profile.require_client",
    ),
    CommandCase("workflow-status", ("workflow", "status", "sess-1"), "cli.commands.workflow.require_client"),
    CommandCase("workflow-results", ("workflow", "results", "sess-1"), "cli.commands.workflow.require_client"),
    CommandCase(
        "workflow-watch",
        ("workflow", "watch", "sess-1"),
        "cli.commands.workflow.require_client",
        extra_patches={"cli.commands.workflow.watch_workflow_session": lambda **_kwargs: None},
    ),
    CommandCase(
        "workflow-continue",
        ("workflow", "continue", "sess-1", "--confirm"),
        "cli.commands.workflow.require_client",
    ),
    CommandCase(
        "workflow-generate-documents",
        ("workflow", "generate-documents", "sess-1"),
        "cli.commands.workflow.require_client",
    ),
    CommandCase(
        "workflow-regenerate-cover-letter",
        ("workflow", "regenerate", "cover-letter", "sess-1"),
        "cli.commands.workflow.require_client",
    ),
    CommandCase(
        "workflow-regenerate-resume",
        ("workflow", "regenerate", "resume", "sess-1"),
        "cli.commands.workflow.require_client",
    ),
    CommandCase(
        "workflow-generate-interview-prep",
        ("workflow", "generate-interview-prep", "sess-1"),
        "cli.commands.workflow.require_client",
    ),
    CommandCase(
        "workflow-analyze-url",
        ("workflow", "analyze", "--url", "https://careers.example.com/jobs/1"),
        "cli.commands.workflow.require_client",
    ),
    CommandCase("apps-list", ("apps", "list"), "cli.commands.applications.require_client"),
    CommandCase("apps-show", ("apps", "show", "app-1"), "cli.commands.applications.require_client"),
    CommandCase("apps-stats", ("apps", "stats"), "cli.commands.applications.require_client"),
    CommandCase("apps-status", ("apps", "status", "app-1", "applied"), "cli.commands.applications.require_client"),
    CommandCase(
        "apps-notes-text",
        ("apps", "notes", "app-1", "Follow up Tuesday"),
        "cli.commands.applications.require_client",
    ),
    CommandCase("apps-delete", ("apps", "delete", "app-1", "--confirm"), "cli.commands.applications.require_client"),
    CommandCase("interview-show", ("interview", "show", "sess-1"), "cli.commands.interview.require_client"),
    CommandCase("interview-status", ("interview", "status", "sess-1"), "cli.commands.interview.require_client"),
    CommandCase("cv-status", ("cv", "status", "sess-1"), "cli.commands.cv.require_client"),
    CommandCase(
        "interview-delete",
        ("interview", "delete", "sess-1", "--confirm"),
        "cli.commands.interview.require_client",
    ),
    CommandCase(
        "interview-generate",
        ("interview", "generate", "sess-1"),
        "cli.commands.interview.require_client",
    ),
    CommandCase("cv-show", ("cv", "show", "sess-1"), "cli.commands.cv.require_client"),
    CommandCase("cv-start", ("cv", "start", "sess-1"), "cli.commands.cv.require_client"),
    CommandCase("cv-clear", ("cv", "clear", "sess-1", "--confirm"), "cli.commands.cv.require_client"),
    CommandCase("tools-followup-stages", ("tools", "followup-stages"), "cli.commands.tools.require_client"),
    CommandCase(
        "tools-rejection",
        ("tools", "rejection-analysis", "--email", "Thank you for applying."),
        "cli.commands.tools.require_client",
    ),
    CommandCase(
        "tools-thank-you",
        ("tools", "thank-you", "--interviewer", "Jane", "--interview-type", "video", "--company", "Acme", "--title", "Eng"),
        "cli.commands.tools.require_client",
    ),
    CommandCase(
        "tools-followup",
        ("tools", "followup", "--stage", "after_interview", "--company", "Acme", "--title", "Eng"),
        "cli.commands.tools.require_client",
    ),
    CommandCase(
        "tools-salary-coach",
        ("tools", "salary-coach", "--title", "Eng", "--company", "Acme", "--offered", "$150,000"),
        "cli.commands.tools.require_client",
    ),
    CommandCase(
        "tools-reference-request",
        ("tools", "reference-request", "--name", "Alex", "--relationship", "Manager", "--title", "Eng"),
        "cli.commands.tools.require_client",
    ),
    CommandCase(
        "tools-job-comparison",
        ("tools", "job-comparison", "--file", "-"),
        "cli.commands.tools.require_client",
        input=json.dumps({"jobs": [{"title": "A", "company": "Co1"}, {"title": "B", "company": "Co2"}]}),
    ),
    CommandCase("tools-schema-thank-you", ("tools", "schema", "thank-you"), "cli.commands.tools.require_client", needs_auth=False),
    CommandCase("tools-schema-rejection", ("tools", "schema", "rejection-analysis"), "cli.commands.tools.require_client", needs_auth=False),
    CommandCase("tools-schema-reference", ("tools", "schema", "reference-request"), "cli.commands.tools.require_client", needs_auth=False),
    CommandCase("tools-schema-job-comparison", ("tools", "schema", "job-comparison"), "cli.commands.tools.require_client", needs_auth=False),
    CommandCase("tools-schema-followup", ("tools", "schema", "followup"), "cli.commands.tools.require_client", needs_auth=False),
    CommandCase("tools-schema-salary", ("tools", "schema", "salary-coach"), "cli.commands.tools.require_client", needs_auth=False),
    CommandCase("admin-metrics", ("admin", "metrics"), "cli.commands.admin.require_client"),
    CommandCase("admin-maintenance-show", ("admin", "maintenance", "show"), "cli.commands.admin.require_client"),
    CommandCase(
        "admin-maintenance-on",
        ("admin", "maintenance", "on", "--message", "Upgrade", "--confirm"),
        "cli.commands.admin.require_client",
    ),
    CommandCase("admin-cache-stats", ("admin", "cache-stats"), "cli.commands.admin.require_client"),
    CommandCase(
        "admin-maintenance-off",
        ("admin", "maintenance", "off", "--confirm"),
        "cli.commands.admin.require_client",
    ),
]


def _apply_patches(patch_target: str, mock_client, extra: dict[str, object]):
    stack = ExitStack()
    if "make_client" in patch_target or "require_client" in patch_target:
        stack.enter_context(patch(patch_target, return_value=mock_client))
    else:
        stack.enter_context(patch(patch_target, return_value=mock_client))
    for target, value in extra.items():
        if callable(value):
            stack.enter_context(patch(target, side_effect=value))
        else:
            stack.enter_context(patch(target, return_value=value))
    return stack


@pytest.mark.parametrize("case", COMMAND_CASES, ids=lambda c: c.id)
def test_command_happy_path(case: CommandCase, invoke, write_credentials) -> None:
    if case.needs_auth:
        write_credentials()
    mock_client = build_mock_client()
    with _apply_patches(case.patch_target, mock_client, case.extra_patches):
        result = invoke(*case.args, input=case.input)
    assert result.exit_code == 0, f"{case.id}: {result.output}"


def test_doctor_happy_path(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = build_mock_client()
    with patch("cli.commands.doctor.ApplyPilotClient", return_value=mock_client):
        result = invoke("doctor")
    assert result.exit_code == 0


def test_workflow_analyze_upload(invoke, write_credentials, tmp_path: Path) -> None:
    write_credentials()
    job = tmp_path / "job.pdf"
    job.write_bytes(b"%PDF-1.4")
    mock_client = build_mock_client()
    with patch("cli.commands.workflow.require_client", return_value=mock_client):
        result = invoke("workflow", "analyze", "--upload", str(job))
    assert result.exit_code == 0
    assert mock_client.workflow.start.call_args.kwargs.get("job_file") == str(job)


def test_profile_export_writes_file(invoke, write_credentials, tmp_path: Path) -> None:
    write_credentials()
    mock_client = build_mock_client()
    out = tmp_path / "export.json"
    with patch("cli.commands.profile.require_client", return_value=mock_client):
        result = invoke("profile", "export", "--out", str(out))
    assert result.exit_code == 0
    assert out.read_bytes() == b'{"export": true}'


def test_apps_download_writes_file(invoke, write_credentials, tmp_path: Path) -> None:
    write_credentials()
    mock_client = build_mock_client()
    out = tmp_path / "bundle.zip"
    with patch("cli.commands.applications.require_client", return_value=mock_client):
        result = invoke("apps", "download", "app-1", "--out", str(out))
    assert result.exit_code == 0
    assert out.read_bytes() == b"zip-bytes"


def test_cv_download_writes_file(invoke, write_credentials, tmp_path: Path) -> None:
    write_credentials()
    mock_client = build_mock_client()
    out = tmp_path / "cv.odt"
    with patch("cli.commands.cv.require_client", return_value=mock_client):
        result = invoke("cv", "download", "sess-1", "--out", str(out))
    assert result.exit_code == 0
    assert out.read_bytes() == b"odt"


def test_profile_resume_upload(invoke, write_credentials, tmp_path: Path) -> None:
    write_credentials()
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4")
    mock_client = build_mock_client()
    with patch("cli.commands.profile.require_client", return_value=mock_client):
        result = invoke("profile", "resume", "upload", str(resume))
    assert result.exit_code == 0
    mock_client.profile.parse_resume.assert_called_once_with(str(resume))


def test_workflow_analyze_stdin(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = build_mock_client()
    with patch("cli.commands.workflow.require_client", return_value=mock_client):
        result = invoke("workflow", "analyze", "-", input="Senior Engineer at Acme\nPython required.")
    assert result.exit_code == 0
    assert mock_client.workflow.start.call_args.kwargs.get("job_text")


def test_extension_autofill_from_file(invoke, write_credentials, tmp_path: Path) -> None:
    write_credentials()
    body = {
        "page_url": "https://careers.example.com/apply",
        "fields": [{"field_uid": "0", "tag": "input", "input_type": "text", "label_text": "Name"}],
    }
    path = write_json_file(tmp_path / "fields.json", body)
    mock_client = build_mock_client()
    with patch("cli.commands.extension.require_client", return_value=mock_client):
        result = invoke("extension", "autofill", "map", "--file", str(path))
    assert result.exit_code == 0
