"""
API endpoints for Job Finder chat (company careers discovery).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from api.websocket import (
    broadcast_job_finder_error,
    broadcast_job_finder_message,
    broadcast_job_finder_status,
)
from api.workflow import start_workflow_from_job_finder
from config.settings import get_settings
from models.database import JobFinderSession, UserProfile
from utils.auth import get_current_user_with_complete_profile
from utils.cache import (
    check_rate_limit_with_headers,
    clear_job_finder_turn_lock,
    set_job_finder_turn_lock,
)
from utils.database import get_database
from utils.error_responses import (
    APIError,
    ErrorCode,
    internal_error,
    not_found_error,
    rate_limit_error,
    validation_error,
)
from utils.job_finder.orchestrator import JobFinderOrchestrator, make_message
from utils.llm_context import require_user_llm_context
from utils.logging_config import sanitize_log_value
from utils.security import sanitize_text

logger = logging.getLogger(__name__)
router = APIRouter()

RATE_LIMIT_CHAT = 30
RATE_LIMIT_WINDOW = 3600


# =============================================================================
# MODELS
# =============================================================================


class JobFinderSessionResponse(BaseModel):
    """Job Finder session payload."""

    id: str
    status: str
    phase: str = "await_filter_confirm"
    confirmed_filters: Dict[str, Any] = Field(default_factory=dict)
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    last_board: Dict[str, Any] = Field(default_factory=dict)
    last_listings: List[Dict[str, Any]] = Field(default_factory=list)


class MessageRequest(BaseModel):
    """User chat turn."""

    content: str = Field(..., min_length=1, max_length=4000)


class SelectRequest(BaseModel):
    """Select jobs to add to applications."""

    job_ids: List[str] = Field(..., min_length=1, max_length=30)


class CareersUrlRequest(BaseModel):
    """Manual careers URL fallback."""

    url: str = Field(..., min_length=10, max_length=2000)
    company_name: Optional[str] = Field(None, max_length=200)

    @field_validator("url")
    @classmethod
    def validate_careers_url(cls, v: str) -> str:
        """Require https careers URLs only."""
        url = (v or "").strip()
        if not url.startswith("https://"):
            raise ValueError("Careers URL must start with https://")
        return url


class SelectItemResult(BaseModel):
    """Per-job select outcome."""

    job_id: str
    ok: bool
    application_id: Optional[str] = None
    session_id: Optional[str] = None
    error_code: Optional[str] = None
    message: Optional[str] = None


class SelectResponse(BaseModel):
    """Batch select response (partial success OK)."""

    results: List[SelectItemResult]
    started: int
    failed: int


# =============================================================================
# HELPERS
# =============================================================================


def _user_uuid(current_user: Dict[str, Any]) -> uuid.UUID:
    user_id = current_user.get("id") or current_user.get("_id")
    if isinstance(user_id, str):
        return uuid.UUID(user_id)
    return user_id


def _phase_from_session(session: JobFinderSession) -> str:
    extras = (session.confirmed_filters or {}).get("_phase")
    if isinstance(extras, str) and extras:
        return extras
    # Infer
    if session.last_listings:
        return "await_selection"
    if session.confirmed_filters and session.confirmed_filters.get("_confirmed"):
        return "await_company"
    return "await_filter_confirm"


def _set_phase(filters: Dict[str, Any], phase: str) -> Dict[str, Any]:
    out = dict(filters or {})
    out["_phase"] = phase
    if phase != "await_filter_confirm":
        out["_confirmed"] = True
    return out


def _to_response(session: JobFinderSession) -> JobFinderSessionResponse:
    return JobFinderSessionResponse(
        id=str(session.id),
        status=session.status,
        phase=_phase_from_session(session),
        confirmed_filters={
            k: v
            for k, v in (session.confirmed_filters or {}).items()
            if not str(k).startswith("_")
        },
        messages=session.messages or [],
        last_board=session.last_board or {},
        last_listings=session.last_listings or [],
    )


async def _load_owned_session(
    db: AsyncSession, session_id: str, user_id: uuid.UUID
) -> JobFinderSession:
    try:
        sid = uuid.UUID(session_id)
    except ValueError as exc:
        raise validation_error("Invalid session id") from exc
    result = await db.execute(
        select(JobFinderSession).where(
            and_(
                JobFinderSession.id == sid,
                JobFinderSession.user_id == user_id,
            )
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise not_found_error("Job Finder session")
    return row


async def _load_profile_dict(
    db: AsyncSession, user_id: uuid.UUID, current_user: Dict[str, Any]
) -> Dict[str, Any]:
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise validation_error("Complete your profile before using Find jobs.")
    data = profile.to_dict()
    data["full_name"] = current_user.get("full_name", "")
    data["email"] = current_user.get("email", "")
    return data


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.post("/sessions", response_model=JobFinderSessionResponse)
async def create_session(
    current_user: Dict[str, Any] = Depends(get_current_user_with_complete_profile),
    db: AsyncSession = Depends(get_database),
) -> JobFinderSessionResponse:
    """Create a Job Finder chat session with filter proposal."""
    settings = get_settings()
    if not getattr(settings, "job_finder_enabled", True):
        raise validation_error("Job Finder is temporarily unavailable.")

    user_id = _user_uuid(current_user)
    await require_user_llm_context(db, user_id)

    # Archive previous active sessions
    existing = await db.execute(
        select(JobFinderSession).where(
            and_(
                JobFinderSession.user_id == user_id,
                JobFinderSession.status == "active",
            )
        )
    )
    for row in existing.scalars().all():
        row.status = "archived"

    profile = await _load_profile_dict(db, user_id, current_user)
    orch = JobFinderOrchestrator()
    messages, proposed, phase = orch.initial_assistant_messages(profile)
    filters = _set_phase(proposed.to_dict(), phase)

    session = JobFinderSession(
        id=uuid.uuid4(),
        user_id=user_id,
        status="active",
        confirmed_filters=filters,
        messages=messages,
        last_board={},
        last_listings=[],
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return _to_response(session)


@router.get("/sessions/active", response_model=JobFinderSessionResponse)
async def get_active_session(
    current_user: Dict[str, Any] = Depends(get_current_user_with_complete_profile),
    db: AsyncSession = Depends(get_database),
) -> JobFinderSessionResponse:
    """Resume the active Job Finder session if any."""
    user_id = _user_uuid(current_user)
    result = await db.execute(
        select(JobFinderSession)
        .where(
            and_(
                JobFinderSession.user_id == user_id,
                JobFinderSession.status == "active",
            )
        )
        .order_by(JobFinderSession.updated_at.desc())
    )
    row = result.scalars().first()
    if not row:
        raise not_found_error("Job Finder session")
    return _to_response(row)


@router.get("/sessions/{session_id}", response_model=JobFinderSessionResponse)
async def get_session(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user_with_complete_profile),
    db: AsyncSession = Depends(get_database),
) -> JobFinderSessionResponse:
    """Get a Job Finder session by id."""
    user_id = _user_uuid(current_user)
    session = await _load_owned_session(db, session_id, user_id)
    return _to_response(session)


@router.post("/sessions/{session_id}/messages", response_model=JobFinderSessionResponse)
async def post_message(
    session_id: str,
    body: MessageRequest,
    response: Response,
    current_user: Dict[str, Any] = Depends(get_current_user_with_complete_profile),
    db: AsyncSession = Depends(get_database),
) -> JobFinderSessionResponse:
    """Send a user chat turn and receive assistant reply messages."""
    settings = get_settings()
    if not getattr(settings, "job_finder_enabled", True):
        raise validation_error("Job Finder is temporarily unavailable.")

    user_id = _user_uuid(current_user)
    _user, llm_ctx, _prefs = await require_user_llm_context(db, user_id)

    rate = await check_rate_limit_with_headers(
        identifier=f"{user_id}:job_finder_chat:30ph",
        limit=RATE_LIMIT_CHAT,
        window_seconds=RATE_LIMIT_WINDOW,
    )
    for header, value in rate.get_headers().items():
        response.headers[header] = value
    if not rate.allowed:
        raise rate_limit_error(
            f"Rate limit exceeded. Maximum {RATE_LIMIT_CHAT} Find jobs messages per hour."
        )

    session = await _load_owned_session(db, session_id, user_id)
    claimed = await set_job_finder_turn_lock(str(user_id), session_id)
    if not claimed:
        raise APIError(
            ErrorCode.RESOURCE_CONFLICT,
            "A Find jobs reply is already in progress. Please wait a moment.",
            status_code=409,
        )

    try:
        await broadcast_job_finder_status(
            str(user_id), session_id, status="thinking"
        )
        profile = await _load_profile_dict(db, user_id, current_user)
        user_msg = make_message("user", sanitize_text(body.content))
        messages = list(session.messages or [])
        messages.append(user_msg)

        orch = JobFinderOrchestrator()
        result = await orch.handle_user_message(
            user_text=body.content,
            phase=_phase_from_session(session),
            confirmed_filters=session.confirmed_filters,
            last_listings=session.last_listings,
            profile=profile,
            user_api_key=llm_ctx.user_api_key,
            model=llm_ctx.preferred_model,
            llm_provider=llm_ctx.provider,
        )

        for am in result.get("assistant_messages") or []:
            messages.append(am)

        session.messages = messages
        session.confirmed_filters = _set_phase(
            result.get("confirmed_filters") or {},
            result.get("phase") or "await_company",
        )
        if result.get("last_board") is not None:
            session.last_board = result.get("last_board") or {}
        if result.get("last_listings") is not None:
            session.last_listings = result.get("last_listings") or []
        flag_modified(session, "messages")
        flag_modified(session, "confirmed_filters")
        flag_modified(session, "last_board")
        flag_modified(session, "last_listings")
        await db.commit()
        await db.refresh(session)
        # Broadcast after commit so clients never see unpersisted messages
        for am in result.get("assistant_messages") or []:
            await broadcast_job_finder_message(str(user_id), session_id, message=am)
        return _to_response(session)
    except APIError:
        raise
    except Exception as exc:
        logger.error(
            "Job finder message failed: %s",
            sanitize_log_value(str(exc)),
            exc_info=True,
        )
        await broadcast_job_finder_error(
            str(user_id), session_id, "Something went wrong. Please try again."
        )
        raise internal_error("Find jobs turn failed")
    finally:
        await clear_job_finder_turn_lock(str(user_id), session_id)


@router.post("/sessions/{session_id}/careers-url", response_model=JobFinderSessionResponse)
async def post_careers_url(
    session_id: str,
    body: CareersUrlRequest,
    response: Response,
    current_user: Dict[str, Any] = Depends(get_current_user_with_complete_profile),
    db: AsyncSession = Depends(get_database),
) -> JobFinderSessionResponse:
    """Paste a company careers URL when auto-resolve fails."""
    settings = get_settings()
    if not getattr(settings, "job_finder_enabled", True):
        raise validation_error("Job Finder is temporarily unavailable.")

    user_id = _user_uuid(current_user)
    await require_user_llm_context(db, user_id)

    rate = await check_rate_limit_with_headers(
        identifier=f"{user_id}:job_finder_chat:30ph",
        limit=RATE_LIMIT_CHAT,
        window_seconds=RATE_LIMIT_WINDOW,
    )
    for header, value in rate.get_headers().items():
        response.headers[header] = value
    if not rate.allowed:
        raise rate_limit_error(
            f"Rate limit exceeded. Maximum {RATE_LIMIT_CHAT} Find jobs messages per hour."
        )

    session = await _load_owned_session(db, session_id, user_id)
    claimed = await set_job_finder_turn_lock(str(user_id), session_id)
    if not claimed:
        raise APIError(
            ErrorCode.RESOURCE_CONFLICT,
            "A Find jobs reply is already in progress. Please wait a moment.",
            status_code=409,
        )

    try:
        profile = await _load_profile_dict(db, user_id, current_user)
        orch = JobFinderOrchestrator()
        company = (body.company_name or "").strip() or "Company"
        text = f"{company} {body.url.strip()}"
        result = await orch.handle_user_message(
            user_text=text,
            phase="await_company",
            confirmed_filters=session.confirmed_filters,
            last_listings=session.last_listings,
            profile=profile,
            user_api_key=None,
            model=None,
            llm_provider=None,
        )
        messages = list(session.messages or [])
        messages.append(make_message("user", f"Careers URL: {body.url.strip()}"))
        for am in result.get("assistant_messages") or []:
            messages.append(am)
        session.messages = messages
        session.confirmed_filters = _set_phase(
            result.get("confirmed_filters") or {},
            result.get("phase") or "await_company",
        )
        session.last_board = result.get("last_board") or {}
        session.last_listings = result.get("last_listings") or []
        flag_modified(session, "messages")
        flag_modified(session, "confirmed_filters")
        flag_modified(session, "last_board")
        flag_modified(session, "last_listings")
        await db.commit()
        await db.refresh(session)
        for am in result.get("assistant_messages") or []:
            await broadcast_job_finder_message(str(user_id), session_id, message=am)
        return _to_response(session)
    except APIError:
        raise
    except Exception as exc:
        logger.error(
            "Job finder careers-url failed: %s",
            sanitize_log_value(str(exc)),
            exc_info=True,
        )
        await broadcast_job_finder_error(
            str(user_id), session_id, "Something went wrong. Please try again."
        )
        raise internal_error("Find jobs careers URL failed")
    finally:
        await clear_job_finder_turn_lock(str(user_id), session_id)


@router.post("/sessions/{session_id}/select", response_model=SelectResponse)
async def select_jobs(
    session_id: str,
    body: SelectRequest,
    background_tasks: BackgroundTasks,
    current_user: Dict[str, Any] = Depends(get_current_user_with_complete_profile),
    db: AsyncSession = Depends(get_database),
) -> SelectResponse:
    """
    Add selected careers roles to Applications (sequential workflow starts).

    Partial success is returned as HTTP 200 with per-item errors.
    """
    user_id = _user_uuid(current_user)
    await require_user_llm_context(db, user_id)
    session = await _load_owned_session(db, session_id, user_id)

    listings_by_id = {
        str(j.get("id")): j for j in (session.last_listings or []) if j.get("id")
    }
    results: List[SelectItemResult] = []
    started = 0
    failed = 0

    for job_id in body.job_ids:
        job = listings_by_id.get(job_id)
        if not job:
            results.append(
                SelectItemResult(
                    job_id=job_id,
                    ok=False,
                    error_code="VAL_2001",
                    message="Job not found in current listings",
                )
            )
            failed += 1
            continue

        desc = (job.get("description_text") or "").strip()
        if len(desc) < 40:
            # Minimal synthetic JD so analyzer still has text
            desc = (
                f"Job title: {job.get('title')}\n"
                f"Company: {job.get('company')}\n"
                f"Location: {job.get('location')}\n"
                f"Posting URL: {job.get('url')}\n"
            )

        try:
            out = await start_workflow_from_job_finder(
                background_tasks=background_tasks,
                db=db,
                current_user=current_user,
                job_text=desc,
                job_url=job.get("url"),
                detected_title=job.get("title"),
                detected_company=job.get("company"),
            )
            results.append(
                SelectItemResult(
                    job_id=job_id,
                    ok=True,
                    application_id=out.get("application_id"),
                    session_id=out.get("session_id"),
                )
            )
            started += 1
        except APIError as api_err:
            try:
                await db.rollback()
            except Exception:
                logger.debug(
                    "Rollback after job_finder select APIError failed",
                    exc_info=True,
                )
            try:
                await db.refresh(session)
            except Exception:
                logger.debug(
                    "Refresh session after job_finder select rollback failed",
                    exc_info=True,
                )
            code = getattr(api_err, "error_code", None)
            code_str = getattr(code, "value", None) or str(code or "ERROR")
            results.append(
                SelectItemResult(
                    job_id=job_id,
                    ok=False,
                    error_code=code_str,
                    message=getattr(api_err, "message", None) or str(api_err.detail),
                )
            )
            failed += 1
            if code_str.startswith("RATE"):
                break
        except Exception as exc:
            try:
                await db.rollback()
            except Exception:
                logger.debug(
                    "Rollback after job_finder select failure failed",
                    exc_info=True,
                )
            try:
                await db.refresh(session)
            except Exception:
                logger.debug(
                    "Refresh session after job_finder select exception failed",
                    exc_info=True,
                )
            logger.error(
                "Job finder select failed for %s: %s",
                sanitize_log_value(job_id),
                sanitize_log_value(str(exc)),
                exc_info=True,
            )
            results.append(
                SelectItemResult(
                    job_id=job_id,
                    ok=False,
                    error_code="INT_9001",
                    message="Failed to start analysis",
                )
            )
            failed += 1

    # Chat follow-up
    messages = list(session.messages or [])
    if started:
        messages.append(
            make_message(
                "assistant",
                f"Started analysis for **{started}** role(s). "
                "They’ll appear under **Applications**. Want another company?",
            )
        )
        session.messages = messages
        session.confirmed_filters = _set_phase(
            session.confirmed_filters or {}, "post_select"
        )
        flag_modified(session, "messages")
        flag_modified(session, "confirmed_filters")
        try:
            await db.commit()
        except Exception as exc:
            logger.error(
                "Job finder select follow-up commit failed: %s",
                sanitize_log_value(str(exc)),
                exc_info=True,
            )
            try:
                await db.rollback()
            except Exception:
                logger.debug("Rollback after select commit failure", exc_info=True)

    return SelectResponse(results=results, started=started, failed=failed)


@router.delete("/sessions/{session_id}")
async def archive_session(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user_with_complete_profile),
    db: AsyncSession = Depends(get_database),
) -> Dict[str, str]:
    """Archive a Job Finder session."""
    user_id = _user_uuid(current_user)
    session = await _load_owned_session(db, session_id, user_id)
    session.status = "archived"
    await db.commit()
    return {"status": "archived", "id": session_id}
