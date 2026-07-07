"""
API endpoints for interview preparation generation.
Provides on-demand interview prep materials for completed job applications.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update
from sqlalchemy.orm.attributes import flag_modified

from utils.auth import get_current_user
from utils.database import get_database, get_session
from utils.error_reporting import report_exception
from utils.cache import (
    get_cached_interview_prep,
    cache_interview_prep,
    invalidate_interview_prep,
    is_interview_prep_generating,
    set_interview_prep_generating,
    clear_interview_prep_generating,
    check_rate_limit,
)
from utils.encryption import decrypt_api_key
from utils.security import sanitize_llm_output
from utils.error_responses import APIError, ErrorCode, internal_error, not_found_error, rate_limit_error, validation_error
from models.database import WorkflowSession, User
from agents.interview_prep import InterviewPrepAgent
from api.websocket import (
    broadcast_interview_prep_started,
    broadcast_interview_prep_complete,
    broadcast_interview_prep_error,
)
from config.settings import get_settings
from utils.logging_config import sanitize_log_value

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

logger: logging.Logger = logging.getLogger(__name__)
settings = get_settings()
router: APIRouter = APIRouter()

# Rate limiting: 5 interview prep generations per hour
RATE_LIMIT_INTERVIEW_PREP = 5
RATE_LIMIT_WINDOW_SECONDS = 3600  # 1 hour


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class InterviewPrepResponse(BaseModel):
    """Response model for getting interview prep."""
    
    session_id: str = Field(..., description="Workflow session ID")
    has_interview_prep: bool = Field(..., description="Whether interview prep exists")
    interview_prep: Optional[Dict[str, Any]] = Field(
        None, description="Interview preparation materials"
    )
    generated_at: Optional[str] = Field(
        None, description="When the prep was generated"
    )


class InterviewPrepGenerateResponse(BaseModel):
    """Response model for interview prep generation request."""
    
    session_id: str = Field(..., description="Workflow session ID")
    status: str = Field(
        ..., 
        description="Generation status: generating, exists, or completed"
    )
    message: str = Field(..., description="Status message")


class InterviewPrepStatusResponse(BaseModel):
    """Response model for checking interview prep generation status."""
    
    session_id: str = Field(..., description="Workflow session ID")
    has_interview_prep: bool = Field(..., description="Whether interview prep exists")
    is_generating: bool = Field(
        False, description="Whether generation is in progress"
    )
    generated_at: Optional[str] = Field(
        None, description="When the prep was generated"
    )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _get_user_uuid(current_user: Dict[str, Any]) -> uuid.UUID:
    """Extract and convert user ID to UUID."""
    user_id = current_user.get("id") or current_user.get("_id")
    if isinstance(user_id, str):
        return uuid.UUID(user_id)
    return user_id


async def _get_user_api_key(db: AsyncSession, user_id: uuid.UUID) -> Optional[str]:
    """Get decrypted user API key for BYOK mode."""
    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if user and user.gemini_api_key_encrypted:
            return decrypt_api_key(user.gemini_api_key_encrypted)
    except Exception as e:
        logger.warning(f"Failed to decrypt user API key: {e}")
    
    return None


async def _check_api_key_available(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Check if an API key is available (user's or server's)."""
    # Check for user API key
    user_api_key = await _get_user_api_key(db, user_id)
    if user_api_key:
        return True
    
    # Check for server API key
    server_has_key = bool(getattr(settings, 'gemini_api_key', None)) or getattr(
        settings, 'use_vertex_ai', False
    )
    return server_has_key


# =============================================================================
# API ENDPOINTS
# =============================================================================


@router.get("/{session_id}", response_model=InterviewPrepResponse)
async def get_interview_prep(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> InterviewPrepResponse:
    """
    Get interview preparation materials for a workflow session.
    
    Returns cached interview prep if available, otherwise checks database.
    
    Args:
        session_id: Workflow session ID
        current_user: Authenticated user from JWT
        db: Database session
        
    Returns:
        InterviewPrepResponse with interview prep data if available
        
    Raises:
        HTTPException: 404 if session not found
    """
    try:
        user_id = _get_user_uuid(current_user)
        
        # Check cache first
        cached = await get_cached_interview_prep(session_id)
        if cached and "data" in cached:
            return InterviewPrepResponse(
                session_id=session_id,
                has_interview_prep=True,
                interview_prep=cached["data"],
                generated_at=cached.get("cached_at"),
            )
        
        # Query database
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
        
        interview_prep = workflow_session.interview_prep
        generated_at = None
        
        if interview_prep:
            generated_at = interview_prep.get("generated_at")
            # Cache it for future requests
            await cache_interview_prep(session_id, interview_prep)
        
        return InterviewPrepResponse(
            session_id=session_id,
            has_interview_prep=interview_prep is not None,
            interview_prep=interview_prep,
            generated_at=generated_at,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get interview prep: {e}", exc_info=True)
        raise internal_error("Failed to get interview prep")


@router.get("/{session_id}/status", response_model=InterviewPrepStatusResponse)
async def get_interview_prep_status(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> InterviewPrepStatusResponse:
    """
    Check the status of interview prep for a session.
    
    Useful for polling after starting generation.
    
    Args:
        session_id: Workflow session ID
        current_user: Authenticated user from JWT
        db: Database session
        
    Returns:
        InterviewPrepStatusResponse with current status
        
    Raises:
        HTTPException: 404 if session not found
    """
    try:
        user_id = _get_user_uuid(current_user)
        
        # Query database
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
        
        interview_prep = workflow_session.interview_prep
        has_prep = interview_prep is not None
        generated_at = interview_prep.get("generated_at") if interview_prep else None
        generating = await is_interview_prep_generating(session_id)

        return InterviewPrepStatusResponse(
            session_id=session_id,
            has_interview_prep=has_prep,
            is_generating=generating,
            generated_at=generated_at,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get interview prep status: {e}", exc_info=True)
        raise internal_error("Failed to get interview prep status")


@router.post("/{session_id}/generate", response_model=InterviewPrepGenerateResponse)
async def generate_interview_prep(
    session_id: str,
    background_tasks: BackgroundTasks,
    regenerate: bool = False,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> InterviewPrepGenerateResponse:
    """
    Generate interview preparation materials for a workflow session.
    
    Generates personalized interview prep including predicted questions,
    answer frameworks, and preparation tips. Generation happens in background.
    
    Args:
        session_id: Workflow session ID
        background_tasks: FastAPI background tasks
        regenerate: If True, regenerate even if prep already exists
        current_user: Authenticated user from JWT
        db: Database session
        
    Returns:
        InterviewPrepGenerateResponse with generation status
        
    Raises:
        HTTPException: 400 if workflow not ready, 404 if not found, 429 if rate limited
    """
    try:
        user_id = _get_user_uuid(current_user)
        
        # Rate limiting
        is_allowed, remaining = await check_rate_limit(
            identifier=f"{user_id}:interview_prep",
            limit=RATE_LIMIT_INTERVIEW_PREP,
            window_seconds=RATE_LIMIT_WINDOW_SECONDS,
        )
        if not is_allowed:
            raise rate_limit_error(f"Rate limit exceeded. Maximum {RATE_LIMIT_INTERVIEW_PREP} generations per hour.")
        
        # Query workflow session
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
        
        # Verify workflow has required data
        if not workflow_session.job_analysis:
            raise validation_error("Workflow must have job analysis before generating interview prep. Please complete the workflow first.")
        
        # Check if already exists (unless regenerating)
        if workflow_session.interview_prep and not regenerate:
            return InterviewPrepGenerateResponse(
                session_id=session_id,
                status="exists",
                message="Interview prep already exists. Use regenerate=true to regenerate.",
            )
        
        # Check API key availability
        if not await _check_api_key_available(db, user_id):
            raise validation_error("No API key configured. Please add your Gemini API key in Settings.")
        
        # Get user API key for BYOK
        user_api_key = await _get_user_api_key(db, user_id)
        
        # Invalidate cache if regenerating
        if regenerate:
            await invalidate_interview_prep(session_id)

        # Atomically claim the generating slot — returns False if another request already holds it
        claimed = await set_interview_prep_generating(session_id)
        if not claimed:
            raise APIError(ErrorCode.RESOURCE_CONFLICT, "Interview prep generation is already in progress for this session.", status_code=409)

        # Generate in background
        background_tasks.add_task(
            _generate_interview_prep_background,
            session_id=session_id,
            user_id=str(user_id),
            user_api_key=user_api_key,
        )
        
        logger.info(f"Started interview prep generation for session {sanitize_log_value(session_id)}")
        
        return InterviewPrepGenerateResponse(
            session_id=session_id,
            status="generating",
            message="Interview prep generation started. Check status endpoint for completion.",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start interview prep generation: {e}", exc_info=True)
        raise internal_error("Failed to start interview prep generation")


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interview_prep(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> None:
    """
    Delete interview preparation materials for a workflow session.
    
    Removes interview prep from both database and cache.
    
    Args:
        session_id: Workflow session ID
        current_user: Authenticated user from JWT
        db: Database session
        
    Raises:
        HTTPException: 404 if session not found
    """
    try:
        user_id = _get_user_uuid(current_user)
        
        # Query workflow session
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
        
        # Clear from database
        workflow_session.interview_prep = None
        flag_modified(workflow_session, "interview_prep")
        await db.commit()
        
        # Clear from cache
        await invalidate_interview_prep(session_id)
        
        logger.info(f"Deleted interview prep for session {sanitize_log_value(session_id)}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete interview prep: {e}", exc_info=True)
        raise internal_error("Failed to delete interview prep")


# =============================================================================
# BACKGROUND TASKS
# =============================================================================


async def _generate_interview_prep_background(
    session_id: str,
    user_id: Optional[str] = None,
    user_api_key: Optional[str] = None,
) -> None:
    """
    Background task to generate interview preparation materials.

    Args:
        session_id: Workflow session ID
        user_id: User ID string for WebSocket broadcasts
        user_api_key: Optional user API key for BYOK mode
    """
    try:
        async with get_session() as db:
            # Get workflow session
            result = await db.execute(
                select(WorkflowSession).where(WorkflowSession.session_id == session_id)
            )
            workflow_session = result.scalar_one_or_none()

            if not workflow_session:
                logger.error(f"Workflow session {sanitize_log_value(session_id)} not found for interview prep")
                return

            ws_user_id = user_id or str(workflow_session.user_id)

            # Notify clients that generation is underway
            await broadcast_interview_prep_started(ws_user_id, session_id)

            # Initialize agent
            agent = InterviewPrepAgent()

            # Generate interview prep
            interview_prep = await agent.generate(
                job_analysis=workflow_session.job_analysis or {},
                company_research=workflow_session.company_research or {},
                profile_matching=workflow_session.profile_matching or {},
                user_profile=workflow_session.user_data or {},
                user_api_key=user_api_key,
            )

            # Sanitize all string values before storing to prevent XSS when rendered
            interview_prep = {
                k: sanitize_llm_output(v) if isinstance(v, str) else v
                for k, v in interview_prep.items()
            }

            # Save to database
            workflow_session.interview_prep = interview_prep
            flag_modified(workflow_session, "interview_prep")
            await db.commit()

            # Cache result
            await cache_interview_prep(session_id, interview_prep)

            logger.info(f"Interview prep generated successfully for session {sanitize_log_value(session_id)}")

            # Notify clients that generation completed
            await broadcast_interview_prep_complete(ws_user_id, session_id)

    except Exception as e:
        logger.error(f"Interview prep generation failed for session {sanitize_log_value(session_id)}: {e}", exc_info=True)
        await report_exception(e, user_id=user_id)
        # Mark session as errored so it can be retried
        try:
            async with get_session() as _err_db:
                await _err_db.execute(
                    update(WorkflowSession)
                    .where(WorkflowSession.session_id == session_id)
                    .values(
                        error_message="Interview prep generation failed",
                        processing_end_time=datetime.now(timezone.utc),
                    )
                )
                await _err_db.commit()
        except Exception as _db_err:
            logger.error(
                f"Interview prep {session_id}: failed to persist error state: {_db_err}"
            )
        try:
            ws_user_id = user_id or session_id
            await broadcast_interview_prep_error(ws_user_id, session_id, "Interview prep generation failed")
        except Exception as broadcast_err:
            logger.debug("Failed to broadcast interview prep error (WebSocket may be closed): %s", broadcast_err)
    finally:
        # Always clear the generating flag so clients don't get stuck on is_generating=True
        await clear_interview_prep_generating(session_id)
