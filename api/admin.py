"""
Admin API endpoints for system management.
Provides maintenance mode control and system status.
Protected by the require_admin dependency — only users with is_admin=True may call these.
"""

import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select, func, case, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import User, WorkflowSession, JobApplication, WorkflowStatusEnum
from utils.auth import require_admin
from utils.database import get_database, get_session
from utils.error_responses import APIError, internal_error, unauthorized_error
from utils.logging_config import mask_email, sanitize_log_value
from utils.maintenance import (
    get_maintenance_info,
    enable_maintenance_mode,
    disable_maintenance_mode,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class MaintenanceRequest(BaseModel):
    """Request model for maintenance mode."""
    
    enabled: bool = Field(..., description="Enable or disable maintenance mode")
    message: Optional[str] = Field(
        None, 
        description="Custom maintenance message to display",
        max_length=500
    )
    estimated_end: Optional[str] = Field(
        None,
        description="Estimated end time (e.g., '2 hours', '15:00 UTC')",
        max_length=100
    )


class MaintenanceResponse(BaseModel):
    """Response model for maintenance status."""
    
    enabled: bool
    message: Optional[str]
    estimated_end: Optional[str]


# =============================================================================
# ADMIN ENDPOINTS
# =============================================================================


@router.get("/maintenance", response_model=MaintenanceResponse)
async def get_maintenance_status(
    current_user: Dict[str, Any] = Depends(require_admin),
) -> MaintenanceResponse:
    """
    Get current maintenance mode status.
    
    Args:
        current_user: Authenticated user (required)
        
    Returns:
        Current maintenance mode status and settings
    """
    try:
        info = await get_maintenance_info()
        return MaintenanceResponse(
            enabled=info.get("enabled", False),
            message=info.get("message"),
            estimated_end=info.get("estimated_end"),
        )
    except Exception as e:
        logger.error(f"Failed to get maintenance status: {e}", exc_info=True)
        raise internal_error("Failed to get maintenance status")


@router.post("/maintenance", response_model=MaintenanceResponse)
async def set_maintenance_mode(
    request_data: MaintenanceRequest,
    current_user: Dict[str, Any] = Depends(require_admin),
) -> MaintenanceResponse:
    """
    Enable or disable maintenance mode. Requires admin role.

    Args:
        request_data: Maintenance mode settings
        current_user: Authenticated user (required)
        
    Returns:
        Updated maintenance mode status
        
    Raises:
        HTTPException: 500 if operation fails
    """
    try:
        user_email = current_user.get("email", "unknown")
        
        if request_data.enabled:
            # Enable maintenance mode
            success = await enable_maintenance_mode(
                message=request_data.message,
                estimated_end=request_data.estimated_end,
            )
            if not success:
                raise internal_error("Failed to enable maintenance mode. Check Redis connection.")
            logger.warning(
                "Maintenance mode ENABLED by %s. Message: %s, Estimated end: %s",
                mask_email(user_email),
                sanitize_log_value(request_data.message),
                sanitize_log_value(request_data.estimated_end),
            )
        else:
            # Disable maintenance mode
            success = await disable_maintenance_mode()
            if not success:
                raise internal_error("Failed to disable maintenance mode. Check Redis connection.")
            logger.info(f"Maintenance mode DISABLED by {mask_email(user_email)}")
        
        # Return updated status
        info = await get_maintenance_info()
        return MaintenanceResponse(
            enabled=info.get("enabled", False),
            message=info.get("message"),
            estimated_end=info.get("estimated_end"),
        )
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"Failed to set maintenance mode: {e}", exc_info=True)
        raise internal_error("Failed to update maintenance mode")


@router.delete("/maintenance")
async def clear_maintenance_mode(
    current_user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, str]:
    """
    Quick endpoint to disable maintenance mode.
    
    Equivalent to POST with enabled=false.
    
    Args:
        current_user: Authenticated user (required)
        
    Returns:
        Success message
    """
    try:
        user_email = current_user.get("email", "unknown")
        
        success = await disable_maintenance_mode()
        if not success:
            raise internal_error("Failed to disable maintenance mode")
        
        logger.info(f"Maintenance mode DISABLED by {mask_email(user_email)}")
        return {"message": "Maintenance mode disabled successfully"}
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"Failed to disable maintenance mode: {e}", exc_info=True)
        raise internal_error("Failed to disable maintenance mode")


# =============================================================================
# BUSINESS METRICS
# =============================================================================


class WorkflowMetrics(BaseModel):
    """Breakdown of workflow session counts by status."""

    total: int
    completed: int
    failed: int
    in_progress: int
    success_rate_pct: float


class MetricsResponse(BaseModel):
    """Response model for the admin metrics endpoint."""

    generated_at: str
    users: Dict[str, int]
    workflows: WorkflowMetrics
    applications: Dict[str, int]


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    current_user: Dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_database),
) -> MetricsResponse:
    """
    Return aggregate business metrics pulled live from the database.

    Args:
        current_user: Authenticated admin user
        db: Database session

    Returns:
        MetricsResponse with user, workflow, and application stats

    Raises:
        APIError: 500 if database query fails
    """
    try:
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)
        seven_days_ago = now - timedelta(days=7)

        # ── Users ──────────────────────────────────────────────────────────
        total_users = await db.scalar(select(func.count(User.id)))
        new_users_30d = await db.scalar(
            select(func.count(User.id)).where(User.created_at >= thirty_days_ago)
        )
        active_users_7d = await db.scalar(
            select(func.count(User.id)).where(User.last_login >= seven_days_ago)
        )
        verified_users = await db.scalar(
            select(func.count(User.id)).where(User.email_verified.is_(True))
        )

        # ── Workflows ──────────────────────────────────────────────────────
        workflow_counts = (
            await db.execute(
                select(
                    func.count(WorkflowSession.session_id).label("total"),
                    func.sum(
                        case(
                            (WorkflowSession.workflow_status == WorkflowStatusEnum.COMPLETED.value, 1),
                            else_=0,
                        )
                    ).label("completed"),
                    func.sum(
                        case(
                            (WorkflowSession.workflow_status == WorkflowStatusEnum.FAILED.value, 1),
                            else_=0,
                        )
                    ).label("failed"),
                    func.sum(
                        case(
                            (WorkflowSession.workflow_status == WorkflowStatusEnum.IN_PROGRESS.value, 1),
                            else_=0,
                        )
                    ).label("in_progress"),
                )
            )
        ).one()

        wf_total = int(workflow_counts.total or 0)
        wf_completed = int(workflow_counts.completed or 0)
        wf_failed = int(workflow_counts.failed or 0)
        wf_in_progress = int(workflow_counts.in_progress or 0)
        success_rate = round((wf_completed / wf_total * 100) if wf_total > 0 else 0.0, 1)

        # ── Applications ───────────────────────────────────────────────────
        total_applications = await db.scalar(
            select(func.count(JobApplication.id)).where(
                JobApplication.deleted_at.is_(None)
            )
        )
        new_applications_30d = await db.scalar(
            select(func.count(JobApplication.id)).where(
                JobApplication.deleted_at.is_(None),
                JobApplication.created_at >= thirty_days_ago,
            )
        )

        return MetricsResponse(
            generated_at=now.isoformat(),
            users={
                "total": int(total_users or 0),
                "new_last_30d": int(new_users_30d or 0),
                "active_last_7d": int(active_users_7d or 0),
                "email_verified": int(verified_users or 0),
            },
            workflows=WorkflowMetrics(
                total=wf_total,
                completed=wf_completed,
                failed=wf_failed,
                in_progress=wf_in_progress,
                success_rate_pct=success_rate,
            ),
            applications={
                "total": int(total_applications or 0),
                "new_last_30d": int(new_applications_30d or 0),
            },
        )

    except Exception as e:
        logger.error(f"Failed to fetch metrics: {e}", exc_info=True)
        raise internal_error("Failed to fetch metrics")


# =============================================================================
# INTERNAL — CLOUD SCHEDULER ENDPOINTS
# =============================================================================


@router.post(
    "/internal/cleanup/orphaned-sessions",
    include_in_schema=False,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def cleanup_orphaned_sessions(request: Request) -> Response:
    """Internal endpoint invoked by Cloud Scheduler to reset stuck workflow sessions.

    Resets any session in INITIALIZED or IN_PROGRESS state that has been idle
    for more than 2 hours to FAILED, so users receive clear feedback rather
    than an endlessly spinning UI.

    Security: requests must carry the X-Scheduler-Secret header matching the
    CLOUD_SCHEDULER_SECRET env var. The Cloud Scheduler job delivers it over
    HTTPS so it is encrypted in transit.
    """
    from config.settings import get_settings as _get_settings
    _settings = _get_settings()

    provided_secret = request.headers.get("X-Scheduler-Secret")
    expected_secret = getattr(_settings, "cloud_scheduler_secret", None)

    if not expected_secret or not provided_secret:
        raise unauthorized_error("Unauthorized")
    if not secrets.compare_digest(provided_secret, expected_secret):
        raise unauthorized_error("Unauthorized")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    orphaned_statuses = ["initialized", "in_progress"]

    try:
        async with get_session() as db:
            result = await db.execute(
                update(WorkflowSession)
                .where(
                    WorkflowSession.workflow_status.in_(orphaned_statuses),
                    WorkflowSession.processing_start_time < cutoff,
                )
                .values(
                    workflow_status="failed",
                    error_messages=["Session interrupted by a server event. Please re-submit your job."],
                )
                .returning(WorkflowSession.session_id)
            )
            rows = result.fetchall()
            await db.commit()

        logger.info(
            "Cloud Scheduler cleanup: reset %d orphaned workflow session(s) to 'failed'",
            len(rows),
        )
    except Exception as e:
        logger.error("Orphaned session cleanup failed: %s", e, exc_info=True)
        raise internal_error("Cleanup failed")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
