"""
Cloud Tasks client for dispatching long-running LLM workflows asynchronously.

When Cloud Tasks is configured (CLOUD_TASKS_SERVICE_URL + CLOUD_TASKS_SERVICE_ACCOUNT +
CLOUD_TASKS_SECRET are all set), workflow execution is offloaded from the request-handling
Cloud Run instance to a dedicated Cloud Tasks delivery, which:
  - Gives the workflow its own Cloud Run request (separate 300 s timeout)
  - Automatically retries on transient failures (Cloud Run cold start, network blip)
  - Decouples request latency from AI processing time
  - Lets the queue absorb spikes without hammering the DB

If Cloud Tasks is not configured the caller falls back to FastAPI BackgroundTasks.
"""

# =============================================================================
# IMPORTS
# =============================================================================

import asyncio
import json
import logging
import secrets
from typing import Any, Dict, Optional

from config.settings import get_settings
from utils.logging_config import sanitize_log_value

# Optional import — package is only needed when Cloud Tasks is actually configured.
# Without it the app starts normally and falls back to FastAPI BackgroundTasks.
try:
    from google.cloud import tasks_v2
    from google.protobuf import duration_pb2
    _TASKS_AVAILABLE = True
except ImportError:
    tasks_v2 = None  # type: ignore
    duration_pb2 = None  # type: ignore
    _TASKS_AVAILABLE = False

logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS
# =============================================================================

# Maximum dispatch deadline Cloud Tasks supports (30 minutes).
# The actual Cloud Run request timeout is set separately (cloud_run_timeout var).
DISPATCH_DEADLINE_SECONDS: int = 1800

# =============================================================================
# HELPERS
# =============================================================================


def _extract_project_from_service_url(service_url: str) -> str:
    """Extract the GCP project ID from a Cloud Run service URL.

    Cloud Run URLs follow the pattern:
        https://<service>-<hash>-<region>.a.run.app
    The project cannot be derived from the URL alone; callers must supply it
    via GOOGLE_CLOUD_PROJECT or via the service account email.

    This helper is a best-effort fallback that reads the env var.
    """
    import os
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT", "")
    if not project:
        raise ValueError(
            "Could not determine GCP project ID. "
            "Set the GOOGLE_CLOUD_PROJECT environment variable."
        )
    return project


def _get_tasks_client() -> Any:
    """Return a Cloud Tasks sync client (used inside run_in_executor)."""
    return tasks_v2.CloudTasksClient()  # type: ignore[union-attr]


# =============================================================================
# PUBLIC API
# =============================================================================


async def enqueue_workflow_task(
    *,
    session_id: str,
    user_id: str,
    input_method: str,
    job_input: str,
    user_data: Dict[str, Any],
) -> None:
    """Enqueue an initial workflow execution via Cloud Tasks.

    Args:
        session_id: The workflow session UUID.
        user_id: The user's UUID string.
        input_method: How the job was submitted ("text", "file", etc.).
        job_input: The raw job description text.
        user_data: Serialisable dict of user profile/preference data.

    Raises:
        Exception: Any Cloud Tasks API error (caller should catch and fall back).
    """
    settings = get_settings()

    payload: Dict[str, Any] = {
        "session_id": session_id,
        "user_id": user_id,
        "input_method": input_method,
        "job_input": job_input,
        "user_data": user_data,
    }

    await _enqueue_task(settings=settings, payload=payload)
    logger.info(
        "Enqueued initial workflow task for session %s",
        sanitize_log_value(session_id),
    )


async def enqueue_continue_workflow_task(
    *,
    session_id: str,
    user_id: str,
) -> None:
    """Enqueue a workflow continuation (post-gate) via Cloud Tasks.

    Args:
        session_id: The workflow session UUID.
        user_id: The user's UUID string.

    Raises:
        Exception: Any Cloud Tasks API error (caller should catch and fall back).
    """
    settings = get_settings()

    payload: Dict[str, Any] = {
        "session_id": session_id,
        "user_id": user_id,
        "action": "continue",
    }

    await _enqueue_task(settings=settings, payload=payload)
    logger.info(
        "Enqueued continuation workflow task for session %s",
        sanitize_log_value(session_id),
    )


def verify_cloud_tasks_secret(provided_secret: Optional[str]) -> bool:
    """Return True if the provided secret matches the configured CLOUD_TASKS_SECRET.

    Uses constant-time comparison to prevent timing attacks.
    """
    settings = get_settings()
    expected = settings.cloud_tasks_secret
    if not expected or not provided_secret:
        return False
    return secrets.compare_digest(provided_secret, expected)


# =============================================================================
# INTERNAL
# =============================================================================


async def _enqueue_task(
    *,
    settings: Any,
    payload: Dict[str, Any],
) -> None:
    """Create a Cloud Tasks HTTP task targeting the internal execute endpoint."""
    if not _TASKS_AVAILABLE:
        raise RuntimeError(
            "google-cloud-tasks is not installed. "
            "Add it to requirements.txt to use Cloud Tasks dispatch."
        )
    project_id = _extract_project_from_service_url(settings.cloud_tasks_service_url)
    client = _get_tasks_client()

    queue_path = client.queue_path(
        project_id,
        settings.cloud_tasks_location,
        settings.cloud_tasks_queue_name,
    )

    dispatch_deadline = duration_pb2.Duration(seconds=DISPATCH_DEADLINE_SECONDS)

    task = tasks_v2.Task(
        http_request=tasks_v2.HttpRequest(
            http_method=tasks_v2.HttpMethod.POST,
            url=f"{settings.cloud_tasks_service_url.rstrip('/')}/api/v1/internal/workflow/execute",
            headers={
                "Content-Type": "application/json",
                "X-CloudTasks-Secret": settings.cloud_tasks_secret,
            },
            body=json.dumps(payload).encode("utf-8"),
            oidc_token=tasks_v2.OidcToken(
                service_account_email=settings.cloud_tasks_service_account,
                audience=settings.cloud_tasks_service_url,
            ),
        ),
        dispatch_deadline=dispatch_deadline,
    )

    def _create() -> None:
        client.create_task(parent=queue_path, task=task)  # type: ignore[union-attr]

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _create)
