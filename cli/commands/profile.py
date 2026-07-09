# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

import getpass
import sys
from pathlib import Path
from typing import Optional

import typer

from applypilot_client.errors import ApiClientError, ExitCode
from cli.context import CliContext
from cli.output import emit, emit_error, require_client
from cli.util import filename_from_headers, payload_from_file, require_confirm

profile_app = typer.Typer(help="Profile, resume, API key, and account settings.")
set_app = typer.Typer(help="Update profile sections.")
resume_app = typer.Typer(help="Resume file management.")
api_key_app = typer.Typer(help="Bring-your-own Gemini API key.")
workflow_prefs_app = typer.Typer(help="Workflow agent preferences.")

profile_app.add_typer(set_app, name="set")
profile_app.add_typer(resume_app, name="resume")
profile_app.add_typer(api_key_app, name="api-key")
profile_app.add_typer(workflow_prefs_app, name="workflow-preferences")


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def _require_tty_for_secret(action: str) -> None:
    if not sys.stdin.isatty():
        typer.secho(f"{action} requires an interactive terminal (use a TTY).", fg="red", err=True)
        raise typer.Exit(code=int(ExitCode.ERROR))


def _run(ctx: typer.Context, fn) -> None:
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = fn(client)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data)


@profile_app.command("show")
def profile_show(ctx: typer.Context) -> None:
    """Show complete profile data."""
    _run(ctx, lambda c: c.profile.show())


@profile_app.command("status")
def profile_status(ctx: typer.Context) -> None:
    """Show profile completion breakdown."""
    _run(ctx, lambda c: c.profile.status())


@profile_app.command("complete")
def profile_complete(ctx: typer.Context) -> None:
    """Mark profile complete after all sections are filled."""
    _run(ctx, lambda c: c.profile.complete())


@set_app.command("basic-info")
def set_basic_info(
    ctx: typer.Context,
    file: Optional[str] = typer.Option(None, "--file", "-f", help="JSON file or '-' for stdin"),
    city: Optional[str] = typer.Option(None, "--city"),
    state: Optional[str] = typer.Option(None, "--state"),
    country: Optional[str] = typer.Option(None, "--country"),
    title: Optional[str] = typer.Option(None, "--title", help="Professional title"),
    years: Optional[int] = typer.Option(None, "--years", help="Years of experience"),
    summary: Optional[str] = typer.Option(None, "--summary"),
    student: bool = typer.Option(False, "--student", help="Currently a student"),
    phone: Optional[str] = typer.Option(None, "--phone"),
    linkedin: Optional[str] = typer.Option(None, "--linkedin"),
    github: Optional[str] = typer.Option(None, "--github"),
    portfolio: Optional[str] = typer.Option(None, "--portfolio"),
) -> None:
    """Update basic profile information (step 1)."""
    cli_ctx: CliContext = ctx.obj

    if file:
        payload = payload_from_file(file)
    else:
        missing = [
            name
            for name, val in [
                ("city", city),
                ("state", state),
                ("country", country),
                ("title", title),
                ("years", years),
                ("summary", summary),
            ]
            if val is None or (isinstance(val, str) and not val.strip())
        ]
        if missing:
            typer.secho(
                f"Missing required flags: {', '.join(missing)} (or use --file)",
                fg="red",
                err=True,
            )
            raise typer.Exit(code=int(ExitCode.ERROR))
        payload = {
            "city": city,
            "state": state,
            "country": country,
            "professional_title": title,
            "years_experience": years,
            "is_student": student,
            "summary": summary,
            "phone": phone or "",
            "linkedin_url": linkedin or "",
            "github_url": github or "",
            "portfolio_url": portfolio or "",
        }

    client = require_client(cli_ctx)
    try:
        data = client.profile.update_basic_info(payload)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data, human="Basic info updated.")


@set_app.command("work-experience")
def set_work_experience(
    ctx: typer.Context,
    file: str = typer.Option(..., "--file", "-f", help="JSON file or '-' for stdin"),
) -> None:
    """Update work experience from a JSON file."""
    cli_ctx: CliContext = ctx.obj
    payload = payload_from_file(file, wrapper_key="work_experience")
    client = require_client(cli_ctx)
    try:
        data = client.profile.update_work_experience(payload)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data, human="Work experience updated.")


@set_app.command("education")
def set_education(
    ctx: typer.Context,
    file: str = typer.Option(..., "--file", "-f", help="JSON file or '-' for stdin"),
) -> None:
    """Update education from a JSON file."""
    cli_ctx: CliContext = ctx.obj
    payload = payload_from_file(file, wrapper_key="education")
    client = require_client(cli_ctx)
    try:
        data = client.profile.update_education(payload)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data, human="Education updated.")


@set_app.command("skills")
def set_skills(
    ctx: typer.Context,
    file: Optional[str] = typer.Option(None, "--file", "-f", help="JSON file or '-' for stdin"),
    skills: Optional[str] = typer.Option(None, "--skills", help="Comma-separated skill list"),
) -> None:
    """Update skills and qualifications."""
    cli_ctx: CliContext = ctx.obj
    if file:
        payload = payload_from_file(file, wrapper_key="skills")
    elif skills is not None:
        payload = {"skills": [s.strip() for s in skills.split(",") if s.strip()]}
    else:
        typer.secho("Provide --file or --skills.", fg="red", err=True)
        raise typer.Exit(code=int(ExitCode.ERROR))

    client = require_client(cli_ctx)
    try:
        data = client.profile.update_skills(payload)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data, human="Skills updated.")


@set_app.command("preferences")
def set_preferences(
    ctx: typer.Context,
    file: str = typer.Option(..., "--file", "-f", help="JSON file or '-' for stdin"),
) -> None:
    """Update career preferences from a JSON file."""
    cli_ctx: CliContext = ctx.obj
    payload = payload_from_file(file)
    client = require_client(cli_ctx)
    try:
        data = client.profile.update_career_preferences(payload)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data, human="Career preferences updated.")


@set_app.command("notifications")
def set_notifications(
    ctx: typer.Context,
    file: Optional[str] = typer.Option(None, "--file", "-f", help="JSON file or '-' for stdin"),
    email_notifications: Optional[bool] = typer.Option(None, "--email-notifications/--no-email-notifications"),
    application_updates: Optional[bool] = typer.Option(None, "--application-updates/--no-application-updates"),
    weekly_summary: Optional[bool] = typer.Option(None, "--weekly-summary/--no-weekly-summary"),
    tips_and_suggestions: Optional[bool] = typer.Option(None, "--tips/--no-tips"),
) -> None:
    """Update notification settings."""
    cli_ctx: CliContext = ctx.obj
    if file:
        payload = payload_from_file(file)
    else:
        payload = {}
        if email_notifications is not None:
            payload["email_notifications"] = email_notifications
        if application_updates is not None:
            payload["application_updates"] = application_updates
        if weekly_summary is not None:
            payload["weekly_summary"] = weekly_summary
        if tips_and_suggestions is not None:
            payload["tips_and_suggestions"] = tips_and_suggestions
        if not payload:
            typer.secho("Provide --file or at least one notification flag.", fg="red", err=True)
            raise typer.Exit(code=int(ExitCode.ERROR))

    client = require_client(cli_ctx)
    try:
        data = client.profile.update_notifications(payload)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data, human="Notification settings updated.")


@resume_app.command("upload")
def resume_upload(
    ctx: typer.Context,
    file: Path = typer.Argument(..., exists=True, readable=True, help="Resume file (.pdf, .docx, .txt)"),
) -> None:
    """Upload and parse a resume file."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.profile.parse_resume(str(file))
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data, human="Resume uploaded and parsed.")


@resume_app.command("show")
def resume_show(
    ctx: typer.Context,
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Save resume to this path"),
) -> None:
    """Download the stored resume file."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        content, headers = client.profile.download_resume()
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)

    if out is None:
        if cli_ctx.output_format == "json":
            emit(
                cli_ctx,
                {
                    "size_bytes": len(content),
                    "content_type": headers.get("content-type"),
                    "filename": filename_from_headers(headers, "resume.pdf"),
                    "message": "Use --out to save the file",
                },
            )
            return
        typer.secho("Specify --out to save the resume file.", fg="red", err=True)
        raise typer.Exit(code=int(ExitCode.ERROR))

    out.write_bytes(content)
    emit(cli_ctx, {"saved_to": str(out), "size_bytes": len(content)}, human=f"Saved to {out}")


@resume_app.command("delete")
def resume_delete(
    ctx: typer.Context,
    confirm: bool = typer.Option(False, "--confirm", help="Confirm deletion"),
) -> None:
    """Delete the stored resume file."""
    require_confirm(confirm, "delete your resume")
    _run(ctx, lambda c: c.profile.delete_resume())


@api_key_app.command("status")
def api_key_status(ctx: typer.Context) -> None:
    """Show API key configuration status."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.profile.api_key_status()
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)

    if cli_ctx.output_format != "json":
        has_key = data.get("has_user_key") or data.get("has_api_key")
        server = data.get("server_has_key") or data.get("use_vertex_ai")
        if has_key:
            preview = data.get("key_preview") or "configured"
            human = f"Your API key is set ({preview})."
        elif server:
            human = "Using server-configured AI (no personal key needed)."
        else:
            human = "No API key configured. Run: applypilot profile api-key set"
        emit(cli_ctx, data, human=human)
        return
    emit(cli_ctx, data)


@api_key_app.command("set")
def api_key_set(
    ctx: typer.Context,
    api_key: Optional[str] = typer.Option(None, "--api-key", help="Gemini API key (prefer getpass prompt)"),
) -> None:
    """Save a Gemini API key (BYOK)."""
    cli_ctx: CliContext = ctx.obj
    _require_tty_for_secret("api-key set")
    key = api_key or getpass.getpass("Gemini API key: ")
    if not key.strip():
        typer.secho("API key cannot be empty.", fg="red", err=True)
        raise typer.Exit(code=int(ExitCode.ERROR))

    client = require_client(cli_ctx)
    try:
        data = client.profile.api_key_set(key.strip())
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data, human="API key saved.")


@api_key_app.command("delete")
def api_key_delete(
    ctx: typer.Context,
    confirm: bool = typer.Option(False, "--confirm", help="Confirm deletion"),
) -> None:
    """Remove the stored API key."""
    require_confirm(confirm, "delete your API key")
    _run(ctx, lambda c: c.profile.api_key_delete())


@api_key_app.command("validate")
def api_key_validate(
    ctx: typer.Context,
    api_key: Optional[str] = typer.Option(None, "--api-key", help="Key to validate (prefer getpass prompt)"),
) -> None:
    """Validate a Gemini API key without saving it."""
    cli_ctx: CliContext = ctx.obj
    _require_tty_for_secret("api-key validate")
    key = api_key or getpass.getpass("Gemini API key: ")
    client = require_client(cli_ctx)
    try:
        data = client.profile.api_key_validate(key.strip())
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data, human=data.get("message", "API key is valid"))


@workflow_prefs_app.command("show")
def workflow_preferences_show(ctx: typer.Context) -> None:
    """Show workflow preferences."""
    _run(ctx, lambda c: c.profile.workflow_preferences_show())


@workflow_prefs_app.command("set")
def workflow_preferences_set(
    ctx: typer.Context,
    file: Optional[str] = typer.Option(None, "--file", "-f", help="JSON file or '-' for stdin"),
    gate_threshold: Optional[int] = typer.Option(None, "--gate-threshold"),
    auto_generate_documents: Optional[bool] = typer.Option(
        None, "--auto-generate-documents/--no-auto-generate-documents"
    ),
    cover_letter_tone: Optional[str] = typer.Option(None, "--cover-letter-tone"),
    resume_length: Optional[str] = typer.Option(None, "--resume-length"),
    preferred_model: Optional[str] = typer.Option(None, "--preferred-model"),
) -> None:
    """Update workflow preferences (partial patch)."""
    cli_ctx: CliContext = ctx.obj
    if file:
        payload = payload_from_file(file)
    else:
        payload = {}
        if gate_threshold is not None:
            payload["workflow_gate_threshold"] = gate_threshold
        if auto_generate_documents is not None:
            payload["auto_generate_documents"] = auto_generate_documents
        if cover_letter_tone is not None:
            payload["cover_letter_tone"] = cover_letter_tone
        if resume_length is not None:
            payload["resume_length"] = resume_length
        if preferred_model is not None:
            payload["preferred_model"] = preferred_model
        if not payload:
            typer.secho("Provide --file or at least one preference flag.", fg="red", err=True)
            raise typer.Exit(code=int(ExitCode.ERROR))

    client = require_client(cli_ctx)
    try:
        data = client.profile.workflow_preferences_set(payload)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data, human="Workflow preferences updated.")


@profile_app.command("export")
def profile_export(
    ctx: typer.Context,
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Save export JSON to this path"),
) -> None:
    """Export all account data (GDPR portability)."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        content, headers = client.profile.export_data()
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)

    filename = filename_from_headers(headers, "applypilot-export.json")
    if out is None:
        out = Path(filename)

    out.write_bytes(content)
    emit(cli_ctx, {"saved_to": str(out), "size_bytes": len(content)}, human=f"Exported to {out}")


@profile_app.command("clear-data")
def profile_clear_data(
    ctx: typer.Context,
    confirm: bool = typer.Option(False, "--confirm", help="Confirm deletion of all application data"),
) -> None:
    """Delete all applications and workflow data (keeps account)."""
    require_confirm(confirm, "permanently clear application data")
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.profile.clear_data()
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data, human="Application data cleared.")


@profile_app.command("delete-account")
def profile_delete_account(
    ctx: typer.Context,
    confirm: bool = typer.Option(False, "--confirm", help="Confirm permanent account deletion"),
) -> None:
    """Permanently delete your account."""
    require_confirm(confirm, "permanently delete your account")
    cli_ctx: CliContext = ctx.obj
    _require_tty_for_secret("delete-account")
    password = getpass.getpass("Password (empty for Google-only accounts): ")

    client = require_client(cli_ctx)
    try:
        data = client.profile.delete_account(password)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data, human="Account deleted.")
