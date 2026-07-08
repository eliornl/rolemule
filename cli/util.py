# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import typer

from applypilot_client.errors import ExitCode


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def load_json_file(path: str) -> Any:
    """Load JSON from a file path or stdin when path is '-'."""
    if path == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding="utf-8")
    return json.loads(raw)


def payload_from_file(
    path: str,
    *,
    wrapper_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Load a JSON object for API requests.

    If wrapper_key is set and the file contains a JSON array, wrap it.
    """
    data = load_json_file(path)
    if wrapper_key and isinstance(data, list):
        return {wrapper_key: data}
    if not isinstance(data, dict):
        raise typer.BadParameter("JSON file must contain an object (or array with --wrap)")
    return data


def require_confirm(confirm: bool, action: str) -> None:
    """Exit unless --confirm was passed for destructive operations."""
    if not confirm:
        typer.secho(f"Add --confirm to {action}.", fg="red", err=True)
        raise typer.Exit(code=int(ExitCode.ERROR))


def filename_from_headers(headers: Dict[str, str], default: str) -> str:
    """Parse filename from Content-Disposition header."""
    disposition = headers.get("content-disposition") or headers.get("Content-Disposition", "")
    if "filename=" in disposition:
        part = disposition.split("filename=", 1)[1].strip().strip('"')
        if part:
            return part
    return default
