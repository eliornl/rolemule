# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional


WORKFLOW_STOP_STATUSES = frozenset(
    {
        "awaiting_confirmation",
        "analysis_complete",
        "completed",
        "failed",
    }
)


class WorkflowPollTimeout(TimeoutError):
    """Raised when workflow polling exceeds the configured timeout."""

    def __init__(self, session_id: str, last_status: Optional[Dict[str, Any]] = None) -> None:
        self.session_id = session_id
        self.last_status = last_status or {}
        super().__init__(f"Workflow {session_id} did not reach a terminal status in time")


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def wait_for_terminal_status(
    get_status: Callable[[], Dict[str, Any]],
    *,
    interval_seconds: float = 3.0,
    timeout_seconds: float = 600.0,
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """
    Poll workflow status until a stop state or timeout.

    Stop states: awaiting_confirmation, analysis_complete, completed, failed.
    """
    deadline = time.monotonic() + timeout_seconds
    last: Dict[str, Any] = {}

    while True:
        last = get_status()
        if on_progress:
            on_progress(last)

        status = last.get("status")
        if status in WORKFLOW_STOP_STATUSES:
            return last

        if time.monotonic() >= deadline:
            session_id = str(last.get("session_id") or "")
            raise WorkflowPollTimeout(session_id, last)

        time.sleep(interval_seconds)
