"""
REST API endpoints for managing job applications with comprehensive CRUD operations.
Provides advanced filtering, pagination, search functionality, and detailed analytics.
"""

import uuid
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta, timezone
import logging

from fastapi import APIRouter, Depends, Query, HTTPException, status, Response
from pydantic import BaseModel, Field, field_validator
from utils.logging_config import get_structured_logger, mask_email, sanitize_log_value
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case, or_, exists

from utils.auth import get_current_user_with_complete_profile
from utils.database import get_database
from utils.error_responses import internal_error, not_found_error, validation_error
from config.settings import get_settings
from models.database import (
    ApplicationStatus,
    JobApplication,
    UserProfile,
    WorkflowSession,
    WorkflowStatusEnum,
)

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

# Pagination constants
DEFAULT_PAGE_SIZE: int = 10
MAX_PAGE_SIZE: int = 100
MIN_PAGE: int = 1

# Time period constants
RECENT_DAYS_THRESHOLD: int = 30
STATS_LOOKBACK_DAYS: int = 365
MILLISECONDS_PER_DAY: int = 1000 * 60 * 60 * 24

# Analytics constants
TOP_COMPANIES_LIMIT: int = 5
DEFAULT_STATS_PRECISION: int = 1

# Report constants
MAX_JOB_DESCRIPTION_LENGTH: int = 6000
REPORT_HEADER_SEPARATOR: str = "=" * 80
REPORT_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
REPORT_SECTION_SEPARATOR: str = "\n" + "=" * 80
REPORT_SUBSECTION_PREFIX: str = "\n### "
REPORT_SUBSECTION_SUFFIX: str = " ###"
REPORT_EMPTY_VALUE: str = "Not specified"
REPORT_LIST_ITEM_PREFIX: str = "- "
REPORT_DECIMAL_PLACES: int = 1

# Sort order constants
ASCENDING: int = 1
DESCENDING: int = -1
SORT_ASCENDING: str = "asc"
SORT_DESCENDING: str = "desc"
DEFAULT_SORT_FIELD: str = "created_at"
DEFAULT_SORT_ORDER: str = SORT_DESCENDING


# =============================================================================
# GLOBAL VARIABLES
# =============================================================================

logger: logging.Logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)
settings = get_settings()
router: APIRouter = APIRouter()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def safe_items(obj: Any) -> List[Tuple[Any, Any]]:
    """Safely get items from a dictionary-like object, or return empty list if not a dict."""
    if isinstance(obj, dict):
        return list(obj.items())
    return []


def get_user_uuid(current_user: Dict[str, Any]) -> uuid.UUID:
    """Extract and convert user ID to UUID."""
    user_id = current_user.get("id") or current_user.get("_id")
    if isinstance(user_id, str):
        return uuid.UUID(user_id)
    return user_id


def _dashboard_application_visibility_filter(user_id: uuid.UUID):
    """Rows visible on the dashboard: not soft-deleted, not failed in DB, and not failed in workflow.

    Job applications can stay ``processing`` while ``workflow_sessions.workflow_status`` is
    already ``failed`` (race or before ``_update_job_application_with_final_state``). The
    formatter maps that to ``failed`` for the client — exclude those rows here so failed
    analyses never appear as cards.

    Implemented with ``EXISTS`` instead of ``LEFT JOIN workflow_sessions`` so pagination
    never sees duplicated ``job_applications`` rows if more than one joined row could match.
    """
    workflow_failed = exists(
        select(WorkflowSession.session_id).where(
            WorkflowSession.session_id == JobApplication.session_id,
            WorkflowSession.workflow_status == WorkflowStatusEnum.FAILED.value,
        )
    )
    return and_(
        JobApplication.user_id == user_id,
        JobApplication.deleted_at.is_(None),
        JobApplication.status != ApplicationStatus.FAILED.value,
        or_(
            JobApplication.session_id.is_(None),
            ~workflow_failed,
        ),
    )


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class ApplicationResponse(BaseModel):
    """Response model for application data."""

    id: str = Field(..., description="Unique application identifier")
    job_title: str = Field(..., description="Job title or position name")
    company_name: str = Field(..., description="Company or organization name")
    job_url: Optional[str] = Field(None, description="Original job posting URL")
    match_score: Optional[float] = Field(
        None, description="Profile match score (0.0-1.0)"
    )
    status: str = Field(..., description="Current application status")
    applied_date: Optional[datetime] = Field(
        None, description="Date when application was submitted"
    )
    response_date: Optional[datetime] = Field(
        None, description="Date when response was received"
    )
    notes: Optional[str] = Field(None, description="User's personal notes")
    created_at: datetime = Field(..., description="Application creation timestamp")
    updated_at: datetime = Field(..., description="Last modification timestamp")
    workflow_session_id: Optional[str] = Field(
        None, description="Associated workflow session identifier"
    )
    workflow_data: Dict[str, Any] = Field(
        default_factory=dict, description="Complete workflow session data"
    )


class ApplicationListResponse(BaseModel):
    """Response model for paginated application list."""

    applications: List[ApplicationResponse] = Field(
        ..., description="List of application records"
    )
    total: int = Field(
        ..., description="Total number of applications (across all pages)"
    )
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Number of items per page")
    has_next: bool = Field(..., description="Whether there are more pages available")
    has_prev: bool = Field(
        ..., description="Whether there are previous pages available"
    )


class ApplicationStatsResponse(BaseModel):
    """Response model for basic application statistics for dashboard display."""

    total: int = Field(..., description="Total number of applications")
    applied: int = Field(
        ...,
        description=(
            "Applications past analysis with any user tracking stage "
            "(applied, interview, offer, or rejected — all imply a submission)"
        ),
    )
    interviews: int = Field(
        ..., description="Number of applications with 'interview' status"
    )
    response_rate: float = Field(
        ...,
        description=(
            "Percentage (0-100): (interview + offer + rejected) divided by "
            "all tracked funnel rows (applied + interview + offer + rejected). "
            "Analysis-only rows (e.g. completed) are excluded from denominator."
        ),
    )


def _validate_application_status(v: str) -> str:
    valid_statuses = [s.value for s in ApplicationStatus]
    if v not in valid_statuses:
        raise ValueError(f"Invalid status. Must be one of: {valid_statuses}")
    return v


class StatusUpdateRequest(BaseModel):
    """Request model for application status updates."""

    new_status: str = Field(..., description="New application status")

    validate_status = field_validator("new_status")(_validate_application_status)


class NotesUpdateRequest(BaseModel):
    """Request model for updating application notes."""

    notes: str = Field(..., description="User's personal notes", max_length=5000)


# =============================================================================
# API ENDPOINTS
# =============================================================================


@router.get("/", response_model=ApplicationListResponse)
async def list_applications(
    current_user: Dict[str, Any] = Depends(get_current_user_with_complete_profile),
    db: AsyncSession = Depends(get_database),
    page: int = Query(default=1, ge=1, le=10000),
    per_page: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    status_filter: Optional[str] = Query(default=None),
    days: Optional[int] = Query(default=None, ge=1, le=365, description="Filter by last N days"),
    company: Optional[str] = Query(default=None, max_length=200, description="Partial company name search"),
    search: Optional[str] = Query(default=None, max_length=200, description="Search across job title and company name"),
    sort: Optional[str] = Query(
        default="created_desc",
        description="Sort order: created_desc | created_asc | updated_desc | company_asc | title_asc",
    ),
) -> ApplicationListResponse:
    """List user's job applications with filtering, sorting, and pagination."""
    try:
        user_id = get_user_uuid(current_user)

        # Build query — exclude soft-deleted, DB-failed, and workflow-failed rows (no JOIN —
        # visibility uses EXISTS so OFFSET/LIMIT cannot duplicate rows).
        query = select(JobApplication).where(_dashboard_application_visibility_filter(user_id))

        # Add status filter if specified (case-insensitive)
        if status_filter:
            query = query.where(
                func.lower(JobApplication.status) == status_filter.lower()
            )

        # Add date filter if specified
        if days:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            query = query.where(JobApplication.created_at >= cutoff_date)

        # Full-text search across job title and company name (takes priority over company-only filter)
        if search:
            term = search.lower()
            query = query.where(
                or_(
                    func.lower(JobApplication.job_title).contains(term),
                    func.lower(JobApplication.company_name).contains(term),
                )
            )
        elif company:
            # Partial company name search (case-insensitive) — legacy param kept for API compat
            query = query.where(
                func.lower(JobApplication.company_name).contains(company.lower())
            )

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply sort order. Secondary sort by primary key makes OFFSET/LIMIT pagination stable
        # when many rows share the same timestamp or title — without it, PostgreSQL may reorder
        # ties arbitrarily across requests, producing duplicate rows on "load more".
        sort_map = {
            "created_asc":  (JobApplication.created_at.asc(), JobApplication.id.asc()),
            "updated_desc": (JobApplication.updated_at.desc(), JobApplication.id.desc()),
            "company_asc":  (func.lower(JobApplication.company_name).asc(), JobApplication.id.asc()),
            "title_asc":    (func.lower(JobApplication.job_title).asc(), JobApplication.id.asc()),
        }
        order_clauses = sort_map.get(sort or "", (JobApplication.created_at.desc(), JobApplication.id.desc()))
        query = query.order_by(*order_clauses)
        query = query.offset((page - 1) * per_page).limit(per_page)

        # Execute query
        result = await db.execute(query)
        applications = result.scalars().all()

        # Batch-load all workflow sessions for this page in a single query
        session_ids = [app.session_id for app in applications if app.session_id]
        workflow_sessions_map: Dict[str, Any] = {}
        if session_ids:
            ws_result = await db.execute(
                select(WorkflowSession).where(WorkflowSession.session_id.in_(session_ids))
            )
            for ws in ws_result.scalars().all():
                workflow_sessions_map[ws.session_id] = ws

        # Format applications for response
        formatted_applications = []
        for app in applications:
            formatted_app = await _format_application_response(app, db, workflow_sessions_map)
            formatted_applications.append(formatted_app)

        has_next: bool = (page - 1) * per_page + per_page < total
        has_prev: bool = page > MIN_PAGE

        return ApplicationListResponse(
            applications=formatted_applications,
            total=total,
            page=page,
            per_page=per_page,
            has_next=has_next,
            has_prev=has_prev,
        )

    except Exception as e:
        logger.error('Failed to list applications: %s', sanitize_log_value(e), exc_info=True)
        raise internal_error("Failed to list applications")


@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user_with_complete_profile),
    db: AsyncSession = Depends(get_database),
) -> ApplicationResponse:
    """Get a single application by ID (dashboard visibility rules apply)."""
    try:
        user_id = get_user_uuid(current_user)
        try:
            app_uuid = uuid.UUID(application_id)
        except ValueError:
            raise validation_error("Invalid application ID format")

        result = await db.execute(
            select(JobApplication).where(
                and_(
                    JobApplication.id == app_uuid,
                    _dashboard_application_visibility_filter(user_id),
                )
            )
        )
        application = result.scalar_one_or_none()
        if not application:
            raise not_found_error("Application")

        return await _format_application_response(application, db)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get application: %s", sanitize_log_value(e), exc_info=True)
        raise internal_error("Failed to get application")


@router.patch("/{application_id}/status", response_model=ApplicationResponse)
async def update_application_status(
    application_id: str,
    status_update: StatusUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user_with_complete_profile),
    db: AsyncSession = Depends(get_database),
) -> ApplicationResponse:
    """Update application status only."""
    try:
        try:
            app_uuid = uuid.UUID(application_id)
        except ValueError:
            raise validation_error("Invalid application ID format")

        user_id = get_user_uuid(current_user)

        result = await db.execute(
            select(JobApplication).where(
                and_(
                    JobApplication.id == app_uuid,
                    JobApplication.user_id == user_id,
                    JobApplication.deleted_at.is_(None),
                )
            )
        )
        existing_app = result.scalar_one_or_none()

        if not existing_app:
            raise not_found_error("Application not found")

        existing_app.status = status_update.new_status
        existing_app.updated_at = datetime.now(timezone.utc)

        if (
            status_update.new_status == ApplicationStatus.APPLIED.value
            and not existing_app.applied_date
        ):
            existing_app.applied_date = datetime.now(timezone.utc)

        if status_update.new_status in [
            ApplicationStatus.INTERVIEW.value,
            ApplicationStatus.ACCEPTED.value,
            ApplicationStatus.REJECTED.value,
        ] and not existing_app.response_date:
            existing_app.response_date = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(existing_app)

        logger.info('Updated application status to %s for application %s', sanitize_log_value(status_update.new_status), sanitize_log_value(application_id))

        return await _format_application_response(existing_app, db)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error('Failed to update application status: %s', sanitize_log_value(e), exc_info=True)
        raise internal_error("Failed to update application status")


@router.patch("/{application_id}/notes", response_model=ApplicationResponse)
async def update_application_notes(
    application_id: str,
    notes_update: NotesUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user_with_complete_profile),
    db: AsyncSession = Depends(get_database),
) -> ApplicationResponse:
    """Update application notes."""
    try:
        try:
            app_uuid = uuid.UUID(application_id)
        except ValueError:
            raise validation_error("Invalid application ID format")

        user_id = get_user_uuid(current_user)

        result = await db.execute(
            select(JobApplication).where(
                and_(
                    JobApplication.id == app_uuid,
                    JobApplication.user_id == user_id,
                    JobApplication.deleted_at.is_(None),
                )
            )
        )
        existing_app = result.scalar_one_or_none()

        if not existing_app:
            raise not_found_error("Application not found")

        existing_app.notes = notes_update.notes
        existing_app.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(existing_app)

        logger.info('Updated notes for application %s', sanitize_log_value(application_id))
        return await _format_application_response(existing_app, db)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error('Failed to update application notes: %s', sanitize_log_value(e), exc_info=True)
        raise internal_error("Failed to update application notes")


@router.delete("/{application_id}")
async def delete_application(
    application_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user_with_complete_profile),
    db: AsyncSession = Depends(get_database),
):
    """Delete an application and its associated data."""
    try:
        try:
            app_uuid = uuid.UUID(application_id)
        except ValueError:
            raise validation_error("Invalid application ID format")

        user_id = get_user_uuid(current_user)

        result = await db.execute(
            select(JobApplication).where(
                and_(
                    JobApplication.id == app_uuid,
                    JobApplication.user_id == user_id,
                    JobApplication.deleted_at.is_(None),
                )
            )
        )
        existing_app = result.scalar_one_or_none()

        if not existing_app:
            raise not_found_error("Application not found")

        # Soft delete — preserves workflow data for audit purposes
        existing_app.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info('Soft-deleted application %s for user %s', sanitize_log_value(application_id), mask_email(current_user['email']))

        return {"message": "Application deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error('Failed to delete application: %s', sanitize_log_value(e), exc_info=True)
        raise internal_error("Failed to delete application")


@router.get("/stats/overview", response_model=ApplicationStatsResponse)
async def get_application_stats(
    current_user: Dict[str, Any] = Depends(get_current_user_with_complete_profile),
    db: AsyncSession = Depends(get_database),
) -> ApplicationStatsResponse:
    """Get simple application statistics for dashboard display."""
    try:
        user_id = get_user_uuid(current_user)

        # "Response" = user recorded employer-side movement (not merely submitted).
        response_statuses = [
            ApplicationStatus.INTERVIEW.value,
            ApplicationStatus.ACCEPTED.value,
            ApplicationStatus.REJECTED.value,
        ]
        # "Applied" card = any funnel stage (submitted / progressed / closed).
        applied_tracking_statuses = [
            ApplicationStatus.APPLIED.value,
            ApplicationStatus.INTERVIEW.value,
            ApplicationStatus.ACCEPTED.value,
            ApplicationStatus.REJECTED.value,
        ]

        # Single query with conditional aggregation — replaces 4 separate COUNT queries
        stats_result = await db.execute(
            select(
                func.count().label("total"),
                func.sum(
                    case(
                        (
                            JobApplication.status.in_(applied_tracking_statuses),
                            1,
                        ),
                        else_=0,
                    )
                ).label("applied"),
                func.sum(
                    case(
                        (JobApplication.status == ApplicationStatus.INTERVIEW.value, 1),
                        else_=0,
                    )
                ).label("interviews"),
                func.sum(
                    case(
                        (JobApplication.status.in_(response_statuses), 1),
                        else_=0,
                    )
                ).label("responses"),
            )
            .select_from(JobApplication)
            .where(_dashboard_application_visibility_filter(user_id))
        )
        row = stats_result.one()
        total: int = row.total or 0
        applied: int = row.applied or 0
        interviews: int = row.interviews or 0
        responses: int = row.responses or 0

        # Of tracked funnel apps only — not diluted by analysis-only "completed" rows.
        tracked: int = applied
        if tracked > 0:
            response_rate: float = (responses / tracked) * 100
        else:
            response_rate = 0.0

        logger.info('Stats generated for user %s: total=%s, applied=%s, interviews=%s, responses=%s, response_rate=%s%%', sanitize_log_value(user_id), sanitize_log_value(total), sanitize_log_value(applied), sanitize_log_value(interviews), sanitize_log_value(responses), sanitize_log_value(response_rate))

        return ApplicationStatsResponse(
            total=total,
            applied=applied,
            interviews=interviews,
            response_rate=round(response_rate, 1),
        )

    except Exception as e:
        logger.error('Failed to get application stats: %s', sanitize_log_value(e), exc_info=True)
        raise internal_error("Failed to get application statistics")


# =============================================================================
# DOWNLOAD APPLICATION DATA
# =============================================================================


@router.get(
    "/{application_id}/download",
    response_class=Response,
    status_code=status.HTTP_200_OK,
)
async def get_application_download(
    application_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user_with_complete_profile),
    db: AsyncSession = Depends(get_database),
):
    """Generate a downloadable file with comprehensive application data."""
    try:
        user_id = get_user_uuid(current_user)

        try:
            app_uuid = uuid.UUID(application_id)
        except ValueError:
            raise validation_error("Invalid application ID format")

        result = await db.execute(
            select(JobApplication).where(
                and_(
                    JobApplication.id == app_uuid,
                    JobApplication.user_id == user_id,
                    JobApplication.deleted_at.is_(None),
                )
            )
        )
        application = result.scalar_one_or_none()

        if not application:
            logger.warning('Application %s not found for user %s', sanitize_log_value(application_id), sanitize_log_value(user_id))
            raise not_found_error("Application not found")

        session_id = application.session_id

        if not session_id:
            logger.warning('Application %s has no workflow session ID', sanitize_log_value(application_id))
            raise not_found_error("No workflow data found for this application")

        workflow_result = await db.execute(
            select(WorkflowSession).where(
                and_(
                    WorkflowSession.session_id == session_id,
                    WorkflowSession.user_id == user_id,
                )
            )
        )
        workflow_session = workflow_result.scalar_one_or_none()

        if not workflow_session:
            logger.warning('Workflow session %s not found', sanitize_log_value(session_id))
            raise not_found_error("Workflow data not found")

        workflow_data = workflow_session.to_dict()

        profile_result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        user_profile = profile_result.scalar_one_or_none()
        user_data = user_profile.to_dict() if user_profile else {}

        file_content: str = await _generate_application_report(
            application.to_dict(), workflow_data, user_data
        )
        job_title: str = (application.job_title or "Job").replace(" ", "_")
        company_name: str = (application.company_name or "Company").replace(" ", "_")

        job_title_clean: str = re.sub(r"[^a-zA-Z0-9]", "_", job_title)
        company_name_clean: str = re.sub(r"[^a-zA-Z0-9]", "_", company_name)
        filename: str = f"{company_name_clean}_{job_title_clean}_Application.txt"
        headers: Dict[str, str] = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/plain",
        }

        return Response(content=file_content, headers=headers)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error generating application download: %s",
            sanitize_log_value(e),
            exc_info=True,
        )
        raise internal_error("Failed to generate application download")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


async def _format_application_response(
    application: JobApplication,
    db: AsyncSession,
    workflow_sessions_map: Optional[Dict[str, Any]] = None,
) -> ApplicationResponse:
    """Format application for API response.

    Args:
        application: The JobApplication ORM object.
        db: Database session (used only when workflow_sessions_map is not provided).
        workflow_sessions_map: Optional pre-loaded {session_id: WorkflowSession} map.
            Pass this when formatting a list of applications to avoid N+1 queries.
    """
    session_id = application.session_id
    workflow_data = {}

    if session_id:
        try:
            if workflow_sessions_map is not None:
                workflow_session = workflow_sessions_map.get(session_id)
            else:
                result = await db.execute(
                    select(WorkflowSession).where(WorkflowSession.session_id == session_id)
                )
                workflow_session = result.scalar_one_or_none()

            if workflow_session:
                workflow_data = workflow_session.to_dict()
        except Exception as e:
            logger.error('Error fetching workflow session data: %s', sanitize_log_value(e), exc_info=True)

    # Fallback to workflow session data when application fields are missing
    job_title = application.job_title
    company_name = application.company_name
    match_score = application.match_score
    app_status = application.status

    if workflow_data:
        job_analysis = workflow_data.get("job_analysis", {})
        if not job_title and job_analysis:
            job_title = job_analysis.get("job_title")
        if not company_name and job_analysis:
            company_name = job_analysis.get("company_name")

        # Fix status: sync application status with workflow status when out of date
        ws_status = workflow_data.get("workflow_status", "")
        if app_status == ApplicationStatus.PROCESSING.value:
            if ws_status == "completed":
                app_status = ApplicationStatus.COMPLETED.value
            elif ws_status == "failed":
                app_status = ApplicationStatus.FAILED.value

        # Fallback match score from profile matching
        if match_score is None:
            profile_matching = workflow_data.get("profile_matching", {})
            if profile_matching:
                final_scores = profile_matching.get("final_scores", {})
                if final_scores:
                    match_score = (
                        final_scores.get("overall_match_score")
                        or final_scores.get("overall_fit_score")
                        or final_scores.get("weighted_recommendation_score")
                    )
                if match_score is None:
                    match_score = (
                        profile_matching.get("overall_score")
                        or profile_matching.get("overall_match_score")
                    )

    return ApplicationResponse(
        id=str(application.id),
        job_title=job_title or "",
        company_name=company_name or "",
        job_url=application.job_url,
        match_score=match_score,
        status=app_status,
        applied_date=application.applied_date,
        response_date=application.response_date,
        notes=application.notes,
        created_at=application.created_at,
        updated_at=application.updated_at,
        workflow_session_id=session_id,
        workflow_data=workflow_data,
    )


async def _generate_application_report(
    application: Dict[str, Any],
    workflow_data: Dict[str, Any],
    user_data: Dict[str, Any],
) -> str:
    """Generate a detailed report for application download."""
    lines: List[str] = []

    lines.append("JOB APPLICATION REPORT")
    lines.append(REPORT_HEADER_SEPARATOR)
    lines.append(f"Generated on: {datetime.now(timezone.utc).strftime(REPORT_DATE_FORMAT)} UTC")
    lines.append(REPORT_HEADER_SEPARATOR + "\n")

    job_title = application.get("job_title", REPORT_EMPTY_VALUE)
    company_name = application.get("company_name", REPORT_EMPTY_VALUE)
    lines.append(f"JOB TITLE: {job_title}")
    lines.append(f"COMPANY NAME: {company_name}")

    application_status = application.get("status", REPORT_EMPTY_VALUE)
    workflow_status = workflow_data.get("workflow_status", "")
    if application_status == "processing" and workflow_status == "completed":
        application_status = "COMPLETED"
    lines.append(f"APPLICATION STATUS: {application_status}")

    applied_date = application.get("applied_date")
    if applied_date:
        if isinstance(applied_date, datetime):
            applied_date = applied_date.strftime("%Y-%m-%d")
        lines.append(f"APPLIED DATE: {applied_date}")

    job_analysis = workflow_data.get("job_analysis", {})
    if job_analysis:
        lines.append(REPORT_SECTION_SEPARATOR)
        lines.append("JOB ANALYSIS")
        lines.append(REPORT_HEADER_SEPARATOR)
        _add_dict_section(lines, job_analysis)

    company_research = workflow_data.get("company_research", {})
    if company_research:
        lines.append(REPORT_SECTION_SEPARATOR)
        lines.append("COMPANY RESEARCH")
        lines.append(REPORT_HEADER_SEPARATOR)
        _add_dict_section(lines, company_research)

    profile_matching = workflow_data.get("profile_matching", {})
    if profile_matching:
        lines.append(REPORT_SECTION_SEPARATOR)
        lines.append("PROFILE MATCHING")
        lines.append(REPORT_HEADER_SEPARATOR)
        exec_summary = profile_matching.get("executive_summary", {})
        if exec_summary:
            rec = exec_summary.get("recommendation", "N/A")
            conf = exec_summary.get("confidence", "N/A")
            verdict = exec_summary.get("one_line_verdict", "N/A")
            lines.append(f"\nRecommendation: {rec}")
            lines.append(f"Confidence: {conf}")
            lines.append(f"Verdict: {verdict}")
        final_scores = profile_matching.get("final_scores", {})
        if final_scores:
            lines.append("\nScores:")
            for key, value in safe_items(final_scores):
                if isinstance(value, (int, float)):
                    pct = value * 100
                    lines.append(f"  {key.replace('_', ' ').title()}: {pct:.1f}%")

    resume_recs = workflow_data.get("resume_recommendations", {})
    if resume_recs:
        lines.append(REPORT_SECTION_SEPARATOR)
        lines.append("RESUME RECOMMENDATIONS")
        lines.append(REPORT_HEADER_SEPARATOR)
        _add_dict_section(lines, resume_recs)

    cover_letter = workflow_data.get("cover_letter", {})
    if cover_letter:
        lines.append(REPORT_SECTION_SEPARATOR)
        lines.append("COVER LETTER")
        lines.append(REPORT_HEADER_SEPARATOR)
        content = cover_letter.get("content", "")
        if content:
            lines.append(f"\n{content}")

    lines.append("\n" + "-" * 80)
    lines.append("END OF REPORT")
    lines.append(REPORT_SECTION_SEPARATOR)

    return "\n".join(lines)


def _add_dict_section(lines: List[str], data: Dict[str, Any]) -> None:
    """Add a dict section to the report lines."""
    for key, value in safe_items(data):
        if value is not None and value != "" and value != []:
            if isinstance(value, list):
                lines.append(f"\n{key.replace('_', ' ').title()}:")
                for item in value:
                    lines.append(f"  {REPORT_LIST_ITEM_PREFIX}{item}")
            elif isinstance(value, dict):
                lines.append(f"\n{key.replace('_', ' ').title()}:")
                for k, v in safe_items(value):
                    lines.append(f"  {k}: {v}")
            else:
                lines.append(f"{key.replace('_', ' ').title()}: {value}")
