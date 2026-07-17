# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

import typer

PAT_PREFIX = "rm_pat_"


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def format_watch_event(message: Dict[str, Any]) -> Optional[str]:
    """Return a single human-readable line for a workflow WebSocket event."""
    msg_type = message.get("type", "event")
    data = message.get("data") or {}
    session_id = message.get("session_id") or ""

    if msg_type == "connected":
        return "[connected] Watching workflow…"
    if msg_type == "agent_update":
        agent = data.get("agent", "agent")
        status = data.get("status", "")
        extra = data.get("message")
        line = f"[agent] {agent}: {status}"
        if extra:
            line += f" — {extra}"
        return line
    if msg_type == "phase_change":
        phase = data.get("phase", "")
        progress = data.get("progress")
        if progress is not None:
            return f"[phase] {phase} ({progress}%)"
        return f"[phase] {phase}"
    if msg_type == "workflow_complete":
        return "[done] Workflow completed — rolemule workflow results " + session_id
    if msg_type == "workflow_error":
        err = data.get("error", "Unknown error")
        agent = data.get("failed_agent")
        if agent:
            return f"[failed] {agent}: {err}"
        return f"[failed] {err}"
    if msg_type == "gate_decision":
        score = data.get("match_score")
        try:
            pct = f"{float(score) * 100:.0f}%"
        except (TypeError, ValueError):
            pct = "?"
        sid = session_id or "SESSION"
        return f"[gate] Match {pct} — run: rolemule workflow continue {sid} --confirm"
    if msg_type == "pong":
        return None
    return f"[{msg_type}] {json.dumps(data, default=str)}" if data else f"[{msg_type}]"


def _http_to_ws_url(base_url: str, path: str) -> str:
    parsed = urlparse(base_url.rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    host = parsed.netloc or parsed.path
    return f"{scheme}://{host}{path}"


def watch_workflow_session(
    *,
    base_url: str,
    access_token: str,
    session_id: str,
    on_message: Optional[Callable[[Dict[str, Any]], None]] = None,
    quiet: bool = False,
    human: bool = True,
) -> None:
    """
    Stream workflow WebSocket events until the connection closes or workflow ends.

    Raises:
        typer.Exit: On connection errors
    """
    try:
        import websocket  # type: ignore[import-untyped]  # websocket-client
    except ImportError as exc:
        typer.secho(
            "websocket-client is required for workflow watch (pip install rolemule[cli])",
            fg="red",
            err=True,
        )
        raise typer.Exit(code=1) from exc

    ws_url = _http_to_ws_url(
        base_url,
        f"/api/v1/ws/workflow/{session_id}?token={access_token}",
    )

    terminal_types = frozenset(
        {
            "workflow_complete",
            "workflow_error",
            "gate_decision",
        }
    )

    def _default_handler(message: Dict[str, Any]) -> None:
        if quiet:
            return
        if human:
            line = format_watch_event(message)
            if line:
                typer.echo(line, err=True)
        else:
            typer.echo(json.dumps(message, default=str), err=True)

    handler = on_message or _default_handler
    closed = {"done": False}

    def on_data(_ws: Any, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            if not quiet:
                typer.echo(raw, err=True)
            return
        if isinstance(payload, dict):
            handler(payload)
            if payload.get("type") in terminal_types:
                closed["done"] = True
                _ws.close()

    def on_error(_ws: Any, error: Any) -> None:
        typer.secho(f"WebSocket error: {error}", fg="red", err=True)

    def on_close(_ws: Any, _status: Any, _msg: Any) -> None:
        closed["done"] = True

    ws = websocket.WebSocketApp(
        ws_url,
        on_message=on_data,
        on_error=on_error,
        on_close=on_close,
    )
    ws.run_forever()
    if not closed["done"] and not quiet:
        typer.echo("WebSocket connection closed.", err=True)
