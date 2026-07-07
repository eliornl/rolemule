"""
REST API endpoints for managing workflow processing.
Provides endpoints for starting, monitoring, and managing job application workflows.
"""

import hashlib
import re
import unicodedata
import uuid
from datetime import datetime, timezone
import logging
import asyncio
from typing import Dict, Any, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
    BackgroundTasks,
    UploadFile,
    File,
    Form,
    Response,
)
from pydantic import BaseModel, Field, validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update, func
from sqlalchemy.exc import IntegrityError

from utils.auth import get_current_user, get_current_user_with_complete_profile
from utils.database import get_database, get_session
from utils.error_reporting import report_exception
from utils.cloud_tasks import (
    enqueue_workflow_task,
    enqueue_continue_workflow_task,
    verify_cloud_tasks_secret,
)
from utils.llm_client import (
    is_llm_quota_or_rate_limit_exception,
    user_facing_message_from_llm_exception,
    _GEMINI_QUOTA_USER_MESSAGE,
)
from config.settings import get_settings
from utils.cache import (
    get_cached_workflow_state,
    cache_workflow_state,
    invalidate_workflow_state,
    check_rate_limit,
    check_rate_limit_with_headers,
)
from workflows.state_schema import (
    WorkflowPhase,
    WorkflowStatus,
    InputMethod,
)
from workflows.job_application_workflow import JobApplicationWorkflow
from api.websocket import (
    broadcast_workflow_resumed,
    broadcast_document_generation_started,
    broadcast_workflow_error,
)
from models.database import (
    ApplicationStatus,
    JobApplication,
    WorkflowSession,
    UserProfile,
    User,
    UserWorkflowPreferences,
)
from utils.encryption import decrypt_api_key
from utils.error_responses import (
    APIError,
    ErrorCode,
    internal_error,
    no_api_key_error,
    not_found_error,
    rate_limit_error,
    unauthorized_error,
    validation_error,
)
from utils.security import sanitize_llm_output
from utils.application_dedupe import normalize_title_company_key as _normalize_title_company_key
from utils.resume_parser import extract_text_from_docx, extract_text_from_pdf
from utils.logging_config import mask_email as _mask_email, sanitize_log_value

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

# URL validation
MIN_URL_LENGTH: int = 10
MAX_URL_LENGTH: int = 2000
MAX_TEXT_LENGTH: int = 50000


def _is_http_or_https_url(url: str) -> bool:
    """Return True when url uses http(s) and has a host (not substring-only checks)."""
    parsed = urlparse(url.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)

# File processing
MAX_FILE_SIZE: int = 5 * 1024 * 1024  # 5 MB
MIN_EXTRACTED_JOB_FILE_TEXT_LEN: int = 50
ALLOWED_FILE_TYPES: List[str] = [
    "application/pdf",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]
ALLOWED_FILE_EXTENSIONS: List[str] = [".pdf", ".txt", ".docx"]

# Magic bytes for MIME-type validation (prevents extension spoofing)
_JOB_FILE_MAGIC: Dict[str, Optional[bytes]] = {
    ".pdf": b"%PDF",
    ".txt": None,  # UTF-8 text has no fixed signature
    ".docx": b"PK\x03\x04",  # Office Open XML (ZIP) — same signature as resume DOCX
}

# Processing timeouts
WORKFLOW_TIMEOUT_SECONDS: int = 300  # 5 minutes

# Status mapping
STATUS_DISPLAY_MAP: Dict[str, str] = {
    "initialized": "Starting",
    "in_progress": "In Progress",
    "completed": "Completed",
    "failed": "Failed",
    "awaiting_confirmation": "Awaiting Confirmation",
    "analysis_complete": "Analysis Complete",
}

# =============================================================================
# GLOBAL VARIABLES
# =============================================================================

logger: logging.Logger = logging.getLogger(__name__)
settings = get_settings()
router: APIRouter = APIRouter()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _job_text_from_uploaded_file(file_content: bytes, matched_ext: str) -> str:
    """
    Turn uploaded job file bytes into plain text for the workflow.

    PDFs must be parsed with PyMuPDF — raw UTF-8 decoding of PDF bytes does not
    expose the visible job text to the LLM.
    """
    if matched_ext == ".pdf":
        try:
            text = extract_text_from_pdf(file_content)
        except ValueError as e:
            logger.debug("PDF text extraction failed for job upload: %s", e, exc_info=True)
            raise validation_error(
                "Could not read text from this PDF. If it is a scanned document, "
                "try pasting the job description as text instead."
            ) from e
        text = text.strip()
        if len(text) < MIN_EXTRACTED_JOB_FILE_TEXT_LEN:
            raise validation_error(
                "Could not extract enough text from this PDF. It may be image-only or "
                "protected. Try pasting the job description as text."
            )
        return text
    if matched_ext == ".txt":
        text = file_content.decode("utf-8").strip()
        if len(text) < MIN_EXTRACTED_JOB_FILE_TEXT_LEN:
            raise validation_error("Job description file is too short.")
        return text
    if matched_ext == ".docx":
        try:
            text = extract_text_from_docx(file_content)
        except ValueError as e:
            logger.debug("DOCX text extraction failed for job upload: %s", e, exc_info=True)
            raise validation_error(
                "Could not read text from this Word file. Try pasting the job description as text "
                "or exporting as PDF."
            ) from e
        text = text.strip()
        if len(text) < MIN_EXTRACTED_JOB_FILE_TEXT_LEN:
            raise validation_error(
                "Could not extract enough text from this document. Try pasting the full job posting."
            )
        return text
    raise validation_error(f"Unsupported job file type: {matched_ext}")


def _job_text_from_uploaded_file_with_ext(
    file_content: bytes,
    matched_ext: Optional[str],
) -> str:
    """Extract job text from an uploaded file; ``matched_ext`` must match the upload."""
    if not matched_ext:
        raise validation_error("Invalid file upload state.")
    return _job_text_from_uploaded_file(file_content, matched_ext)


def _agent_error_message(exc: Exception, fallback: str, *, debug: bool = False) -> str:
    """
    User-safe agent failure text; surfaces Gemini quota copy when applicable.
    """
    if debug:
        return str(exc)
    friendly = user_facing_message_from_llm_exception(exc)
    if friendly == _GEMINI_QUOTA_USER_MESSAGE:
        return friendly
    return fallback


def _raise_if_agent_soft_failure(payload: Dict[str, Any]) -> None:
    """
    Raise when an agent returned an error blob (quota, timeout, etc.) instead of real output.

    Prevents persisting fallback JSON that the dashboard would render as partial resume tips.
    """
    if not isinstance(payload, dict):
        return

    check: Dict[str, Any] = payload
    nested = payload.get("comprehensive_advice")
    if isinstance(nested, dict):
        check = nested

    if not (check.get("error") or check.get("parse_error")):
        return

    raw = str(check.get("error_message") or "Generation failed")
    exc = Exception(raw)
    message = user_facing_message_from_llm_exception(exc)
    if is_llm_quota_or_rate_limit_exception(exc):
        raise rate_limit_error(message)
    raise APIError(
        ErrorCode.EXTERNAL_SERVICE_ERROR,
        message,
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _safe_error_msg(exc: Exception, debug: bool = False) -> str:
    """
    Return a client-safe error message from an exception.
    In debug mode returns the raw str(exc); in production returns Gemini quota
    guidance when applicable, otherwise a generic retry message.
    """
    return _agent_error_message(
        exc,
        "Workflow processing failed due to an internal error. Please try again.",
        debug=debug,
    )


async def _soft_delete_job_application_for_failed_workflow(
    db: AsyncSession,
    session_id: str,
) -> None:
    """
    Remove the dashboard card for a failed analysis (soft-delete).

    Workflow sessions keep error details for support; job_applications rows are
    hidden from list/stats like user-initiated deletes.
    """
    now = datetime.now(timezone.utc)
    await db.execute(
        update(JobApplication)
        .where(
            JobApplication.session_id == session_id,
            JobApplication.deleted_at.is_(None),
        )
        .values(
            deleted_at=now,
            status=ApplicationStatus.FAILED.value,
            updated_at=now,
        )
    )


_WORKFLOW_SESSION_AGENT_OUTPUT_COLUMNS = (
    "job_analysis",
    "company_research",
    "profile_matching",
    "resume_recommendations",
    "cover_letter",
)


def _strip_agent_outputs_on_session_model(workflow_session: WorkflowSession) -> None:
    """Clear persisted agent JSONB blobs when a workflow fails (no partial results)."""
    from sqlalchemy.orm.attributes import flag_modified

    for col in _WORKFLOW_SESSION_AGENT_OUTPUT_COLUMNS:
        setattr(workflow_session, col, None)
        flag_modified(workflow_session, col)


# Same user-facing copy as POST /workflow/start RES_3002 and analyzer-time dedupe.
_DUPLICATE_JOB_CONSTRAINT_MESSAGE = (
    "You already have an application for this job. Open it from your dashboard, "
    "or delete the old one first if you want to start over."
)


async def _revert_workflow_session_after_duplicate_job_constraint(
    db: AsyncSession,
    session_id: str,
) -> Optional[str]:
    """
    The workflow session row was already committed as COMPLETED with agent outputs, but
    the follow-up ``job_applications`` update hit ``uq_user_job_company``. Revert the
    session to failed and strip JSONB so we do not leave a duplicate visible via analysis
    fallbacks.
    """
    from sqlalchemy.orm.attributes import flag_modified

    result = await db.execute(
        select(WorkflowSession).where(WorkflowSession.session_id == session_id)
    )
    ws = result.scalar_one_or_none()
    if not ws:
        return None
    ws.workflow_status = WorkflowStatus.FAILED.value
    ws.current_phase = WorkflowPhase.ERROR.value
    msgs = list(ws.error_messages or [])
    if _DUPLICATE_JOB_CONSTRAINT_MESSAGE not in msgs:
        msgs.append(_DUPLICATE_JOB_CONSTRAINT_MESSAGE)
    ws.error_messages = msgs
    flag_modified(ws, "error_messages")
    ws.processing_end_time = datetime.now(timezone.utc)
    _strip_agent_outputs_on_session_model(ws)
    return str(ws.user_id)


def get_user_uuid(current_user: Dict[str, Any]) -> uuid.UUID:
    """Extract and convert user ID to UUID."""
    user_id = current_user.get("id") or current_user.get("_id")
    if isinstance(user_id, str):
        return uuid.UUID(user_id)
    return user_id


def _canonical_job_url(url: str) -> str:
    """
    Normalize job posting URLs for duplicate detection.

    Lowercases scheme and host, trims trailing slashes on the path, drops URL
    fragments, and strips common tracking query parameters so two links to the
    same posting are more likely to match.
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "https").lower()
    netloc = (parsed.netloc or "").lower()
    path = (parsed.path or "").rstrip("/")
    query_str = ""
    if parsed.query:
        qs = parse_qs(parsed.query, keep_blank_values=True)
        noise = frozenset(
            k.lower()
            for k in qs
            if k.lower().startswith("utm_")
            or k.lower()
            in {
                "gclid",
                "fbclid",
                "igshid",
                "mc_eid",
                "_ga",
                "ref",
            }
        )
        filtered: list[tuple[str, str]] = []
        for k in sorted(qs.keys()):
            if k.lower() in noise:
                continue
            for v in qs[k]:
                filtered.append((k, v))
        query_str = urlencode(filtered, doseq=True) if filtered else ""
    return urlunparse((scheme, netloc, path, "", query_str, ""))


# Minimum length before we trust a content hash for deduplication (avoids collisions on tiny inputs).
_MIN_JOB_CONTENT_FINGERPRINT_CHARS: int = 80


def _fingerprint_job_content(raw: Optional[str]) -> Optional[str]:
    """
    Stable SHA-256 hex digest of normalized job posting text (manual / file / extension).

    Used to block starting a second workflow when the user pastes the same posting twice
    without a URL or pre-detected title/company (cases the DB unique index does not catch
    until after analysis).

    Normalization aligns extension-extracted text with manual paste (Unicode NFKC,
    strip zero-width characters, collapse whitespace).
    """
    if not raw or not isinstance(raw, str):
        return None
    text = unicodedata.normalize("NFKC", raw)
    text = re.sub(r"[\u200b-\u200d\ufeff\u2060]", "", text)
    normalized = " ".join(text.strip().lower().split())
    if len(normalized) < _MIN_JOB_CONTENT_FINGERPRINT_CHARS:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def _find_duplicate_active_application(
    db: AsyncSession,
    user_id: uuid.UUID,
    effective_job_url: Optional[str],
    detected_title: Optional[str],
    detected_company: Optional[str],
    content_fingerprint: Optional[str],
) -> Optional[JobApplication]:
    """
    If the user already has a non-deleted application for the same job URL, the same
    title+company pair, or the same normalized job text (fingerprint), return that row.
    """
    if effective_job_url:
        canon = _canonical_job_url(effective_job_url)
        if canon:
            res = await db.execute(
                select(JobApplication).where(
                    JobApplication.user_id == user_id,
                    JobApplication.deleted_at.is_(None),
                    JobApplication.job_url.isnot(None),
                )
            )
            for row in res.scalars().all():
                if _canonical_job_url(row.job_url or "") == canon:
                    return row

    key = _normalize_title_company_key(detected_title, detected_company)
    if key is not None:
        nt, nc = key
        res2 = await db.execute(
            select(JobApplication)
            .where(
                JobApplication.user_id == user_id,
                JobApplication.deleted_at.is_(None),
                JobApplication.job_title.isnot(None),
                JobApplication.company_name.isnot(None),
                func.lower(func.btrim(JobApplication.job_title)) == nt,
                func.lower(func.btrim(JobApplication.company_name)) == nc,
            )
            .limit(1)
        )
        dup = res2.scalar_one_or_none()
        if dup:
            return dup

    if content_fingerprint:
        res3 = await db.execute(
            select(JobApplication)
            .join(
                WorkflowSession,
                JobApplication.session_id == WorkflowSession.session_id,
            )
            .where(
                JobApplication.user_id == user_id,
                JobApplication.deleted_at.is_(None),
                WorkflowSession.job_input_data.contains(
                    {"content_fingerprint": content_fingerprint}
                ),
            )
            .limit(1)
        )
        return res3.scalar_one_or_none()

    return None


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class WorkflowStartRequest(BaseModel):
    """Request model for starting a workflow."""

    job_url: Optional[str] = Field(
        None,
        min_length=MIN_URL_LENGTH,
        max_length=MAX_URL_LENGTH,
        description="Job posting URL from any job board or company careers page",
    )
    job_text: Optional[str] = Field(
        None,
        max_length=MAX_TEXT_LENGTH,
        description="Job posting text content",
    )
    # Extension-specific fields
    source: Optional[str] = Field(
        None,
        max_length=50,
        description="Source of the job data (e.g., 'extension', 'web')",
    )
    source_url: Optional[str] = Field(
        None,
        max_length=MAX_URL_LENGTH,
        description="URL where the job content was extracted from (for extension)",
    )
    detected_title: Optional[str] = Field(
        None,
        max_length=500,
        description="Job title detected by the extension",
    )
    detected_company: Optional[str] = Field(
        None,
        max_length=200,
        description="Company name detected by the extension",
    )

    @validator("job_url")
    def validate_url(cls, v):
        """Validate URL format and ensure it uses http:// or https://."""
        if v is None:
            return v
        trimmed = v.strip()
        if not _is_http_or_https_url(trimmed):
            raise ValueError("URL must start with http:// or https://")
        return trimmed


class WorkflowStatusResponse(BaseModel):
    """Response model for workflow status."""

    session_id: str = Field(..., description="Workflow session ID")
    status: str = Field(
        ...,
        description="Current workflow status (initialized, running, completed, failed, awaiting_confirmation)",
    )
    status_display: str = Field(
        ..., description="Human-readable status for display"
    )
    current_phase: str = Field(..., description="Current workflow phase")
    current_agent: Optional[str] = Field(None, description="Currently executing agent")
    agent_status: Dict[str, str] = Field(
        default_factory=dict, description="Status of each agent"
    )
    completed_agents: List[str] = Field(
        default_factory=list, description="List of completed agents"
    )
    error_messages: List[str] = Field(
        default_factory=list, description="Any error messages"
    )
    progress_percentage: int = Field(
        ..., description="Overall progress percentage (0-100)"
    )
    started_at: Optional[str] = Field(None, description="Workflow start time")
    completed_at: Optional[str] = Field(None, description="Workflow completion time")
    agent_durations: Dict[str, float] = Field(
        default_factory=dict, description="Duration of each agent in milliseconds"
    )


class WorkflowStartResponse(BaseModel):
    """Response model for workflow start."""

    session_id: str = Field(..., description="Created workflow session ID")
    status: str = Field(..., description="Initial status (initialized)")
    message: str = Field(..., description="Status message")


class WorkflowResultsResponse(BaseModel):
    """Response model for workflow results."""

    session_id: str = Field(..., description="Workflow session ID")
    status: str = Field(..., description="Final workflow status")
    job_url: Optional[str] = Field(None, description="Original job posting URL")
    application_id: Optional[str] = Field(None, description="Associated application ID")
    job_analysis: Optional[Dict[str, Any]] = Field(
        None, description="Job analysis results"
    )
    company_research: Optional[Dict[str, Any]] = Field(
        None, description="Company research results"
    )
    profile_matching: Optional[Dict[str, Any]] = Field(
        None, description="Profile matching results"
    )
    resume_recommendations: Optional[Dict[str, Any]] = Field(
        None, description="Resume recommendations"
    )
    cover_letter: Optional[Dict[str, Any]] = Field(
        None, description="Generated cover letter"
    )
    notes: Optional[str] = Field(None, description="User's personal notes")
    error_messages: List[str] = Field(
        default_factory=list, description="Any error messages from workflow"
    )


class WorkflowContinueResponse(BaseModel):
    """Response model for workflow continuation after gate decision."""

    session_id: str = Field(..., description="Workflow session ID")
    status: str = Field(..., description="Workflow status after continuation")
    message: str = Field(..., description="Status message")


class RegenerateCoverLetterResponse(BaseModel):
    """Response model for cover letter regeneration."""

    session_id: str = Field(..., description="Workflow session ID")
    cover_letter: Dict[str, Any] = Field(..., description="Regenerated cover letter")
    message: str = Field(..., description="Status message")


class RegenerateAgentResponse(BaseModel):
    """Generic response model for agent regeneration."""

    session_id: str = Field(..., description="Workflow session ID")
    result: Dict[str, Any] = Field(..., description="Regenerated agent output")
    message: str = Field(..., description="Status message")


# =============================================================================
# API ENDPOINTS
# =============================================================================


@router.post("/start", response_model=WorkflowStartResponse)
async def start_workflow(
    background_tasks: BackgroundTasks,
    response: Response,
    request: WorkflowStartRequest = None,
    job_file: UploadFile = File(None),
    job_url: Optional[str] = Form(None),
    job_text: Optional[str] = Form(None),
    detected_title_form: Optional[str] = Form(None, alias="detected_title"),
    detected_company_form: Optional[str] = Form(None, alias="detected_company"),
    source_form: Optional[str] = Form(None, alias="source"),
    source_url_form: Optional[str] = Form(None, alias="source_url"),
    current_user: Dict[str, Any] = Depends(get_current_user_with_complete_profile),
    db: AsyncSession = Depends(get_database),
) -> WorkflowStartResponse:
    """Start a new job application workflow with rate limiting."""
    try:
        user_id = get_user_uuid(current_user)
        
        # Rate limiting: 30 workflows per hour per user (with headers).
        # Identifier includes policy version so Redis counters reset when the limit changes.
        rate_result = await check_rate_limit_with_headers(
            identifier=f"{user_id}:workflow_start:30ph",
            limit=30,
            window_seconds=3600,  # 1 hour
        )
        
        # Add rate limit headers to response
        for header, value in rate_result.get_headers().items():
            response.headers[header] = value
        
        if not rate_result.allowed:
            raise rate_limit_error(f"Rate limit exceeded. Maximum 30 workflows per hour. Resets in {rate_result.reset_seconds} seconds.")

        # Concurrency guard: prevent two simultaneous start_workflow calls for the
        # same user (would create duplicate sessions and consume double LLM credits).
        try:
            from utils.redis_client import get_redis_client as _get_wf_rc
            from utils.error_responses import APIError as _APIError
            _wf_rc = await _get_wf_rc()
            if _wf_rc:
                _lock_key = f"workflow_creating:{user_id}"
                _acquired = await _wf_rc.set(_lock_key, "1", nx=True, ex=10)
                if not _acquired:
                    raise rate_limit_error("A workflow is already being created. Please wait a moment.", retry_after=10)
        except _APIError:
            raise
        except Exception as _lock_err:
            logger.warning(
                "Could not acquire workflow-creation lock for %s: %s",
                sanitize_log_value(user_id),
                sanitize_log_value(_lock_err),
            )
            # Fail open (best-effort) — proceed without the lock if Redis is unavailable

        # Resolve input from multiple sources
        resolved_url = job_url or (request.job_url if request else None)
        resolved_text = job_text or (request.job_text if request else None)
        file_content = None
        matched_ext: Optional[str] = None

        # Process uploaded file
        if job_file and job_file.filename:
            matched_ext = next(
                (ext for ext in ALLOWED_FILE_EXTENSIONS if job_file.filename.lower().endswith(ext)),
                None,
            )
            if not matched_ext:
                raise validation_error(f"File type not allowed. Allowed: {ALLOWED_FILE_EXTENSIONS}")

            file_content = await job_file.read()
            if len(file_content) > MAX_FILE_SIZE:
                raise validation_error(f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)} MB")

            # Validate file content matches the declared extension (prevents extension spoofing)
            expected_magic = _JOB_FILE_MAGIC.get(matched_ext)
            if expected_magic is not None and not file_content.startswith(expected_magic):
                raise validation_error("File content does not match the declared file type.")
            if matched_ext == ".txt":
                try:
                    file_content.decode("utf-8")
                except UnicodeDecodeError:
                    raise validation_error("TXT files must be UTF-8 encoded.")


        # Validate at least one input method
        if not resolved_url and not resolved_text and not file_content:
            raise validation_error("At least one input method is required: job_url, job_text, or job_file")

        # Get user profile data
        profile_result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        user_profile = profile_result.scalar_one_or_none()

        if not user_profile:
            raise validation_error("User profile not found. Please complete your profile setup.")

        # Get user's API key if available (BYOK mode)
        user_result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        
        user_api_key = None
        if user and user.gemini_api_key_encrypted:
            try:
                user_api_key = decrypt_api_key(user.gemini_api_key_encrypted)
            except Exception as e:
                logger.warning(f"Failed to decrypt user API key: {e}")
                # Continue without user key - will use server default if available

        # Check if we have an API key available (either user's or server's)
        from config.settings import get_settings
        settings = get_settings()
        server_has_key = bool(getattr(settings, 'gemini_api_key', None)) or getattr(
            settings, 'use_vertex_ai', False
        )
        
        if not user_api_key and not server_has_key:
            raise no_api_key_error()

        # Prepare input data for workflow
        user_data = user_profile.to_dict()

        # Add user info
        user_data.update({
            "full_name": current_user.get("full_name", ""),
            "email": current_user.get("email", ""),
        })

        # Load workflow preferences and inject under the key the workflow reads
        prefs_result = await db.execute(
            select(UserWorkflowPreferences).where(
                UserWorkflowPreferences.user_id == user_id
            )
        )
        prefs_row = prefs_result.scalar_one_or_none()
        user_data["application_preferences"] = (
            prefs_row.to_dict() if prefs_row else {}
        )

        # Get extension-specific metadata (JSON body takes priority; Form fields are the
        # extension path where request is None)
        source = (request.source if request else None) or source_form
        source_url = (request.source_url if request else None) or source_url_form
        detected_title = (request.detected_title if request else None) or detected_title_form
        detected_company = (request.detected_company if request else None) or detected_company_form

        effective_job_url = resolved_url if resolved_url else source_url

        # Never persist a non-http(s) URL as job_url. Unlike WorkflowStartRequest.job_url,
        # the form job_url field and source_url (JSON body or Form) are not schema-validated,
        # so the extension or a manual submit could supply an arbitrary scheme.
        if effective_job_url and not _is_http_or_https_url(effective_job_url):
            logger.warning("Discarding job URL with unsupported scheme on workflow start")
            effective_job_url = None
            source_url = None

        # Resolve input method and job text before duplicate check so we can fingerprint
        # pasted job descriptions (manual / file / extension) even without a URL.
        if resolved_url:
            input_method = InputMethod.URL.value
            job_input = resolved_url
            content_fingerprint: Optional[str] = None
        elif file_content:
            input_method = InputMethod.FILE.value
            job_input = _job_text_from_uploaded_file_with_ext(file_content, matched_ext)
            content_fingerprint = _fingerprint_job_content(job_input)
        elif source == "extension":
            input_method = InputMethod.EXTENSION.value
            job_input = resolved_text
            content_fingerprint = _fingerprint_job_content(resolved_text)
        else:
            input_method = InputMethod.MANUAL.value
            job_input = resolved_text
            content_fingerprint = _fingerprint_job_content(resolved_text)

        dup_row = await _find_duplicate_active_application(
            db,
            user_id,
            effective_job_url,
            detected_title,
            detected_company,
            content_fingerprint,
        )
        if dup_row:
            dup_details: List[Dict[str, Any]] = [
                {
                    "field": "application_id",
                    "message": str(dup_row.id),
                    "code": "DUPLICATE_APPLICATION",
                },
            ]
            if dup_row.session_id:
                dup_details.append(
                    {
                        "field": "session_id",
                        "message": dup_row.session_id,
                        "code": "DUPLICATE_APPLICATION",
                    }
                )
            # APIError subclasses HTTPException — outer handler re-raises HTTPException
            # without running the lock-release path; release workflow_creating here.
            try:
                from utils.redis_client import get_redis_client as _dup_wf_rc
                _dwrc = await _dup_wf_rc()
                if _dwrc:
                    await _dwrc.delete(f"workflow_creating:{user_id}")
            except Exception:
                logger.debug(
                    "Failed to release workflow creation lock after duplicate hit",
                    exc_info=True,
                )
            raise APIError(
                error_code=ErrorCode.RESOURCE_ALREADY_EXISTS,
                message="You already have an application for this job. Open it from your dashboard, or delete the old one first if you want to start over.",
                status_code=status.HTTP_409_CONFLICT,
                details=dup_details,
            )

        session_id = str(uuid.uuid4())

        # Create workflow session
        workflow_session = WorkflowSession(
            id=uuid.uuid4(),
            session_id=session_id,
            user_id=user_id,
            workflow_status=WorkflowStatus.INITIALIZED.value,
            current_phase=WorkflowPhase.INITIALIZATION.value,
            agent_status={},
            completed_agents=[],
            failed_agents=[],
            error_messages=[],
            warning_messages=[],
            job_input_data={
                "input_method": input_method,
                "job_input": job_input if not file_content else "[file content]",
                "source_url": source_url,  # URL where content was extracted (for extension)
                "detected_title": detected_title,  # Pre-detected job title
                "detected_company": detected_company,  # Pre-detected company name
                "content_fingerprint": content_fingerprint,
            },
            user_data=user_data,
            processing_start_time=datetime.now(timezone.utc),
        )

        # Create job application entry with job_url if available
        # For extension, use source_url as job_url (effective_job_url set above)
        job_application = JobApplication(
            id=uuid.uuid4(),
            user_id=user_id,
            session_id=session_id,
            status=ApplicationStatus.PROCESSING.value,
            job_url=effective_job_url,
            # Seed with detected values so the dashboard card shows something real
            # immediately. The Job Analyzer will overwrite these with AI-extracted
            # values once it completes (~4 s into the workflow).
            job_title=detected_title or None,
            company_name=detected_company or None,
        )

        # Add both records and commit in a single transaction so a failure
        # cannot leave an orphaned WorkflowSession without a JobApplication.
        db.add(workflow_session)
        db.add(job_application)
        await db.commit()

        effective_job_input = job_input

        # Dispatch workflow — prefer Cloud Tasks for automatic retry & separate timeout.
        # Falls back to FastAPI BackgroundTasks when Cloud Tasks is not configured.
        settings = get_settings()
        if settings.use_cloud_tasks:
            try:
                await enqueue_workflow_task(
                    session_id=session_id,
                    user_id=str(user_id),
                    input_method=input_method,
                    job_input=effective_job_input,
                    user_data=user_data,
                )
            except Exception as ct_err:
                logger.warning(
                    f"Cloud Tasks enqueue failed, falling back to BackgroundTasks: {ct_err}"
                )
                background_tasks.add_task(
                    _execute_workflow_background,
                    session_id=session_id,
                    user_id=str(user_id),
                    input_method=input_method,
                    job_input=effective_job_input,
                    user_data=user_data,
                    user_api_key=user_api_key,
                )
        else:
            background_tasks.add_task(
                _execute_workflow_background,
                session_id=session_id,
                user_id=str(user_id),
                input_method=input_method,
                job_input=effective_job_input,
                user_data=user_data,
                user_api_key=user_api_key,
            )

        logger.info(f"Started workflow {sanitize_log_value(session_id)} for user {_mask_email(current_user['email'])}")

        # Release the concurrency lock — session is committed, background task is
        # queued.  The next request for this user is now safe to proceed.
        try:
            from utils.redis_client import get_redis_client as _get_wf_rc2
            _wf_rc2 = await _get_wf_rc2()
            if _wf_rc2:
                await _wf_rc2.delete(f"workflow_creating:{user_id}")
        except Exception:
            logger.debug("Failed to release workflow creation lock (will auto-expire in 10s)", exc_info=True)

        return WorkflowStartResponse(
            session_id=session_id,
            status=WorkflowStatus.INITIALIZED.value,
            message="Workflow started successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        # Ensure lock is released on any failure path
        try:
            from utils.redis_client import get_redis_client as _get_wf_rc3
            _wf_rc3 = await _get_wf_rc3()
            if _wf_rc3:
                await _wf_rc3.delete(f"workflow_creating:{user_id}")
        except Exception:
            logger.debug("Failed to release workflow creation lock during error cleanup", exc_info=True)
        logger.error(f"Failed to start workflow: {e}", exc_info=True)
        raise internal_error("Failed to start workflow")


@router.get("/status/{session_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> WorkflowStatusResponse:
    """Get current workflow status with caching for frequent polling."""
    try:
        user_id = get_user_uuid(current_user)

        # Try cache first for active workflows (frequently polled)
        cached_state = await get_cached_workflow_state(session_id)
        if cached_state:
            # Verify ownership from cached data
            if cached_state.get("user_id") == str(user_id):
                return WorkflowStatusResponse(**cached_state)

        # Query for workflow session from database
        result = await db.execute(
            select(WorkflowSession).where(
                and_(
                    WorkflowSession.session_id == session_id,
                    WorkflowSession.user_id == user_id
                )
            )
        )
        workflow_session = result.scalar_one_or_none()

        if not workflow_session:
            raise not_found_error("Workflow session not found")

        # Calculate progress
        # analysis_complete means all 3 analysis agents ran successfully — show 100%
        workflow_status_val = workflow_session.workflow_status
        if workflow_status_val == "analysis_complete":
            progress = 100
        else:
            total_agents = 5
            completed_count = len(workflow_session.completed_agents or [])
            progress = int((completed_count / total_agents) * 100)

        workflow_status = workflow_session.workflow_status
        status_display = STATUS_DISPLAY_MAP.get(workflow_status, workflow_status)

        response_data = {
            "session_id": session_id,
            "user_id": str(user_id),  # For cache ownership verification
            "status": workflow_status,
            "status_display": status_display,
            "current_phase": workflow_session.current_phase,
            "current_agent": workflow_session.current_agent,
            "agent_status": workflow_session.agent_status or {},
            "completed_agents": workflow_session.completed_agents or [],
            "error_messages": workflow_session.error_messages or [],
            "progress_percentage": progress,
            "started_at": (
                workflow_session.processing_start_time.isoformat()
                if workflow_session.processing_start_time
                else None
            ),
            "completed_at": (
                workflow_session.processing_end_time.isoformat()
                if workflow_session.processing_end_time
                else None
            ),
            "agent_durations": workflow_session.agent_durations or {},
        }

        # Cache if workflow is still in progress (frequently polled)
        if workflow_status in [WorkflowStatus.INITIALIZED.value, WorkflowStatus.IN_PROGRESS.value]:
            await cache_workflow_state(session_id, response_data)

        return WorkflowStatusResponse(**response_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workflow status: {e}", exc_info=True)
        raise internal_error("Failed to get workflow status")


@router.get("/results/{session_id}", response_model=WorkflowResultsResponse)
async def get_workflow_results(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> WorkflowResultsResponse:
    """Get workflow results after completion."""
    try:
        user_id = get_user_uuid(current_user)

        # Query for workflow session
        result = await db.execute(
            select(WorkflowSession).where(
                and_(
                    WorkflowSession.session_id == session_id,
                    WorkflowSession.user_id == user_id
                )
            )
        )
        workflow_session = result.scalar_one_or_none()

        if not workflow_session:
            raise not_found_error("Workflow session not found")

        workflow_status = workflow_session.workflow_status

        # Allow results for completed, failed, awaiting_confirmation, or analysis_complete
        if workflow_status not in [
            WorkflowStatus.COMPLETED.value,
            WorkflowStatus.FAILED.value,
            WorkflowStatus.AWAITING_CONFIRMATION.value,
            "analysis_complete",
        ]:
            raise validation_error(f"Workflow is still {workflow_status}. Results are not yet available.")

        # Look up the associated application for job_url and notes
        app_result = await db.execute(
            select(JobApplication).where(
                and_(
                    JobApplication.session_id == session_id,
                    JobApplication.user_id == user_id
                )
            )
        )
        application = app_result.scalar_one_or_none()

        return WorkflowResultsResponse(
            session_id=session_id,
            status=workflow_status,
            job_url=application.job_url if application else None,
            application_id=str(application.id) if application else None,
            notes=application.notes if application else None,
            job_analysis=sanitize_llm_output(workflow_session.job_analysis) if workflow_session.job_analysis else None,
            company_research=sanitize_llm_output(workflow_session.company_research) if workflow_session.company_research else None,
            profile_matching=sanitize_llm_output(workflow_session.profile_matching) if workflow_session.profile_matching else None,
            resume_recommendations=sanitize_llm_output(workflow_session.resume_recommendations) if workflow_session.resume_recommendations else None,
            cover_letter=sanitize_llm_output(workflow_session.cover_letter) if workflow_session.cover_letter else None,
            error_messages=workflow_session.error_messages or [],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workflow results: {e}", exc_info=True)
        raise internal_error("Failed to get workflow results")


@router.post("/regenerate-cover-letter/{session_id}", response_model=RegenerateCoverLetterResponse)
async def regenerate_cover_letter(
    session_id: str,
    response: Response,
    current_user: Dict[str, Any] = Depends(get_current_user_with_complete_profile),
    db: AsyncSession = Depends(get_database),
) -> RegenerateCoverLetterResponse:
    """
    Regenerate the cover letter for a completed workflow session.

    Re-runs only the cover letter agent using the existing workflow state data.
    """
    try:
        user_id_raw = current_user.get("id") or current_user.get("_id")
        user_id = uuid.UUID(user_id_raw) if isinstance(user_id_raw, str) else user_id_raw

        # Rate limit: 5 regenerations per hour
        rate_result = await check_rate_limit_with_headers(
            identifier=f"{user_id}:regen_cover_letter",
            limit=5,
            window_seconds=3600,
        )
        response.headers["X-RateLimit-Limit"] = str(rate_result.limit)
        response.headers["X-RateLimit-Remaining"] = str(rate_result.remaining)
        response.headers["X-RateLimit-Reset"] = str(rate_result.reset_seconds)
        if not rate_result.allowed:
            raise rate_limit_error("Rate limit exceeded. Maximum 5 regenerations per hour.")

        # Load workflow session
        result = await db.execute(
            select(WorkflowSession).where(
                and_(
                    WorkflowSession.session_id == session_id,
                    WorkflowSession.user_id == user_id
                )
            )
        )
        workflow_session = result.scalar_one_or_none()

        if not workflow_session:
            raise not_found_error("Workflow session not found")

        if workflow_session.workflow_status not in [
            WorkflowStatus.COMPLETED.value,
            WorkflowStatus.AWAITING_CONFIRMATION.value,
            WorkflowStatus.ANALYSIS_COMPLETE.value,
        ]:
            raise validation_error("Can only regenerate cover letter for completed workflows")

        # Load user profile for the agent
        profile_result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        user_profile = profile_result.scalar_one_or_none()
        if not user_profile:
            raise validation_error("User profile not found")

        # Get user's API key if they have one (BYOK)
        user_result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user_record = user_result.scalar_one_or_none()
        user_api_key = None
        if user_record and user_record.gemini_api_key_encrypted:
            from utils.encryption import decrypt_api_key
            user_api_key = decrypt_api_key(user_record.gemini_api_key_encrypted)

        # Build minimal workflow state for the cover letter agent
        from agents.cover_letter_writer import CoverLetterWriterAgent
        from utils.llm_client import get_gemini_client

        gemini_client = await get_gemini_client()
        agent = CoverLetterWriterAgent(gemini_client)

        state = {
            "user_profile": user_profile.to_dict() if hasattr(user_profile, 'to_dict') else {},
            "job_analysis": workflow_session.job_analysis or {},
            "profile_matching": workflow_session.profile_matching,
            "company_research": workflow_session.company_research,
            "session_id": session_id,
            "user_api_key": user_api_key,
            "cover_letter": None,
            "error_messages": [],
            "warning_messages": [],
        }

        # Run the cover letter agent
        updated_state = await agent.process(state)
        new_cover_letter = updated_state.get("cover_letter", {})

        # Sanitize before persisting and returning to prevent XSS from LLM output
        new_cover_letter = sanitize_llm_output(new_cover_letter)

        from sqlalchemy.orm.attributes import flag_modified
        workflow_session.cover_letter = new_cover_letter
        flag_modified(workflow_session, "cover_letter")
        await db.commit()

        logger.info(f"Regenerated cover letter for session {sanitize_log_value(session_id)}")

        return RegenerateCoverLetterResponse(
            session_id=session_id,
            cover_letter=new_cover_letter,
            message="Cover letter regenerated successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to regenerate cover letter: {e}", exc_info=True)
        raise internal_error(
            _agent_error_message(e, "Failed to regenerate cover letter", debug=settings.debug)
        )


@router.post("/regenerate-resume/{session_id}", response_model=RegenerateAgentResponse)
async def regenerate_resume(
    session_id: str,
    response: Response,
    current_user: Dict[str, Any] = Depends(get_current_user_with_complete_profile),
    db: AsyncSession = Depends(get_database),
) -> RegenerateAgentResponse:
    """
    Regenerate resume recommendations for a completed workflow session.

    Re-runs only the resume advisor agent using the existing workflow state data.
    """
    try:
        user_id_raw = current_user.get("id") or current_user.get("_id")
        user_id = uuid.UUID(user_id_raw) if isinstance(user_id_raw, str) else user_id_raw

        rate_result = await check_rate_limit_with_headers(
            identifier=f"{user_id}:regen_resume",
            limit=5,
            window_seconds=3600,
        )
        response.headers["X-RateLimit-Limit"] = str(rate_result.limit)
        response.headers["X-RateLimit-Remaining"] = str(rate_result.remaining)
        response.headers["X-RateLimit-Reset"] = str(rate_result.reset_seconds)
        if not rate_result.allowed:
            raise rate_limit_error("Rate limit exceeded. Maximum 5 regenerations per hour.")

        result = await db.execute(
            select(WorkflowSession).where(
                and_(
                    WorkflowSession.session_id == session_id,
                    WorkflowSession.user_id == user_id
                )
            )
        )
        workflow_session = result.scalar_one_or_none()

        if not workflow_session:
            raise not_found_error("Workflow session not found")

        if workflow_session.workflow_status not in [
            WorkflowStatus.COMPLETED.value,
            WorkflowStatus.AWAITING_CONFIRMATION.value,
            WorkflowStatus.ANALYSIS_COMPLETE.value,
        ]:
            raise validation_error("Can only regenerate for completed workflows")

        profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
        user_profile = profile_result.scalar_one_or_none()
        if not user_profile:
            raise validation_error("User profile not found")

        user_result = await db.execute(select(User).where(User.id == user_id))
        user_record = user_result.scalar_one_or_none()
        user_api_key = None
        if user_record and user_record.gemini_api_key_encrypted:
            from utils.encryption import decrypt_api_key
            user_api_key = decrypt_api_key(user_record.gemini_api_key_encrypted)

        from agents.resume_advisor import ResumeAdvisorAgent
        from utils.llm_client import get_gemini_client

        gemini_client = await get_gemini_client()
        agent = ResumeAdvisorAgent(gemini_client)

        state = {
            "user_profile": user_profile.to_dict() if hasattr(user_profile, 'to_dict') else {},
            "job_analysis": workflow_session.job_analysis or {},
            "profile_matching": workflow_session.profile_matching,
            "company_research": workflow_session.company_research,
            "session_id": session_id,
            "user_api_key": user_api_key,
            "resume_recommendations": None,
            "error_messages": [],
            "warning_messages": [],
        }

        updated_state = await agent.process(state)
        new_resume = updated_state.get("resume_recommendations", {})

        # Sanitize before persisting and returning to prevent XSS from LLM output
        new_resume = sanitize_llm_output(new_resume)
        _raise_if_agent_soft_failure(new_resume)

        from sqlalchemy.orm.attributes import flag_modified
        workflow_session.resume_recommendations = new_resume
        flag_modified(workflow_session, "resume_recommendations")
        await db.commit()

        logger.info(f"Regenerated resume recommendations for session {sanitize_log_value(session_id)}")

        return RegenerateAgentResponse(
            session_id=session_id,
            result=new_resume,
            message="Resume recommendations regenerated successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to regenerate resume: {e}", exc_info=True)
        raise internal_error(
            _agent_error_message(
                e, "Failed to regenerate resume recommendations", debug=settings.debug
            )
        )


@router.post("/generate-interview-prep/{session_id}", response_model=RegenerateAgentResponse)
async def generate_interview_prep(
    session_id: str,
    response: Response,
    current_user: Dict[str, Any] = Depends(get_current_user_with_complete_profile),
    db: AsyncSession = Depends(get_database),
) -> RegenerateAgentResponse:
    """
    Generate or regenerate detailed interview preparation materials.

    Uses job analysis, company research, and profile matching to create
    comprehensive, personalized interview prep.
    """
    try:
        user_id_raw = current_user.get("id") or current_user.get("_id")
        user_id = uuid.UUID(user_id_raw) if isinstance(user_id_raw, str) else user_id_raw

        rate_result = await check_rate_limit_with_headers(
            identifier=f"{user_id}:gen_interview_prep",
            limit=5,
            window_seconds=3600,
        )
        response.headers["X-RateLimit-Limit"] = str(rate_result.limit)
        response.headers["X-RateLimit-Remaining"] = str(rate_result.remaining)
        response.headers["X-RateLimit-Reset"] = str(rate_result.reset_seconds)
        if not rate_result.allowed:
            raise rate_limit_error("Rate limit exceeded. Maximum 5 generations per hour.")

        result = await db.execute(
            select(WorkflowSession).where(
                and_(
                    WorkflowSession.session_id == session_id,
                    WorkflowSession.user_id == user_id
                )
            )
        )
        workflow_session = result.scalar_one_or_none()

        if not workflow_session:
            raise not_found_error("Workflow session not found")

        if workflow_session.workflow_status not in [
            WorkflowStatus.COMPLETED.value,
            WorkflowStatus.AWAITING_CONFIRMATION.value,
            WorkflowStatus.ANALYSIS_COMPLETE.value,
        ]:
            raise validation_error("Can only generate for completed workflows")

        # Get user profile for personalization
        profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
        user_profile = profile_result.scalar_one_or_none()

        # Get user's API key if available
        user_result = await db.execute(select(User).where(User.id == user_id))
        user_record = user_result.scalar_one_or_none()
        user_api_key = None
        if user_record and user_record.gemini_api_key_encrypted:
            from utils.encryption import decrypt_api_key
            user_api_key = decrypt_api_key(user_record.gemini_api_key_encrypted)

        from utils.llm_client import get_gemini_client
        import json

        gemini_client = await get_gemini_client()

        job = workflow_session.job_analysis or {}
        company = workflow_session.company_research or {}
        matching = workflow_session.profile_matching or {}
        profile_dict = user_profile.to_dict() if user_profile and hasattr(user_profile, 'to_dict') else {}

        prompt = f"""You are an expert career coach. Generate comprehensive, personalized interview preparation materials for this candidate.

## Job Information
- Title: {job.get('job_title', 'Unknown')}
- Company: {job.get('company_name', 'Unknown')}
- Requirements: {json.dumps(job.get('requirements', [])[:10], default=str)}
- Responsibilities: {json.dumps(job.get('responsibilities', [])[:10], default=str)}
- Skills needed: {json.dumps(job.get('required_skills', [])[:15], default=str)}

## Company Context
- Industry: {company.get('industry', 'Unknown')}
- Size: {company.get('company_size', 'Unknown')}
- Culture values: {json.dumps(company.get('company_values', []), default=str)}
- What they look for: {json.dumps(company.get('what_they_look_for', []), default=str)}
- Hiring timeline: {company.get('hiring_timeline', 'Unknown')}

## Candidate Profile
- Title: {profile_dict.get('professional_title', 'Unknown')}
- Experience: {profile_dict.get('years_experience', 'Unknown')} years
- Key skills: {json.dumps(profile_dict.get('skills', [])[:10], default=str)}
- Match score: {matching.get('overall_match_score', matching.get('overall_score', 'Unknown'))}%
- Strengths: {json.dumps(matching.get('key_strengths', [])[:5], default=str)}
- Gaps: {json.dumps(matching.get('gaps_to_address', matching.get('areas_for_improvement', []))[:5], default=str)}

Return a JSON object with:
{{
  "interview_format": "Expected format (e.g., 4 rounds over 2-3 weeks)",
  "hiring_timeline": "Expected timeline",
  "interview_stages": [
    {{
      "stage": "Stage name (e.g., Recruiter Screen)",
      "description": "What to expect",
      "duration": "30-45 min",
      "tips": "How to prepare for this stage"
    }}
  ],
  "likely_questions": [
    {{
      "question": "The interview question",
      "category": "behavioral|technical|situational|company-specific",
      "why_they_ask": "Why this matters for the role",
      "suggested_approach": "How to structure your answer using your experience"
    }}
  ],
  "technical_topics": ["Topic to review 1", "Topic to review 2"],
  "what_they_evaluate": ["Evaluation criteria 1", "Evaluation criteria 2"],
  "your_strengths_to_highlight": ["Strength 1 with specific example to use", "Strength 2"],
  "gaps_to_address": [
    {{
      "gap": "The gap or concern",
      "strategy": "How to address it positively in the interview"
    }}
  ],
  "questions_to_ask": [
    {{
      "question": "Question to ask the interviewer",
      "why": "Why this is a good question to ask",
      "when": "Which stage to ask this in"
    }}
  ],
  "preparation_checklist": ["Action item 1", "Action item 2"],
  "day_of_tips": ["Tip for interview day 1", "Tip 2"]
}}

Generate 4-6 interview stages, 8-10 likely questions with personalized suggested approaches, 5-8 technical topics, and 5-6 questions to ask. Make everything specific to this role, company, and candidate's background."""

        response = await asyncio.wait_for(
            gemini_client.generate(
                prompt=prompt,
                system="You are an expert interview coach. Return only valid JSON.",
                temperature=0.7,
                max_tokens=16000,
                user_api_key=user_api_key,
            ),
            timeout=180.0,
        )

        from utils.llm_parsing import parse_json_from_llm_response
        interview_prep = parse_json_from_llm_response(response.get("response", ""))

        if not interview_prep:
            interview_prep = {"raw_response": response.get("response", ""), "parse_error": True}

        # Sanitize before persisting and returning to prevent XSS from LLM output
        interview_prep = sanitize_llm_output(interview_prep)

        from sqlalchemy.orm.attributes import flag_modified
        if workflow_session.company_research is None:
            workflow_session.company_research = {}
        workflow_session.company_research["interview_preparation"] = interview_prep
        flag_modified(workflow_session, "company_research")
        await db.commit()

        logger.info(f"Generated interview prep for session {sanitize_log_value(session_id)}")

        return RegenerateAgentResponse(
            session_id=session_id,
            result=interview_prep,
            message="Interview preparation generated successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate interview prep: {e}", exc_info=True)
        raise internal_error(
            _agent_error_message(e, "Failed to generate interview preparation", debug=settings.debug)
        )


@router.post("/continue/{session_id}", response_model=WorkflowContinueResponse)
async def continue_workflow_after_gate(
    session_id: str,
    background_tasks: BackgroundTasks,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> WorkflowContinueResponse:
    """
    Continue workflow after user confirms to proceed despite low match score.

    This endpoint is called when the gate decision stops the workflow due to
    low profile matching score, and the user chooses to continue anyway.
    """
    try:
        user_id = get_user_uuid(current_user)

        # Rate limit: 20 continue attempts per hour per user
        is_allowed, _remaining = await check_rate_limit(
            identifier=f"{user_id}:workflow_continue",
            limit=20,
            window_seconds=3600,
        )
        if not is_allowed:
            raise rate_limit_error("Too many workflow continuation attempts. Please try again later.", retry_after=3600)

        # Query for workflow session
        result = await db.execute(
            select(WorkflowSession).where(
                and_(
                    WorkflowSession.session_id == session_id,
                    WorkflowSession.user_id == user_id
                )
            )
        )
        workflow_session = result.scalar_one_or_none()

        if not workflow_session:
            raise not_found_error("Workflow session not found")

        # Verify workflow is in awaiting_confirmation state
        if workflow_session.workflow_status != WorkflowStatus.AWAITING_CONFIRMATION.value:
            raise validation_error(f"Workflow is not awaiting confirmation. Current status: {workflow_session.workflow_status}")

        # Update ONLY the status using direct SQL to avoid overwriting other fields
        # This prevents race conditions where the ORM object might have stale data
        from sqlalchemy import update
        await db.execute(
            update(WorkflowSession)
            .where(WorkflowSession.session_id == session_id)
            .values(workflow_status=WorkflowStatus.IN_PROGRESS.value)
        )
        await db.commit()

        # Dispatch continuation — prefer Cloud Tasks when configured.
        settings = get_settings()
        if settings.use_cloud_tasks:
            try:
                await enqueue_continue_workflow_task(
                    session_id=session_id,
                    user_id=str(user_id),
                )
            except Exception as ct_err:
                logger.warning(
                    f"Cloud Tasks enqueue failed for continuation, falling back: {ct_err}"
                )
                background_tasks.add_task(
                    _continue_workflow_background,
                    session_id=session_id,
                    user_id=str(user_id),
                )
        else:
            background_tasks.add_task(
                _continue_workflow_background,
                session_id=session_id,
                user_id=str(user_id),
            )

        logger.info(f"Continuing workflow {sanitize_log_value(session_id)} after user confirmation")

        return WorkflowContinueResponse(
            session_id=session_id,
            status=WorkflowStatus.IN_PROGRESS.value,
            message="Workflow resumed. Processing remaining agents.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to continue workflow: {e}", exc_info=True)
        raise internal_error("Failed to continue workflow")


@router.post("/generate-documents/{session_id}", response_model=WorkflowContinueResponse)
async def generate_documents(
    session_id: str,
    background_tasks: BackgroundTasks,
    response: Response,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> WorkflowContinueResponse:
    """
    Trigger document generation (resume advice + cover letter) for a session
    that stopped at ANALYSIS_COMPLETE.

    This endpoint is the on-demand counterpart to the auto_generate_documents
    preference.  Call it when the user decides they want documents after reviewing
    the analysis results.
    """
    try:
        user_id = get_user_uuid(current_user)

        rate_result = await check_rate_limit_with_headers(
            identifier=f"{user_id}:gen_documents",
            limit=5,
            window_seconds=3600,
        )
        response.headers["X-RateLimit-Limit"] = str(rate_result.limit)
        response.headers["X-RateLimit-Remaining"] = str(rate_result.remaining)
        response.headers["X-RateLimit-Reset"] = str(rate_result.reset_seconds)
        if not rate_result.allowed:
            raise rate_limit_error("Rate limit exceeded. Maximum 5 document generations per hour.")

        result = await db.execute(
            select(WorkflowSession).where(
                and_(
                    WorkflowSession.session_id == session_id,
                    WorkflowSession.user_id == user_id,
                )
            )
        )
        workflow_session = result.scalar_one_or_none()

        if not workflow_session:
            raise not_found_error("Workflow session not found")

        if workflow_session.workflow_status != "analysis_complete":
            raise validation_error(
                f"Documents can only be generated from 'analysis_complete' status. "
                f"Current status: {workflow_session.workflow_status}"
            )

        # Mark as in_progress so the UI shows a spinner
        await db.execute(
            update(WorkflowSession)
            .where(WorkflowSession.session_id == session_id)
            .values(workflow_status=WorkflowStatus.IN_PROGRESS.value)
        )
        await db.commit()

        background_tasks.add_task(
            _generate_documents_background,
            session_id=session_id,
            user_id=str(user_id),
        )

        logger.info(f"Document generation started for session {sanitize_log_value(session_id)}")

        return WorkflowContinueResponse(
            session_id=session_id,
            status=WorkflowStatus.IN_PROGRESS.value,
            message="Document generation started.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start document generation: {e}", exc_info=True)
        raise internal_error("Failed to start document generation")


# =============================================================================
# BACKGROUND TASKS
# =============================================================================


async def _execute_workflow_background(
    session_id: str,
    user_id: str,
    input_method: str,
    job_input: str,
    user_data: Dict[str, Any],
    user_api_key: Optional[str] = None,
) -> None:
    """Execute workflow in background."""
    try:
        async with get_session() as db:
            # Get workflow session
            result = await db.execute(
                select(WorkflowSession).where(WorkflowSession.session_id == session_id)
            )
            workflow_session = result.scalar_one_or_none()

            if not workflow_session:
                logger.error(f"Workflow session {sanitize_log_value(session_id)} not found")
                return

            # Idempotency guard: if a Cloud Tasks retry fires after the workflow
            # already completed or started, skip the re-execution to prevent
            # data corruption.
            _idempotent_statuses = {
                WorkflowStatus.IN_PROGRESS.value,
                WorkflowStatus.COMPLETED.value,
                WorkflowStatus.AWAITING_CONFIRMATION.value,
                WorkflowStatus.ANALYSIS_COMPLETE.value,
            }
            if workflow_session.workflow_status in _idempotent_statuses:
                logger.warning(
                    f"Workflow {session_id} already in status "
                    f"'{workflow_session.workflow_status}' — skipping retry execution"
                )
                return

            # Update status to running
            workflow_session.workflow_status = WorkflowStatus.IN_PROGRESS.value
            await db.commit()

            # Initialize and run workflow
            workflow = JobApplicationWorkflow(db)

            try:
                final_state = await workflow.run_initial_workflow(
                    session_id=session_id,
                    user_id=user_id,
                    input_method=input_method,
                    job_input=job_input,
                    user_data=user_data,
                    user_api_key=user_api_key,
                )

                # Update workflow session with results
                try:
                    await _update_workflow_session_with_state(db, session_id, final_state)
                except Exception as session_err:
                    logger.error(f"Workflow {sanitize_log_value(session_id)}: Failed to update workflow session: {session_err}")
                    # Continue to update job application even if session update fails
                    # (workflow's _save_workflow_state already saved the data)
                    try:
                        await db.rollback()
                    except Exception as rb_err:
                        logger.debug("Rollback failed (connection already closed or rolled back): %s", rb_err)

                # Update job application (independent of workflow session update)
                duplicate_constraint_reverted = False
                try:
                    duplicate_constraint_reverted = await _update_job_application_with_final_state(
                        db, session_id, final_state
                    )
                except Exception as app_err:
                    logger.error(f"Workflow {sanitize_log_value(session_id)}: Failed to update job application: {app_err}", exc_info=True)
                    try:
                        await db.rollback()
                    except Exception as rb_err:
                        logger.debug("Rollback failed (connection already closed or rolled back): %s", rb_err)

                if duplicate_constraint_reverted:
                    logger.warning(
                        f"Workflow {session_id}: duplicate job (uq_user_job_company) — "
                        "session reverted and application hidden"
                    )
                else:
                    logger.info(f"Workflow {sanitize_log_value(session_id)} completed successfully")
                # Clear stale in-progress cache so the next poll sees the terminal state immediately
                await invalidate_workflow_state(session_id)

            except Exception as e:
                logger.error(f"Workflow {sanitize_log_value(session_id)} failed: {e}", exc_info=True)
                try:
                    await db.rollback()
                except Exception as rb_err:
                    logger.debug("Rollback failed (connection already closed or rolled back): %s", rb_err)

                try:
                    from sqlalchemy.orm.attributes import flag_modified
                    workflow_session.workflow_status = WorkflowStatus.FAILED.value
                    workflow_session.error_messages = (workflow_session.error_messages or []) + [_safe_error_msg(e, settings.debug)]
                    workflow_session.processing_end_time = datetime.now(timezone.utc)
                    flag_modified(workflow_session, "error_messages")
                    _strip_agent_outputs_on_session_model(workflow_session)
                    await db.commit()
                except Exception as rollback_err:
                    logger.error(f"Workflow {sanitize_log_value(session_id)}: Failed to save error state: {rollback_err}")
                # Clear stale cache on failure too
                await invalidate_workflow_state(session_id)

                # Hide failed analysis from the applications list (soft-delete)
                try:
                    await _soft_delete_job_application_for_failed_workflow(db, session_id)
                    await db.commit()
                except Exception as app_err:
                    logger.error(
                        f"Workflow {session_id}: Failed to soft-delete application: {app_err}",
                        exc_info=True,
                    )

    except Exception as e:
        logger.error(f"Background workflow execution failed: {e}", exc_info=True)
        await report_exception(e, user_id=user_id)
        # Ensure session is marked FAILED even if the inner DB session was lost
        try:
            async with get_session() as _db:
                await _db.execute(
                    update(WorkflowSession)
                    .where(
                        WorkflowSession.session_id == session_id,
                        WorkflowSession.workflow_status == WorkflowStatus.IN_PROGRESS.value,
                    )
                    .values(
                        workflow_status=WorkflowStatus.FAILED.value,
                        processing_end_time=datetime.now(timezone.utc),
                        job_analysis=None,
                        company_research=None,
                        profile_matching=None,
                        resume_recommendations=None,
                        cover_letter=None,
                    )
                )
                await _soft_delete_job_application_for_failed_workflow(_db, session_id)
                await _db.commit()
        except Exception as _update_err:
            logger.error(
                f"Workflow {session_id}: failed to set FAILED status after top-level error: {_update_err}",
                exc_info=True,
            )


async def _continue_workflow_background(session_id: str, user_id: Optional[str] = None) -> None:
    """Continue workflow execution after user confirmation."""
    try:
        async with get_session() as db:
            # Get workflow session
            result = await db.execute(
                select(WorkflowSession).where(WorkflowSession.session_id == session_id)
            )
            workflow_session = result.scalar_one_or_none()

            if not workflow_session:
                logger.error(f"Workflow session {sanitize_log_value(session_id)} not found for continuation")
                return

            # Idempotency guard: only continue from AWAITING_CONFIRMATION or IN_PROGRESS.
            # Cloud Tasks may retry; skip if the session already completed.
            _continuation_idempotent_statuses = {
                WorkflowStatus.COMPLETED.value,
                WorkflowStatus.ANALYSIS_COMPLETE.value,
                WorkflowStatus.FAILED.value,
            }
            if workflow_session.workflow_status in _continuation_idempotent_statuses:
                logger.warning(
                    f"Workflow {session_id} already in status "
                    f"'{workflow_session.workflow_status}' — skipping retry continuation"
                )
                return

            ws_user_id = user_id or str(workflow_session.user_id)

            # Notify clients that the workflow is resuming
            await broadcast_workflow_resumed(ws_user_id, session_id)

            # Get user's API key if available (BYOK mode)
            user_api_key = None
            if user_id:
                user_result = await db.execute(
                    select(User).where(User.id == uuid.UUID(user_id))
                )
                user = user_result.scalar_one_or_none()
                
                if user and user.gemini_api_key_encrypted:
                    try:
                        user_api_key = decrypt_api_key(user.gemini_api_key_encrypted)
                    except Exception as e:
                        logger.warning(f"Failed to decrypt user API key for continuation: {e}")

            # Initialize workflow
            workflow = JobApplicationWorkflow(db)

            try:
                # Build and run continuation workflow
                final_state = await workflow.continue_workflow_after_gate(
                    session_id=session_id,
                    user_api_key=user_api_key,
                )

                # Update workflow session with results
                try:
                    await _update_workflow_session_with_state(db, session_id, final_state)
                except Exception as session_err:
                    logger.error(f"Workflow {sanitize_log_value(session_id)} continuation: Failed to update session: {session_err}")
                    try:
                        await db.rollback()
                    except Exception as rb_err:
                        logger.debug("Rollback failed (connection already closed or rolled back): %s", rb_err)

                # Update job application (independent of workflow session update)
                duplicate_constraint_reverted = False
                try:
                    duplicate_constraint_reverted = await _update_job_application_with_final_state(
                        db, session_id, final_state
                    )
                except Exception as app_err:
                    logger.error(f"Workflow {sanitize_log_value(session_id)} continuation: Failed to update application: {app_err}")
                    try:
                        await db.rollback()
                    except Exception as rb_err:
                        logger.debug("Rollback failed (connection already closed or rolled back): %s", rb_err)

                if duplicate_constraint_reverted:
                    logger.warning(
                        f"Workflow {session_id} continuation: duplicate job (uq_user_job_company) — "
                        "session reverted and application hidden"
                    )
                else:
                    logger.info(f"Workflow {sanitize_log_value(session_id)} continuation completed successfully")
                await invalidate_workflow_state(session_id)

            except Exception as e:
                logger.error(f"Workflow {sanitize_log_value(session_id)} continuation failed: {e}", exc_info=True)
                try:
                    await db.rollback()
                except Exception as rb_err:
                    logger.debug("Rollback failed (connection already closed or rolled back): %s", rb_err)
                try:
                    from sqlalchemy.orm.attributes import flag_modified
                    workflow_session.workflow_status = WorkflowStatus.FAILED.value
                    workflow_session.error_messages = (workflow_session.error_messages or []) + [_safe_error_msg(e, settings.debug)]
                    workflow_session.processing_end_time = datetime.now(timezone.utc)
                    flag_modified(workflow_session, "error_messages")
                    _strip_agent_outputs_on_session_model(workflow_session)
                    await _soft_delete_job_application_for_failed_workflow(db, session_id)
                    await db.commit()
                except Exception as rollback_err:
                    logger.error(f"Workflow {sanitize_log_value(session_id)}: Failed to save continuation error state: {rollback_err}")
                await invalidate_workflow_state(session_id)

    except Exception as e:
        logger.error(f"Background workflow continuation failed: {e}", exc_info=True)
        await report_exception(e, user_id=user_id)
        try:
            async with get_session() as _db:
                await _db.execute(
                    update(WorkflowSession)
                    .where(
                        WorkflowSession.session_id == session_id,
                        WorkflowSession.workflow_status == WorkflowStatus.IN_PROGRESS.value,
                    )
                    .values(
                        workflow_status=WorkflowStatus.FAILED.value,
                        processing_end_time=datetime.now(timezone.utc),
                        job_analysis=None,
                        company_research=None,
                        profile_matching=None,
                        resume_recommendations=None,
                        cover_letter=None,
                    )
                )
                await _soft_delete_job_application_for_failed_workflow(_db, session_id)
                await _db.commit()
        except Exception as _update_err:
            logger.error(
                f"Workflow {session_id}: failed to set FAILED status after top-level continuation error: {_update_err}",
                exc_info=True,
            )


async def _generate_documents_background(
    session_id: str, user_id: Optional[str] = None
) -> None:
    """Run resume advisor + cover letter writer for an ANALYSIS_COMPLETE session."""
    try:
        async with get_session() as db:
            result = await db.execute(
                select(WorkflowSession).where(WorkflowSession.session_id == session_id)
            )
            workflow_session = result.scalar_one_or_none()

            if not workflow_session:
                logger.error(f"Session {sanitize_log_value(session_id)} not found for document generation")
                return

            # Idempotency guard: skip if documents were already generated or if
            # the session failed.  Cloud Tasks retries should not overwrite results.
            _doc_gen_idempotent_statuses = {
                WorkflowStatus.COMPLETED.value,
                WorkflowStatus.FAILED.value,
            }
            if workflow_session.workflow_status in _doc_gen_idempotent_statuses:
                logger.warning(
                    f"Document generation for {session_id} already terminal "
                    f"(status: {workflow_session.workflow_status}) — skipping retry"
                )
                return

            ws_user_id = user_id or str(workflow_session.user_id)

            # Notify clients that document generation is starting
            await broadcast_document_generation_started(ws_user_id, session_id)

            user_api_key = None
            if user_id:
                user_result = await db.execute(
                    select(User).where(User.id == uuid.UUID(user_id))
                )
                user = user_result.scalar_one_or_none()
                if user and user.gemini_api_key_encrypted:
                    try:
                        user_api_key = decrypt_api_key(user.gemini_api_key_encrypted)
                    except Exception as e:
                        logger.warning(f"Failed to decrypt API key for document generation: {e}")

            workflow = JobApplicationWorkflow(db)

            try:
                final_state = await workflow.run_document_generation(
                    session_id=session_id,
                    user_api_key=user_api_key,
                )

                try:
                    await _update_workflow_session_with_state(db, session_id, final_state)
                except Exception as session_err:
                    logger.error(f"Session {sanitize_log_value(session_id)}: failed to persist document results: {session_err}")
                    try:
                        await db.rollback()
                    except Exception as rb_err:
                        logger.debug("Rollback failed (connection already closed or rolled back): %s", rb_err)

                duplicate_constraint_reverted = False
                try:
                    duplicate_constraint_reverted = await _update_job_application_with_final_state(
                        db, session_id, final_state
                    )
                except Exception as app_err:
                    logger.error(f"Session {sanitize_log_value(session_id)}: failed to update application after documents: {app_err}")
                    try:
                        await db.rollback()
                    except Exception as rb_err:
                        logger.debug("Rollback failed (connection already closed or rolled back): %s", rb_err)

                if duplicate_constraint_reverted:
                    logger.warning(
                        f"Session {session_id}: duplicate job after documents (uq_user_job_company) — "
                        "session reverted and application hidden"
                    )
                else:
                    logger.info(f"Document generation completed for session {sanitize_log_value(session_id)}")

            except Exception as e:
                logger.error(f"Document generation failed for session {sanitize_log_value(session_id)}: {e}", exc_info=True)
                try:
                    await db.rollback()
                except Exception as rb_err:
                    logger.debug("Rollback failed (connection already closed or rolled back): %s", rb_err)
                try:
                    from sqlalchemy.orm.attributes import flag_modified
                    workflow_session.workflow_status = WorkflowStatus.FAILED.value
                    workflow_session.error_messages = (workflow_session.error_messages or []) + [_safe_error_msg(e, settings.debug)]
                    workflow_session.processing_end_time = datetime.now(timezone.utc)
                    flag_modified(workflow_session, "error_messages")
                    _strip_agent_outputs_on_session_model(workflow_session)
                    await _soft_delete_job_application_for_failed_workflow(db, session_id)
                    await db.commit()
                except Exception as rollback_err:
                    logger.error(f"Session {sanitize_log_value(session_id)}: failed to persist error state: {rollback_err}")

    except Exception as e:
        logger.error(f"Background document generation task failed: {e}", exc_info=True)
        await report_exception(e, user_id=user_id)
        try:
            async with get_session() as _db:
                await _db.execute(
                    update(WorkflowSession)
                    .where(WorkflowSession.session_id == session_id)
                    .values(
                        workflow_status=WorkflowStatus.FAILED.value,
                        processing_end_time=datetime.now(timezone.utc),
                        job_analysis=None,
                        company_research=None,
                        profile_matching=None,
                        resume_recommendations=None,
                        cover_letter=None,
                    )
                )
                await _soft_delete_job_application_for_failed_workflow(_db, session_id)
                await _db.commit()
        except Exception as _update_err:
            logger.error(
                f"Session {session_id}: failed to set FAILED status after top-level doc gen error: {_update_err}",
                exc_info=True,
            )


async def _update_workflow_session_with_state(
    db: AsyncSession,
    session_id: str,
    final_state: Dict[str, Any],
) -> None:
    """Update workflow session with final state."""
    result = await db.execute(
        select(WorkflowSession).where(WorkflowSession.session_id == session_id)
    )
    workflow_session = result.scalar_one_or_none()

    if not workflow_session:
        return

    from sqlalchemy.orm.attributes import flag_modified

    # Update fields from state
    workflow_session.workflow_status = final_state.get("workflow_status", WorkflowStatus.COMPLETED.value)
    workflow_session.current_phase = final_state.get("current_phase", WorkflowPhase.COMPLETED.value)
    workflow_session.current_agent = final_state.get("current_agent")
    workflow_session.agent_status = final_state.get("agent_status", {})
    workflow_session.completed_agents = final_state.get("completed_agents", [])
    workflow_session.failed_agents = final_state.get("failed_agents", [])
    workflow_session.error_messages = final_state.get("error_messages", [])
    workflow_session.warning_messages = final_state.get("warning_messages", [])
    workflow_session.processing_end_time = datetime.now(timezone.utc)

    flag_modified(workflow_session, "agent_status")
    flag_modified(workflow_session, "completed_agents")
    flag_modified(workflow_session, "failed_agents")
    flag_modified(workflow_session, "error_messages")
    flag_modified(workflow_session, "warning_messages")

    # Failed workflows must not retain partial agent outputs in the session row.
    if _normalize_workflow_status_string(final_state.get("workflow_status")) == WorkflowStatus.FAILED.value:
        for _col in (
            "job_analysis",
            "company_research",
            "profile_matching",
            "resume_recommendations",
            "cover_letter",
        ):
            setattr(workflow_session, _col, None)
            flag_modified(workflow_session, _col)
    else:
        if final_state.get("job_analysis"):
            workflow_session.job_analysis = final_state["job_analysis"]
            flag_modified(workflow_session, "job_analysis")
        if final_state.get("company_research"):
            workflow_session.company_research = final_state["company_research"]
            flag_modified(workflow_session, "company_research")
        if final_state.get("profile_matching"):
            workflow_session.profile_matching = final_state["profile_matching"]
            flag_modified(workflow_session, "profile_matching")
        if final_state.get("resume_recommendations"):
            workflow_session.resume_recommendations = final_state["resume_recommendations"]
            flag_modified(workflow_session, "resume_recommendations")
        if final_state.get("cover_letter"):
            workflow_session.cover_letter = final_state["cover_letter"]
            flag_modified(workflow_session, "cover_letter")

    await db.commit()


def _normalize_workflow_status_string(raw: Any) -> str:
    """Coerce workflow_status from final_state (enum or str) to a lowercase string."""
    if raw is None:
        return str(WorkflowStatus.COMPLETED.value)
    if hasattr(raw, "value"):
        return str(raw.value).strip().lower()
    return str(raw).strip().lower()


async def _update_job_application_with_final_state(
    db: AsyncSession,
    session_id: str,
    final_state: Dict[str, Any],
) -> bool:
    """
    Update job application based on final workflow state.

    Returns:
        True if the run hit ``uq_user_job_company`` after the workflow had already
        completed in the session row — the session was reverted to failed and the
        application soft-deleted (duplicate job). Caller should not log success.
    """
    logger.info(f"Updating job application for session {sanitize_log_value(session_id)}")

    # Get job analysis for title and company.
    # Use `or {}` instead of a default — when a workflow fails, job_analysis is
    # explicitly None in the state dict, so get(..., {}) still returns None.
    job_analysis = final_state.get("job_analysis") or {}
    job_title = job_analysis.get("job_title")
    company_name = job_analysis.get("company_name")

    ws_raw = final_state.get("workflow_status")
    workflow_status_norm = _normalize_workflow_status_string(ws_raw)

    logger.info(
        f"Job application update: title={job_title}, company={company_name}, "
        f"workflow_status={ws_raw!r} (normalized={workflow_status_norm!r})"
    )

    # Determine application status
    failed_workflow = False

    if workflow_status_norm == WorkflowStatus.COMPLETED.value:
        app_status = ApplicationStatus.COMPLETED.value
    elif workflow_status_norm == WorkflowStatus.ANALYSIS_COMPLETE.value:
        app_status = ApplicationStatus.COMPLETED.value
    elif workflow_status_norm == WorkflowStatus.AWAITING_CONFIRMATION.value:
        app_status = ApplicationStatus.COMPLETED.value
    elif workflow_status_norm == WorkflowStatus.FAILED.value:
        app_status = ApplicationStatus.FAILED.value
        failed_workflow = True
    else:
        app_status = ApplicationStatus.PROCESSING.value

    # Extract match score from profile matching results
    profile_matching = final_state.get("profile_matching", {})
    match_score = None
    if profile_matching:
        # Try multiple possible keys (LLM output format varies)
        final_scores = profile_matching.get("final_scores", {})
        if final_scores:
            match_score = (
                final_scores.get("overall_match_score")
                or final_scores.get("overall_fit_score")
                or final_scores.get("overall_fit")
                or final_scores.get("weighted_recommendation_score")
            )
        # Fallback to top-level keys
        if match_score is None:
            match_score = (
                profile_matching.get("overall_score")
                or profile_matching.get("overall_fit_score")
                or profile_matching.get("overall_match_score")
            )

    # Update application.
    # Try the full update (status + title + company + match_score) inside a savepoint.
    # If ``uq_user_job_company`` fires on a completed workflow, we revert the session row
    # and soft-delete this application (see IntegrityError branch) — we do not drop
    # title/company and leave a second visible card.
    now_ts = datetime.now(timezone.utc)
    full_values: Dict[str, Any] = {
        "status": app_status,
        "updated_at": now_ts,
    }
    if failed_workflow:
        full_values["deleted_at"] = now_ts
    if job_title:
        full_values["job_title"] = job_title
    if company_name:
        full_values["company_name"] = company_name
    if match_score is not None:
        full_values["match_score"] = match_score

    attempted_title_company = bool(job_title or company_name)

    try:
        async with db.begin_nested():
            await db.execute(
                update(JobApplication)
                .where(JobApplication.session_id == session_id)
                .values(**full_values)
            )
    except IntegrityError:
        # Unique on (user_id, job_title, company_name) for active rows — do not strip
        # title/company and "complete" anyway; that leaves two cards with the same
        # display names (list API falls back to job_analysis). Revert session + hide row.
        if attempted_title_company and not failed_workflow:
            logger.warning(
                f"Workflow {session_id}: duplicate constraint on job_applications "
                "(uq_user_job_company) — reverting completed session and soft-deleting row"
            )
            ws_user_id = await _revert_workflow_session_after_duplicate_job_constraint(
                db, session_id
            )
            await _soft_delete_job_application_for_failed_workflow(db, session_id)
            await db.commit()
            if ws_user_id:
                try:
                    await broadcast_workflow_error(
                        user_id=ws_user_id,
                        session_id=session_id,
                        error_message=_DUPLICATE_JOB_CONSTRAINT_MESSAGE,
                        failed_agent=None,
                    )
                except Exception as broadcast_err:
                    logger.debug(
                        "broadcast_workflow_error after duplicate constraint: %s",
                        broadcast_err,
                        exc_info=True,
                    )
            return True

        # Failed workflow path: still persist status/deleted_at without title churn.
        logger.warning(
            f"Workflow {session_id}: duplicate constraint on job_applications — "
            "retrying without title/company"
        )
        minimal_values: Dict[str, Any] = {
            "status": app_status,
            "updated_at": now_ts,
        }
        if failed_workflow:
            minimal_values["deleted_at"] = now_ts
        if match_score is not None:
            minimal_values["match_score"] = match_score
        await db.execute(
            update(JobApplication)
            .where(JobApplication.session_id == session_id)
            .values(**minimal_values)
        )

    await db.commit()
    return False


# =============================================================================
# WORKFLOW HISTORY / LIST
# =============================================================================


class WorkflowHistoryItem(BaseModel):
    """Summary item for the workflow history list."""

    session_id: str
    workflow_status: str
    current_phase: Optional[str] = None
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class WorkflowHistoryResponse(BaseModel):
    """Paginated list of workflow sessions."""

    sessions: List[WorkflowHistoryItem]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


@router.get("/history", response_model=WorkflowHistoryResponse)
async def list_workflow_history(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
    page: int = Query(default=1, ge=1, le=10000, description="Page number (1-indexed)"),
    per_page: int = Query(default=10, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(default=None, description="Filter by workflow_status"),
    sort: Optional[str] = Query(
        default="created_desc",
        description="Sort order: created_desc | created_asc | updated_desc",
    ),
) -> WorkflowHistoryResponse:
    """
    List the calling user's workflow sessions with pagination.

    Args:
        page: Page number (1-indexed)
        per_page: Results per page (max 100)
        status_filter: Optional workflow status filter
        sort: Sort order (created_desc, created_asc, updated_desc)

    Returns:
        Paginated WorkflowHistoryResponse
    """
    try:
        user_id = get_user_uuid(current_user)

        base_where = [WorkflowSession.user_id == user_id]
        if status_filter:
            base_where.append(WorkflowSession.workflow_status == status_filter)

        from sqlalchemy import and_ as sql_and

        count_result = await db.execute(
            select(func.count()).where(sql_and(*base_where))
        )
        total: int = count_result.scalar() or 0

        sort_map = {
            "created_asc":  WorkflowSession.created_at.asc(),
            "updated_desc": WorkflowSession.updated_at.desc(),
        }
        order_clause = sort_map.get(sort or "", WorkflowSession.created_at.desc())

        result = await db.execute(
            select(WorkflowSession)
            .where(sql_and(*base_where))
            .order_by(order_clause)
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        sessions = result.scalars().all()

        items = []
        for ws in sessions:
            job_title = None
            company_name = None
            if ws.job_analysis:
                job_title = ws.job_analysis.get("job_title")
                company_name = ws.job_analysis.get("company_name")
            items.append(
                WorkflowHistoryItem(
                    session_id=ws.session_id,
                    workflow_status=ws.workflow_status,
                    current_phase=ws.current_phase,
                    job_title=job_title,
                    company_name=company_name,
                    created_at=ws.created_at.isoformat() if ws.created_at else None,
                    updated_at=ws.updated_at.isoformat() if ws.updated_at else None,
                )
            )

        return WorkflowHistoryResponse(
            sessions=items,
            total=total,
            page=page,
            per_page=per_page,
            has_next=(page - 1) * per_page + per_page < total,
            has_prev=page > 1,
        )

    except Exception as e:
        logger.error(f"Failed to list workflow history: {e}", exc_info=True)
        raise internal_error("Failed to list workflow history")


# =============================================================================
# CLOUD TASKS INTERNAL CALLBACK ENDPOINT
# =============================================================================


class WorkflowTaskPayload(BaseModel):
    """Payload delivered by Cloud Tasks to the internal execute endpoint."""

    session_id: str
    user_id: str
    # Action is only set for continuation tasks; absent means initial execution.
    action: Optional[str] = None
    # Initial-execution fields (only present when action is None).
    input_method: Optional[str] = None
    job_input: Optional[str] = None
    user_data: Optional[Dict[str, Any]] = None


@router.post(
    "/internal/workflow/execute",
    include_in_schema=False,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def execute_workflow_task(
    payload: WorkflowTaskPayload,
    request: Request,
) -> Response:
    """Internal endpoint invoked by Cloud Tasks to execute or continue a workflow.

    Security: requests must carry the X-CloudTasks-Secret header matching the
    CLOUD_TASKS_SECRET env var. Cloud Tasks delivers it over HTTPS so it is
    encrypted in transit. This prevents unauthorized callers from triggering
    workflow execution.

    This endpoint intentionally returns 204 immediately after validating the
    request and starting the background coroutine — Cloud Tasks only cares that
    the endpoint acknowledges receipt (2xx) within the deadline.
    """
    provided_secret = request.headers.get("X-CloudTasks-Secret")
    if not verify_cloud_tasks_secret(provided_secret):
        raise unauthorized_error("Unauthorized")

    if payload.action == "continue":
        # Await the workflow directly so Cloud Run keeps this request "in-flight"
        # for the full duration. If we used asyncio.create_task() and returned 204
        # immediately, Cloud Run would think the request was done and could scale
        # down the instance mid-workflow. Awaiting here also lets Cloud Tasks see
        # any unhandled exception as a 5xx and retry (if retry is configured).
        await _continue_workflow_background(
            session_id=payload.session_id,
            user_id=payload.user_id,
        )
    else:
        if not payload.input_method or not payload.job_input or payload.user_data is None:
            raise validation_error("input_method, job_input, and user_data are required for initial execution")

        await _execute_workflow_background(
            session_id=payload.session_id,
            user_id=payload.user_id,
            input_method=payload.input_method,
            job_input=payload.job_input,
            user_data=payload.user_data,
            user_api_key=None,
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
