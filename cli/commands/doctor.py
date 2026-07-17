# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

import json
import os
import stat
from typing import Any, Dict, List

import typer

from rolemule_client.client import RoleMuleClient
from rolemule_client.errors import ApiClientError, ExitCode
from cli.config import config_dir, config_path, credentials_path, ensure_config_dir, mask_token
from cli.context import CliContext
from cli.workflow_watch import PAT_PREFIX

doctor_app = typer.Typer(help="Check server connectivity and local configuration.")


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def _check(path: str, ok: bool, detail: str = "") -> Dict[str, Any]:
    return {"check": path, "ok": ok, "detail": detail}


@doctor_app.callback(invoke_without_command=True)
def doctor_run(ctx: typer.Context) -> None:
    """
    Verify RoleMule server reachability, config files, and token (if saved).
    """
    cli_ctx: CliContext = ctx.obj
    results: List[Dict[str, Any]] = []

    # Config directory (created on first save if missing)
    if not config_dir().is_dir():
        ensure_config_dir()
    cdir = config_dir()
    results.append(_check("config_dir", cdir.is_dir(), str(cdir)))

    cfg_file = config_path()
    results.append(_check("config_file", True, str(cfg_file) + (" (using defaults)" if not cfg_file.is_file() else "")))

    cred_file = credentials_path()
    if cred_file.is_file():
        mode = stat.S_IMODE(os.stat(cred_file).st_mode)
        cred_ok = mode == 0o600
        results.append(
            _check(
                "credentials_permissions",
                cred_ok,
                f"{cred_file} mode {oct(mode)}" + ("" if cred_ok else " (expected 0600)"),
            )
        )
    else:
        results.append(_check("credentials_file", True, "not present (run rolemule auth login)"))

    client = RoleMuleClient(cli_ctx.base_url, access_token=cli_ctx.access_token)

    # Health
    try:
        health = client.health()
        status = health.get("status", "unknown")
        results.append(_check("server_health", True, f"status={status}"))
    except ApiClientError as exc:
        results.append(_check("server_health", False, str(exc)))

    # Token verify
    if cli_ctx.access_token:
        token_kind = "pat" if cli_ctx.access_token.startswith(PAT_PREFIX) else "jwt"
        try:
            verify = client.verify_token()
            email = verify.get("email") or cli_ctx.credentials.email if cli_ctx.credentials else ""
            profile_done = verify.get("profile_completed", False)
            results.append(
                _check(
                    "auth_token",
                    verify.get("success", True),
                    f"token_type={token_kind} email={email} profile_completed={profile_done}",
                )
            )
            if token_kind == "pat":
                results.append(
                    _check(
                        "pat_refresh",
                        True,
                        "PAT cannot be refreshed — use: rolemule auth token create --save",
                    )
                )
                try:
                    pat_rows = client.auth.list_pats().get("tokens") or []
                    for row in pat_rows:
                        prefix = row.get("token_prefix") or ""
                        if prefix and cli_ctx.access_token.startswith(prefix):
                            if row.get("active"):
                                expires = row.get("expires_at") or "no expiry"
                                results.append(
                                    _check(
                                        "pat_metadata",
                                        True,
                                        f"name={row.get('name')} expires_at={expires}",
                                    )
                                )
                            else:
                                results.append(
                                    _check(
                                        "pat_metadata",
                                        False,
                                        f"token revoked (name={row.get('name')})",
                                    )
                                )
                            break
                except ApiClientError:
                    results.append(
                        _check("pat_metadata", True, "could not list PAT metadata (token still valid)")
                    )
            elif verify.get("success", True):
                results.append(
                    _check(
                        "jwt_refresh",
                        True,
                        "refresh with: rolemule auth refresh",
                    )
                )
        except ApiClientError as exc:
            detail = str(exc)
            if token_kind == "pat":
                detail += " — create a new PAT: rolemule auth token create --save"
            results.append(_check("auth_token", False, detail))
    elif not cli_ctx.quiet:
        results.append(_check("auth_token", True, "skipped (not logged in)"))

    all_ok = all(r["ok"] for r in results)

    if cli_ctx.output_format == "json":
        typer.echo(json.dumps({"ok": all_ok, "checks": results}, indent=2))
    else:
        for row in results:
            mark = typer.style("ok", fg="green") if row["ok"] else typer.style("FAIL", fg="red")
            detail = f" — {row['detail']}" if row["detail"] else ""
            typer.echo(f"[{mark}] {row['check']}{detail}")
        if cli_ctx.access_token and not cli_ctx.quiet:
            kind = "PAT" if cli_ctx.access_token.startswith(PAT_PREFIX) else "JWT"
            typer.echo(f"Token ({kind}): {mask_token(cli_ctx.access_token)}")

    if not all_ok:
        raise typer.Exit(code=int(ExitCode.ERROR))
