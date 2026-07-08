# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

import getpass
import sys
from typing import Optional

import typer

from applypilot_client.errors import ApiClientError, ExitCode
from cli.config import Credentials, clear_credentials, load_credentials, mask_token, save_credentials
from cli.context import CliContext
from cli.output import _now_iso, emit, emit_error, make_client, persist_auth_response

auth_app = typer.Typer(help="Login, logout, and token management.")
token_app = typer.Typer(help="Manage locally stored JWT.")
auth_app.add_typer(token_app, name="token")


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def _require_tty_for_secret(action: str) -> None:
    if not sys.stdin.isatty():
        typer.secho(f"{action} requires an interactive terminal (use a TTY).", fg="red", err=True)
        raise typer.Exit(code=int(ExitCode.ERROR))


@auth_app.command("login")
def login(
    ctx: typer.Context,
    email: Optional[str] = typer.Option(None, "--email", "-e", prompt="Email"),
    remember_me: bool = typer.Option(False, "--remember-me", help="Extended session duration"),
) -> None:
    """Log in with email and password."""
    cli_ctx: CliContext = ctx.obj
    _require_tty_for_secret("login")
    password = getpass.getpass("Password: ")
    client = make_client(cli_ctx)
    try:
        data = client.auth.login(email, password, remember_me=remember_me)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)

    persist_auth_response(data, email_hint=email)
    emit(
        cli_ctx,
        data,
        human=f"Logged in as {data.get('user', {}).get('email', email)}",
    )


@auth_app.command("logout")
def logout(ctx: typer.Context) -> None:
    """Log out and clear local credentials."""
    cli_ctx: CliContext = ctx.obj
    if cli_ctx.access_token:
        client = make_client(cli_ctx)
        try:
            client.auth.logout()
        except ApiClientError:
            pass
    clear_credentials()
    emit(cli_ctx, {"logged_out": True}, human="Logged out.")


@auth_app.command("whoami")
def whoami(ctx: typer.Context) -> None:
    """Show current authenticated user."""
    cli_ctx: CliContext = ctx.obj
    if not cli_ctx.access_token:
        emit(cli_ctx, {"authenticated": False}, human="Not logged in. Run: applypilot auth login")
        raise typer.Exit(code=int(ExitCode.AUTH_OR_PROFILE))

    client = make_client(cli_ctx)
    try:
        data = client.auth.verify()
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)

    emit(
        cli_ctx,
        data,
        human=(
            f"email={data.get('email')} "
            f"profile_completed={data.get('profile_completed')}"
        ),
    )


@auth_app.command("refresh")
def refresh(ctx: typer.Context) -> None:
    """Refresh the JWT access token."""
    cli_ctx: CliContext = ctx.obj
    if not cli_ctx.access_token:
        typer.secho("Not logged in.", fg="red", err=True)
        raise typer.Exit(code=int(ExitCode.AUTH_OR_PROFILE))

    client = make_client(cli_ctx)
    try:
        data = client.auth.refresh()
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)

    persist_auth_response(data)
    emit(cli_ctx, {"refreshed": True, "expires_in": data.get("expires_in")}, human="Token refreshed.")


@auth_app.command("register")
def register(
    ctx: typer.Context,
    full_name: Optional[str] = typer.Option(None, "--name", prompt="Full name"),
    email: Optional[str] = typer.Option(None, "--email", "-e", prompt="Email"),
) -> None:
    """Register a new account (verify email before logging in)."""
    cli_ctx: CliContext = ctx.obj
    _require_tty_for_secret("register")
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    client = make_client(cli_ctx)
    try:
        data = client.auth.register(full_name, email, password, confirm)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)

    # Do not persist register token — only verify-code/login should save credentials.
    emit(
        cli_ctx,
        {
            "registered": True,
            "email": email,
            "message": data.get("message"),
            "next_step": "applypilot auth verify-code",
        },
        human=(
            f"Account created for {email}. "
            "Check your email for the verification code, then run: applypilot auth verify-code"
        ),
    )


@auth_app.command("verify-code")
def verify_code(
    ctx: typer.Context,
    email: Optional[str] = typer.Option(None, "--email", "-e", prompt="Email"),
    code: Optional[str] = typer.Option(None, "--code", "-c", prompt="6-digit code"),
) -> None:
    """Verify email with a 6-digit code and save login token."""
    cli_ctx: CliContext = ctx.obj
    client = make_client(cli_ctx)
    try:
        data = client.auth.verify_code(email, code)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)

    persist_auth_response(data, email_hint=email)
    emit(
        cli_ctx,
        data,
        human=data.get("message", "Email verified."),
    )


@auth_app.command("resend-verification")
def resend_verification(
    ctx: typer.Context,
    email: str = typer.Option(..., "--email", "-e", prompt="Email"),
) -> None:
    """Resend email verification code."""
    cli_ctx: CliContext = ctx.obj
    client = make_client(cli_ctx)
    try:
        data = client.auth.resend_verification(email)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)

    emit(cli_ctx, data, human=data.get("message", "Verification email sent if applicable."))


@auth_app.command("verification-status")
def verification_status(ctx: typer.Context) -> None:
    """Show email verification status for the current user."""
    cli_ctx: CliContext = ctx.obj
    if not cli_ctx.access_token:
        raise typer.Exit(code=int(ExitCode.AUTH_OR_PROFILE))
    client = make_client(cli_ctx)
    try:
        data = client.auth.verification_status()
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data)


@auth_app.command("extension-status")
def extension_status(ctx: typer.Context) -> None:
    """Show auth status (extension-compatible payload)."""
    cli_ctx: CliContext = ctx.obj
    if not cli_ctx.access_token:
        raise typer.Exit(code=int(ExitCode.AUTH_OR_PROFILE))
    client = make_client(cli_ctx)
    try:
        data = client.auth.extension_status()
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data)


@auth_app.command("email-status")
def email_status(ctx: typer.Context) -> None:
    """Check whether server email (SMTP) is configured."""
    cli_ctx: CliContext = ctx.obj
    client = make_client(cli_ctx)
    try:
        data = client.auth.email_status()
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data)


@auth_app.command("change-password")
def change_password(ctx: typer.Context) -> None:
    """Change password for the logged-in account."""
    cli_ctx: CliContext = ctx.obj
    if not cli_ctx.access_token:
        raise typer.Exit(code=int(ExitCode.AUTH_OR_PROFILE))
    _require_tty_for_secret("change-password")
    current = getpass.getpass("Current password: ")
    new_pw = getpass.getpass("New password: ")
    confirm = getpass.getpass("Confirm new password: ")
    client = make_client(cli_ctx)
    try:
        data = client.auth.change_password(current, new_pw, confirm)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data, human=data.get("message", "Password changed."))


@token_app.command("set")
def token_set(
    ctx: typer.Context,
    from_stdin: bool = typer.Option(False, "--from-stdin", help="Read JWT from stdin"),
    token: Optional[str] = typer.Option(None, "--token", help="JWT string (avoid in shell history)"),
) -> None:
    """Store a JWT locally (for Google OAuth users)."""
    cli_ctx: CliContext = ctx.obj
    raw = token
    if from_stdin:
        raw = sys.stdin.read().strip()
    elif raw is None:
        _require_tty_for_secret("token set")
        raw = getpass.getpass("Paste access token: ").strip()

    if not raw:
        typer.secho("No token provided.", fg="red", err=True)
        raise typer.Exit(code=int(ExitCode.ERROR))

    save_credentials(
        Credentials(
            access_token=raw,
            saved_at=_now_iso(),
        )
    )
    emit(cli_ctx, {"saved": True}, human="Token saved.")


@token_app.command("show")
def token_show(ctx: typer.Context) -> None:
    """Show masked locally stored token."""
    cli_ctx: CliContext = ctx.obj
    creds = load_credentials()
    if not creds:
        emit(cli_ctx, {"present": False}, human="No token stored.")
        raise typer.Exit(code=int(ExitCode.AUTH_OR_PROFILE))

    emit(
        cli_ctx,
        {"present": True, "email": creds.email, "token": mask_token(creds.access_token)},
        human=f"email={creds.email or 'unknown'} token={mask_token(creds.access_token)}",
    )
