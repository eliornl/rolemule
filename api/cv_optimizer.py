"""
API endpoints for the CV Optimization Loop feature.

Provides on-demand iterative CV optimization for completed workflow sessions.
Uses the user's BYOK Gemini API key when set, otherwise falls back to the
server key configured in .env (GEMINI_API_KEY).
"""

import asyncio
import io
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, status
from fastapi.exceptions import HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from agents.cv_optimizer_loop import (
    CVOptimizationOrchestrator,
    IterationRecord,
    OptimizationConfig,
)
from agents.cv_optimizer_loop import _compose_cv_from_profile
from api.websocket import (
    broadcast_cv_optimization_complete,
    broadcast_cv_optimization_error,
    broadcast_cv_optimization_iteration,
    broadcast_cv_optimization_started,
)
from config.settings import get_settings
from models.database import WorkflowSession, User, WorkflowStatusEnum
from utils.auth import get_current_user
from utils.cache import (
    cache_cv_optimization,
    clear_cv_optimization_running,
    get_cached_cv_optimization,
    invalidate_cv_optimization,
    is_cv_optimization_running,
    set_cv_optimization_running,
    check_rate_limit,
)
from utils.database import get_database, get_session
from utils.encryption import decrypt_api_key
from utils.security import sanitize_llm_output
from utils.error_reporting import report_exception
from utils.error_responses import (
    APIError,
    ErrorCode,
    internal_error,
    not_found_error,
    no_api_key_error,
    rate_limit_error,
    validation_error,
)

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

logger: logging.Logger = logging.getLogger(__name__)
settings = get_settings()
router: APIRouter = APIRouter()

RATE_LIMIT_CV_OPTIMIZER: int = 5
RATE_LIMIT_CV_OPTIMIZER_DOWNLOAD: int = 10
RATE_LIMIT_WINDOW_SECONDS: int = 3600  # 1 hour

MAX_ITERATIONS_LIMIT: int = 7
MIN_ITERATIONS_LIMIT: int = 1
MAX_SCORE_THRESHOLD: float = 9.5
MIN_SCORE_THRESHOLD: float = 7.0

ODT_LIBREOFFICE_TIMEOUT_SECONDS: int = 90

CV_TO_HTML_SYSTEM_CONTEXT: str = """You are a professional CV/résumé document designer. Convert the provided markdown CV into clean, professional HTML that renders beautifully when imported into a word processor via LibreOffice.

Use ONLY inline CSS — no <style> tags, no external stylesheets, no classes.

Design rules:
- Font everywhere: font-family:Arial,Helvetica,sans-serif
- Candidate name <h1>: font-size:24px; font-weight:bold; margin:0 0 4px 0; color:#111
- Professional title <p> directly after name: font-size:13px; color:#555; margin:0 0 2px 0
- Contact line <p>: font-size:11px; color:#666; margin:0 0 20px 0
- Section headings <h2>: font-size:12px; font-weight:bold; text-transform:uppercase; letter-spacing:1px; border-bottom:1px solid #444; padding-bottom:3px; margin:18px 0 8px 0; color:#111
- Role/institution headings <h3>: font-size:12px; font-weight:bold; margin:10px 0 1px 0; color:#111
- Date/location line <p> after h3: font-size:11px; font-style:italic; color:#555; margin:0 0 4px 0
- Body paragraphs and <li>: font-size:11px; line-height:1.5; color:#222; margin:2px 0
- <ul>: margin:4px 0 8px 20px; padding:0
- <body>: font-family:Arial,Helvetica,sans-serif; max-width:720px; margin:0 auto; padding:40px 48px; background:#fff; color:#222

No decorative colors, gradients, shadows, or icons. Professional, clean, ATS-friendly.
Return ONLY the complete HTML document starting with <!DOCTYPE html>. No explanation, no markdown fences."""

CV_TO_HTML_PROMPT_TEMPLATE: str = """Convert this markdown CV to professional HTML following your design instructions exactly.

## MARKDOWN CV
{cv_markdown}

Return only the complete HTML document."""


# =============================================================================
# REQUEST / RESPONSE MODELS
# =============================================================================


class CvOptimizationStartRequest(BaseModel):
    """Optional configuration overrides for the optimization loop."""

    max_iterations: int = Field(
        default=5,
        ge=MIN_ITERATIONS_LIMIT,
        le=MAX_ITERATIONS_LIMIT,
        description="Maximum number of evaluate-revise iterations (1–7)",
    )
    score_threshold: float = Field(
        default=8.5,
        ge=MIN_SCORE_THRESHOLD,
        le=MAX_SCORE_THRESHOLD,
        description="Score that triggers early stopping (7.0–9.5)",
    )


class CvOptimizationStartResponse(BaseModel):
    """Response for the start endpoint."""

    session_id: str = Field(..., description="Workflow session ID")
    status: str = Field(..., description="'started' or 'already_running'")
    message: str = Field(..., description="Status message")


class CvOptimizationStatusResponse(BaseModel):
    """Response for the status endpoint."""

    session_id: str = Field(..., description="Workflow session ID")
    has_result: bool = Field(..., description="Whether a completed result exists")
    is_running: bool = Field(default=False, description="Whether optimization is in progress")
    best_score: Optional[float] = Field(None, description="Best score achieved so far")
    completed_at: Optional[str] = Field(None, description="ISO timestamp when optimization completed")


class CvOptimizationResultResponse(BaseModel):
    """Full optimization result response."""

    session_id: str = Field(..., description="Workflow session ID")
    has_result: bool = Field(..., description="Whether a completed result exists")
    result: Optional[Dict[str, Any]] = Field(None, description="Full optimization result")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


async def _markdown_cv_to_odt(cv_markdown: str, user_api_key: Optional[str]) -> bytes:
    """
    Convert a markdown CV to ODT bytes via Gemini HTML generation + LibreOffice.

    Gemini produces professionally styled HTML with inline CSS; LibreOffice
    headless converts that HTML to ODT.

    Args:
        cv_markdown: Markdown-formatted CV text
        user_api_key: BYOK Gemini API key, or None to use the server key

    Returns:
        ODT file contents as bytes

    Raises:
        ValueError: If Gemini returns unusable output or LibreOffice fails
    """
    from utils.llm_client import get_gemini_client

    gemini_client = await get_gemini_client()
    prompt = CV_TO_HTML_PROMPT_TEMPLATE.format(cv_markdown=cv_markdown[:12000])

    response = await gemini_client.generate(
        prompt=prompt,
        system=CV_TO_HTML_SYSTEM_CONTEXT,
        temperature=0.2,
        max_tokens=16000,
        user_api_key=user_api_key,
    )

    if response.get("filtered"):
        raise ValueError("HTML generation was blocked by the content filter")

    html_content = response.get("response", "").strip()

    # Strip markdown fences if the model wrapped the HTML anyway
    if html_content.startswith("```"):
        lines = html_content.splitlines()
        html_content = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        ).strip()

    # Find the start of actual HTML
    lower = html_content.lower()
    start = lower.find("<!doctype")
    if start == -1:
        start = lower.find("<html")
    if start == -1 or not html_content:
        raise ValueError("Gemini did not return valid HTML for document conversion")
    html_content = html_content[start:]

    tmpdir = tempfile.mkdtemp(prefix="cvo_odt_")
    try:
        html_path = os.path.join(tmpdir, "cv.html")
        odt_path = os.path.join(tmpdir, "cv.odt")

        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(html_content)

        loop = asyncio.get_event_loop()
        # HOME is set to tmpdir so each invocation gets an isolated
        # LibreOffice user-profile directory; avoids cross-request conflicts.
        lo_env = {**os.environ, "HOME": tmpdir}
        proc = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    [
                        "soffice",
                        "--headless",
                        "--norestore",
                        "--convert-to", "odt",
                        "--outdir", tmpdir,
                        html_path,
                    ],
                    capture_output=True,
                    timeout=ODT_LIBREOFFICE_TIMEOUT_SECONDS,
                    env=lo_env,
                ),
            ),
            timeout=ODT_LIBREOFFICE_TIMEOUT_SECONDS,
        )

        if proc.returncode != 0:
            logger.error(
                "LibreOffice ODT conversion failed: %s",
                proc.stderr.decode(errors="replace"),
            )
            raise ValueError("LibreOffice document conversion failed")

        if not os.path.exists(odt_path):
            raise ValueError("LibreOffice did not produce an output file")

        with open(odt_path, "rb") as fh:
            return fh.read()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _synthesize_jd_from_analysis(job_analysis: Dict[str, Any]) -> str:
    """Build a plain-text job description from structured job_analysis fields.

    Used when raw posting text is unavailable (URL or file-upload inputs).
    job_analysis is always present before CV optimization can start, so this
    always yields at least a minimal description.
    """
    parts: list[str] = []
    if title := job_analysis.get("job_title"):
        parts.append(f"Position: {title}")
    if company := job_analysis.get("company_name"):
        parts.append(f"Company: {company}")
    if reqs := job_analysis.get("required_qualifications"):
        items = "\n".join(f"- {r}" for r in reqs[:10])
        parts.append(f"Required qualifications:\n{items}")
    if prefs := job_analysis.get("preferred_qualifications"):
        items = "\n".join(f"- {p}" for p in prefs[:10])
        parts.append(f"Preferred qualifications:\n{items}")
    if skills := job_analysis.get("required_skills"):
        parts.append("Required skills: " + ", ".join(skills[:15]))
    return "\n\n".join(parts)


def _get_user_uuid(current_user: Dict[str, Any]) -> uuid.UUID:
    """Extract and convert user ID to UUID."""
    user_id = current_user.get("id") or current_user.get("_id")
    if isinstance(user_id, str):
        return uuid.UUID(user_id)
    return user_id


async def _get_user_api_key(db: AsyncSession, user_id: uuid.UUID) -> Optional[str]:
    """
    Decrypt and return the user's BYOK Gemini API key.

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        Decrypted API key string, or None if not set
    """
    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user and user.gemini_api_key_encrypted:
            return decrypt_api_key(user.gemini_api_key_encrypted)
    except Exception as e:
        logger.warning("Failed to decrypt user API key for user %s: %s", user_id, e)
    return None


# =============================================================================
# API ENDPOINTS
# =============================================================================


@router.post(
    "/{session_id}/start",
    response_model=CvOptimizationStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_cv_optimization(
    session_id: str,
    background_tasks: BackgroundTasks,
    request: CvOptimizationStartRequest = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> CvOptimizationStartResponse:
    """
    Start the CV optimization loop for a completed workflow session.

    Requires a BYOK Gemini API key. The optimization loop runs as a background
    task and broadcasts progress via WebSocket (cv_optimization_iteration events).

    Args:
        session_id: Workflow session ID
        background_tasks: FastAPI background tasks
        request: Optional config overrides (max_iterations, score_threshold)
        current_user: Authenticated user from JWT
        db: Database session

    Returns:
        CvOptimizationStartResponse with start status

    Raises:
        APIError: 404 session not found, 409 already running or wrong status,
                  422 no BYOK key, 429 rate limit exceeded
    """
    try:
        if request is None:
            request = CvOptimizationStartRequest()

        user_id = _get_user_uuid(current_user)

        # Rate limiting
        is_allowed, _ = await check_rate_limit(
            identifier=f"{user_id}:cv_optimizer",
            limit=RATE_LIMIT_CV_OPTIMIZER,
            window_seconds=RATE_LIMIT_WINDOW_SECONDS,
        )
        if not is_allowed:
            raise rate_limit_error(
                f"Rate limit exceeded. Maximum {RATE_LIMIT_CV_OPTIMIZER} optimization runs per hour."
            )

        # Resolve API key: prefer BYOK, fall back to server key from .env
        user_api_key = await _get_user_api_key(db, user_id)
        if (
            not user_api_key
            and not getattr(settings, "gemini_api_key", None)
            and not getattr(settings, "use_vertex_ai", False)
        ):
            raise no_api_key_error(
                "No Gemini API key is configured. "
                "Please add your API key in Settings → AI Setup."
            )

        # Load workflow session
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

        if workflow_session.workflow_status != WorkflowStatusEnum.COMPLETED.value:
            wf_status = workflow_session.workflow_status or "unknown"
            # If status is stuck at analysis_complete but both documents are already
            # present, the status column was never updated — heal it and continue.
            if (
                wf_status == WorkflowStatusEnum.ANALYSIS_COMPLETE.value
                and workflow_session.resume_recommendations
                and workflow_session.cover_letter
            ):
                workflow_session.workflow_status = WorkflowStatusEnum.COMPLETED.value
                await db.commit()
            else:
                if wf_status == WorkflowStatusEnum.ANALYSIS_COMPLETE.value:
                    detail = (
                        "The job analysis is done but your resume advice and cover letter haven't been generated yet. "
                        "Click the Continue button on this page to finish the workflow first."
                    )
                elif wf_status == WorkflowStatusEnum.IN_PROGRESS.value:
                    detail = "The workflow is still running. Please wait for it to finish."
                elif wf_status == WorkflowStatusEnum.AWAITING_CONFIRMATION.value:
                    detail = (
                        "The workflow is waiting for your confirmation. "
                        "Please review the analysis and confirm to continue."
                    )
                elif wf_status == WorkflowStatusEnum.FAILED.value:
                    detail = "The workflow failed. Please start a new application to use CV optimization."
                else:
                    detail = f"The workflow has not completed yet (status: {wf_status.replace('_', ' ')}). Please finish the workflow first."
                raise APIError(
                    ErrorCode.VALIDATION_ERROR,
                    detail,
                    status_code=409,
                )

        if not workflow_session.job_analysis or not workflow_session.user_data:
            raise validation_error(
                "Workflow is missing required data. Please ensure the workflow completed successfully."
            )

        # Single-flight lock
        claimed = await set_cv_optimization_running(session_id)
        if not claimed:
            raise APIError(
                ErrorCode.RESOURCE_CONFLICT,
                "CV optimization is already running for this session.",
                status_code=409,
            )

        config = OptimizationConfig(
            max_iterations=request.max_iterations,
            score_threshold=request.score_threshold,
        )

        background_tasks.add_task(
            _run_cv_optimization_background,
            session_id=session_id,
            user_id=str(user_id),
            user_api_key=user_api_key,
            config=config,
        )

        logger.info(
            "Started CV optimization for session %s user=%s max_iter=%d threshold=%.1f",
            session_id,
            user_id,
            config.max_iterations,
            config.score_threshold,
        )

        return CvOptimizationStartResponse(
            session_id=session_id,
            status="started",
            message="CV optimization started. Listen for cv_optimization_iteration WebSocket events.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start CV optimization for session %s: %s", session_id, e, exc_info=True)
        raise internal_error("Failed to start CV optimization")


@router.get("/{session_id}", response_model=CvOptimizationResultResponse)
async def get_cv_optimization(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> CvOptimizationResultResponse:
    """
    Get the full CV optimization result for a session.

    Returns the cached result if available, otherwise reads from database.

    Args:
        session_id: Workflow session ID
        current_user: Authenticated user from JWT
        db: Database session

    Returns:
        CvOptimizationResultResponse with optimization data if available

    Raises:
        APIError: 404 if session not found
    """
    try:
        user_id = _get_user_uuid(current_user)

        # Verify ownership first, then serve from cache if available
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

        cached = await get_cached_cv_optimization(session_id)
        if cached:
            return CvOptimizationResultResponse(
                session_id=session_id,
                has_result=True,
                result=cached,
            )

        optimization = workflow_session.cv_optimization

        if optimization:
            await cache_cv_optimization(session_id, optimization)

        return CvOptimizationResultResponse(
            session_id=session_id,
            has_result=optimization is not None,
            result=optimization,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get CV optimization for session %s: %s", session_id, e, exc_info=True)
        raise internal_error("Failed to get CV optimization result")


@router.get("/{session_id}/status", response_model=CvOptimizationStatusResponse)
async def get_cv_optimization_status(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> CvOptimizationStatusResponse:
    """
    Check the current status of CV optimization for a session.

    Args:
        session_id: Workflow session ID
        current_user: Authenticated user from JWT
        db: Database session

    Returns:
        CvOptimizationStatusResponse with running/completed state

    Raises:
        APIError: 404 if session not found
    """
    try:
        user_id = _get_user_uuid(current_user)

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

        optimization = workflow_session.cv_optimization
        running = await is_cv_optimization_running(session_id)

        best_score = None
        completed_at = None
        if optimization:
            best_score = optimization.get("best_score")
            completed_at = optimization.get("completed_at")

        return CvOptimizationStatusResponse(
            session_id=session_id,
            has_result=optimization is not None,
            is_running=running,
            best_score=best_score,
            completed_at=completed_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get CV optimization status for session %s: %s", session_id, e, exc_info=True
        )
        raise internal_error("Failed to get CV optimization status")


@router.get("/{session_id}/download-cv")
async def download_optimized_cv_odt(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> StreamingResponse:
    """
    Download the optimized CV as a professionally formatted ODT file.

    Gemini converts the stored markdown CV to professional HTML, then
    LibreOffice headless renders it to ODT.

    Args:
        session_id: Workflow session ID
        current_user: Authenticated user from JWT
        db: Database session

    Returns:
        ODT file attachment

    Raises:
        APIError: 404 if session or optimization result not found, 500 on
                  conversion failure
    """
    try:
        user_id = _get_user_uuid(current_user)

        is_allowed, _ = await check_rate_limit(
            identifier=f"{user_id}:cv_optimizer_download",
            limit=RATE_LIMIT_CV_OPTIMIZER_DOWNLOAD,
            window_seconds=RATE_LIMIT_WINDOW_SECONDS,
        )
        if not is_allowed:
            raise rate_limit_error(
                f"Rate limit exceeded. Maximum {RATE_LIMIT_CV_OPTIMIZER_DOWNLOAD} CV downloads per hour."
            )

        user_api_key = await _get_user_api_key(db, user_id)

        # Verify ownership first, then serve optimization data from cache
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

        cached = await get_cached_cv_optimization(session_id)
        optimization = cached if cached else workflow_session.cv_optimization

        if not optimization:
            raise not_found_error(
                "No optimization result found. Run CV optimization first."
            )

        cv_markdown = optimization.get("optimized_cv") or ""
        if not cv_markdown:
            raise not_found_error("Optimized CV text not found in result")

        odt_bytes = await _markdown_cv_to_odt(cv_markdown, user_api_key)

        buffer = io.BytesIO(odt_bytes)
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/vnd.oasis.opendocument.text",
            headers={"Content-Disposition": "attachment; filename=optimized-cv.odt"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to generate ODT for session %s: %s", session_id, e, exc_info=True
        )
        raise internal_error("Failed to generate ODT document")


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cv_optimization(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> None:
    """
    Clear CV optimization result, enabling a fresh re-run.

    Removes the result from both database and cache. Cannot be called
    while optimization is in progress.

    Args:
        session_id: Workflow session ID
        current_user: Authenticated user from JWT
        db: Database session

    Raises:
        APIError: 404 session not found, 409 if optimization is still running
    """
    try:
        user_id = _get_user_uuid(current_user)

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

        running = await is_cv_optimization_running(session_id)
        if running:
            raise APIError(
                ErrorCode.RESOURCE_CONFLICT,
                "Cannot clear results while optimization is in progress.",
                status_code=409,
            )

        workflow_session.cv_optimization = None
        flag_modified(workflow_session, "cv_optimization")
        await db.commit()

        await invalidate_cv_optimization(session_id)

        logger.info("Cleared CV optimization for session %s", session_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete CV optimization for session %s: %s", session_id, e, exc_info=True)
        raise internal_error("Failed to delete CV optimization result")


# =============================================================================
# BACKGROUND TASK
# =============================================================================


async def _run_cv_optimization_background(
    session_id: str,
    user_id: Optional[str] = None,
    user_api_key: Optional[str] = None,
    config: Optional[OptimizationConfig] = None,
) -> None:
    """
    Background task that runs the full CV optimization loop.

    Broadcasts cv_optimization_iteration after each loop step and
    cv_optimization_complete (or cv_optimization_error) when done.

    Args:
        session_id: Workflow session ID
        user_id: User ID string for WebSocket broadcasts
        user_api_key: User's BYOK Gemini API key
        config: Optimization configuration
    """
    if config is None:
        config = OptimizationConfig()

    try:
        async with get_session() as db:
            result = await db.execute(
                select(WorkflowSession).where(WorkflowSession.session_id == session_id)
            )
            workflow_session = result.scalar_one_or_none()

            if not workflow_session:
                logger.error("CV optimization: session %s not found", session_id)
                return

            ws_user_id = user_id or str(workflow_session.user_id)

            await broadcast_cv_optimization_started(ws_user_id, session_id)

            # Compose initial CV from structured profile data
            user_data = workflow_session.user_data or {}
            initial_cv = _compose_cv_from_profile(user_data)

            # Extract job description text.
            # job_input_data keys: input_method, job_input, source_url, detected_title,
            # detected_company, content_fingerprint.  "job_input" holds real text only for
            # MANUAL and EXTENSION inputs; URL inputs store the URL string and file uploads
            # store "[file content]".  For those cases synthesize from job_analysis instead.
            job_input = workflow_session.job_input_data or {}
            raw_input = job_input.get("job_input") or ""
            if raw_input and raw_input != "[file content]" and not raw_input.startswith("http"):
                job_description = raw_input
            else:
                job_description = _synthesize_jd_from_analysis(workflow_session.job_analysis or {})

            job_analysis = workflow_session.job_analysis or {}
            company_research = workflow_session.company_research

            # Build per-iteration broadcast callback
            async def _broadcast_iteration(record: IterationRecord) -> None:
                await broadcast_cv_optimization_iteration(
                    user_id=ws_user_id,
                    session_id=session_id,
                    iteration=record.iteration,
                    score=record.score,
                    strengths=record.strengths,
                    gaps=record.gaps,
                    action_items=record.action_items,
                )

            orchestrator = CVOptimizationOrchestrator()
            optimization_result = await orchestrator.run(
                session_id=session_id,
                user_id=ws_user_id,
                initial_cv=initial_cv,
                job_description=job_description,
                job_analysis=job_analysis,
                company_research=company_research,
                config=config,
                user_api_key=user_api_key,
                broadcast_iteration_fn=_broadcast_iteration,
            )

            result_dict = sanitize_llm_output(optimization_result.to_dict())

            logger.info(
                "CV optimization storing result session=%s cv_len=%d cl_len=%d",
                session_id,
                len(result_dict.get("optimized_cv", "")),
                len(result_dict.get("cover_letter", "")),
            )

            workflow_session.cv_optimization = result_dict
            flag_modified(workflow_session, "cv_optimization")
            await db.commit()

            await cache_cv_optimization(session_id, result_dict)

            logger.info(
                "CV optimization complete session=%s best_score=%.1f stop=%s",
                session_id,
                optimization_result.best_score,
                optimization_result.stop_reason,
            )

            await broadcast_cv_optimization_complete(
                user_id=ws_user_id,
                session_id=session_id,
                final_score=optimization_result.best_score,
                stop_reason=optimization_result.stop_reason,
                iteration_count=len(optimization_result.iteration_history),
            )

    except Exception as e:
        logger.error(
            "CV optimization background task failed session=%s: %s", session_id, e, exc_info=True
        )
        await report_exception(e, user_id=user_id)
        try:
            ws_user_id = user_id or session_id
            await broadcast_cv_optimization_error(
                ws_user_id, session_id, "CV optimization failed. Please try again."
            )
        except Exception as broadcast_err:
            logger.debug(
                "Failed to broadcast cv_optimization_error (WebSocket may be closed): %s",
                broadcast_err,
            )
    finally:
        await clear_cv_optimization_running(session_id)
