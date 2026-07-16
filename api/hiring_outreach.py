"""
API endpoints for hiring outreach generation.
Provides on-demand hiring contact suggestions and draft messages for completed job applications.
"""

import uuid
import logging
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, status, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm.attributes import flag_modified

from utils.auth import get_current_user
from utils.database import get_database, get_session
from utils.error_reporting import report_exception
from utils.cache import (
    get_cached_hiring_outreach,
    cache_hiring_outreach,
    invalidate_hiring_outreach,
    is_hiring_outreach_generating,
    set_hiring_outreach_generating,
    clear_hiring_outreach_generating,
    check_rate_limit,
)
from utils.security import sanitize_llm_output
from utils.error_responses import (
    APIError,
    ErrorCode,
    internal_error,
    not_found_error,
    rate_limit_error,
    validation_error,
)
from models.database import WorkflowSession
from agents.hiring_outreach import HiringOutreachAgent
from api.websocket import (
    broadcast_hiring_outreach_started,
    broadcast_hiring_outreach_complete,
    broadcast_hiring_outreach_error,
)
from utils.logging_config import sanitize_log_value

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

logger: logging.Logger = logging.getLogger(__name__)
router: APIRouter = APIRouter()

# Rate limiting: 5 hiring outreach generations per hour
RATE_LIMIT_HIRING_OUTREACH = 5
RATE_LIMIT_WINDOW_SECONDS = 3600  # 1 hour


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class HiringOutreachResponse(BaseModel):
    """Response model for getting hiring outreach."""

    session_id: str = Field(..., description="Workflow session ID")
    has_hiring_outreach: bool = Field(..., description="Whether hiring outreach exists")
    hiring_outreach: Optional[Dict[str, Any]] = Field(
        None, description="Hiring outreach contacts and draft messages"
    )
    generated_at: Optional[str] = Field(
        None, description="When the outreach was generated"
    )


class HiringOutreachGenerateResponse(BaseModel):
    """Response model for hiring outreach generation request."""

    session_id: str = Field(..., description="Workflow session ID")
    status: str = Field(
        ...,
        description="Generation status: generating, exists, or completed",
    )
    message: str = Field(..., description="Status message")


class HiringOutreachStatusResponse(BaseModel):
    """Response model for checking hiring outreach generation status."""

    session_id: str = Field(..., description="Workflow session ID")
    has_hiring_outreach: bool = Field(..., description="Whether hiring outreach exists")
    is_generating: bool = Field(
        False, description="Whether generation is in progress"
    )
    generated_at: Optional[str] = Field(
        None, description="When the outreach was generated"
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


# =============================================================================
# API ENDPOINTS
# =============================================================================


@router.get("/{session_id}", response_model=HiringOutreachResponse)
async def get_hiring_outreach(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> HiringOutreachResponse:
    """
    Get hiring outreach materials for a workflow session.

    Returns cached hiring outreach if available, otherwise checks database.

    Args:
        session_id: Workflow session ID
        current_user: Authenticated user from JWT
        db: Database session

    Returns:
        HiringOutreachResponse with hiring outreach data if available

    Raises:
        HTTPException: 404 if session not found
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

        cached = await get_cached_hiring_outreach(session_id)
        if cached and "data" in cached:
            return HiringOutreachResponse(
                session_id=session_id,
                has_hiring_outreach=True,
                hiring_outreach=cached["data"],
                generated_at=cached.get("cached_at"),
            )

        hiring_outreach = workflow_session.hiring_outreach
        generated_at = None

        if hiring_outreach:
            generated_at = hiring_outreach.get("generated_at")
            # Cache it for future requests
            await cache_hiring_outreach(session_id, hiring_outreach)

        return HiringOutreachResponse(
            session_id=session_id,
            has_hiring_outreach=hiring_outreach is not None,
            hiring_outreach=hiring_outreach,
            generated_at=generated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error('Failed to get hiring outreach: %s', sanitize_log_value(e), exc_info=True)
        raise internal_error("Failed to get hiring outreach")


@router.get("/{session_id}/status", response_model=HiringOutreachStatusResponse)
async def get_hiring_outreach_status(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> HiringOutreachStatusResponse:
    """
    Check the status of hiring outreach for a session.

    Useful for polling after starting generation.

    Args:
        session_id: Workflow session ID
        current_user: Authenticated user from JWT
        db: Database session

    Returns:
        HiringOutreachStatusResponse with current status

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

        hiring_outreach = workflow_session.hiring_outreach
        has_outreach = hiring_outreach is not None
        generated_at = hiring_outreach.get("generated_at") if hiring_outreach else None
        generating = await is_hiring_outreach_generating(session_id)

        return HiringOutreachStatusResponse(
            session_id=session_id,
            has_hiring_outreach=has_outreach,
            is_generating=generating,
            generated_at=generated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error('Failed to get hiring outreach status: %s', sanitize_log_value(e), exc_info=True)
        raise internal_error("Failed to get hiring outreach status")


@router.post("/{session_id}/generate", response_model=HiringOutreachGenerateResponse)
async def generate_hiring_outreach(
    session_id: str,
    background_tasks: BackgroundTasks,
    regenerate: bool = False,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> HiringOutreachGenerateResponse:
    """
    Generate hiring outreach materials for a workflow session.

    Generates personalized contact suggestions and draft messages. Generation happens in background.

    Args:
        session_id: Workflow session ID
        background_tasks: FastAPI background tasks
        regenerate: If True, regenerate even if outreach already exists
        current_user: Authenticated user from JWT
        db: Database session

    Returns:
        HiringOutreachGenerateResponse with generation status

    Raises:
        HTTPException: 400 if workflow not ready, 404 if not found, 429 if rate limited
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

        # Verify workflow has required data
        if not workflow_session.job_analysis:
            raise validation_error(
                "Workflow must have job analysis before generating hiring outreach. "
                "Please complete the workflow first."
            )

        # Check if already exists (unless regenerating) — before rate limit so
        # no-op exists responses do not consume the hourly budget.
        if workflow_session.hiring_outreach and not regenerate:
            return HiringOutreachGenerateResponse(
                session_id=session_id,
                status="exists",
                message="Hiring outreach already exists. Use regenerate=true to regenerate.",
            )

        # Rate limiting (only when we will actually generate)
        is_allowed, remaining = await check_rate_limit(
            identifier=f"{user_id}:hiring_outreach",
            limit=RATE_LIMIT_HIRING_OUTREACH,
            window_seconds=RATE_LIMIT_WINDOW_SECONDS,
        )
        if not is_allowed:
            raise rate_limit_error(
                f"Rate limit exceeded. Maximum {RATE_LIMIT_HIRING_OUTREACH} generations per hour."
            )

        # Resolve LLM context (BYOK / Ollama / Vertex)
        from utils.llm_context import require_user_llm_context

        _u, llm_ctx, _p = await require_user_llm_context(db, user_id)
        user_api_key = llm_ctx.user_api_key
        llm_provider = llm_ctx.provider
        from utils.llm_preferences import load_preferred_model

        preferred_model = await load_preferred_model(
            db, user_id, user_api_key, has_credentials=True
        )

        # Invalidate cache if regenerating
        if regenerate:
            await invalidate_hiring_outreach(session_id)

        # Atomically claim the generating slot — returns False if another request already holds it
        claimed = await set_hiring_outreach_generating(session_id)
        if not claimed:
            raise APIError(
                ErrorCode.RESOURCE_CONFLICT,
                "Hiring outreach generation is already in progress for this session.",
                status_code=409,
            )

        # Generate in background
        background_tasks.add_task(
            _generate_hiring_outreach_background,
            session_id=session_id,
            user_id=str(user_id),
            user_api_key=user_api_key,
            preferred_model=preferred_model,
            llm_provider=llm_provider,
        )

        logger.info('Started hiring outreach generation for session %s', sanitize_log_value(session_id))

        return HiringOutreachGenerateResponse(
            session_id=session_id,
            status="generating",
            message="Hiring outreach generation started. Check status endpoint for completion.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            'Failed to start hiring outreach generation: %s',
            sanitize_log_value(e),
            exc_info=True,
        )
        raise internal_error("Failed to start hiring outreach generation")


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_hiring_outreach(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> None:
    """
    Delete hiring outreach materials for a workflow session.

    Removes hiring outreach from both database and cache.

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
        workflow_session.hiring_outreach = None
        flag_modified(workflow_session, "hiring_outreach")
        await db.commit()

        # Clear from cache
        await invalidate_hiring_outreach(session_id)

        logger.info('Deleted hiring outreach for session %s', sanitize_log_value(session_id))

    except HTTPException:
        raise
    except Exception as e:
        logger.error('Failed to delete hiring outreach: %s', sanitize_log_value(e), exc_info=True)
        raise internal_error("Failed to delete hiring outreach")


# =============================================================================
# BACKGROUND TASKS
# =============================================================================


async def _generate_hiring_outreach_background(
    session_id: str,
    user_id: Optional[str] = None,
    user_api_key: Optional[str] = None,
    preferred_model: Optional[str] = None,
    llm_provider: Optional[str] = None,
) -> None:
    """
    Background task to generate hiring outreach materials.

    Args:
        session_id: Workflow session ID
        user_id: User ID string for WebSocket broadcasts
        user_api_key: Optional user API key for BYOK mode
        preferred_model: Optional BYOK preferred model from Settings
        llm_provider: Resolved LLM provider (gemini, openai, anthropic, ollama)
    """
    try:
        async with get_session() as db:
            # Get workflow session
            result = await db.execute(
                select(WorkflowSession).where(WorkflowSession.session_id == session_id)
            )
            workflow_session = result.scalar_one_or_none()

            if not workflow_session:
                logger.error(
                    'Workflow session %s not found for hiring outreach',
                    sanitize_log_value(session_id),
                )
                return

            ws_user_id = user_id or str(workflow_session.user_id)

            # Notify clients that generation is underway
            await broadcast_hiring_outreach_started(ws_user_id, session_id)

            # Initialize agent
            agent = HiringOutreachAgent()

            # Generate hiring outreach
            hiring_outreach = await agent.generate(
                job_analysis=workflow_session.job_analysis or {},
                company_research=workflow_session.company_research or {},
                profile_matching=workflow_session.profile_matching or {},
                user_profile=workflow_session.user_data or {},
                user_api_key=user_api_key,
                model=preferred_model,
                llm_provider=llm_provider,
            )

            # Sanitize all string values before storing to prevent XSS when rendered
            hiring_outreach = sanitize_llm_output(hiring_outreach)

            # Save to database
            workflow_session.hiring_outreach = hiring_outreach
            flag_modified(workflow_session, "hiring_outreach")
            await db.commit()

            # Cache result
            await cache_hiring_outreach(session_id, hiring_outreach)

            logger.info(
                'Hiring outreach generated successfully for session %s',
                sanitize_log_value(session_id),
            )

            # Notify clients that generation completed
            await broadcast_hiring_outreach_complete(ws_user_id, session_id)

    except Exception as e:
        logger.error(
            'Hiring outreach generation failed for session %s: %s',
            sanitize_log_value(session_id),
            sanitize_log_value(e),
            exc_info=True,
        )
        await report_exception(e, user_id=user_id)
        try:
            ws_user_id = user_id or session_id
            await broadcast_hiring_outreach_error(
                ws_user_id, session_id, "Hiring outreach generation failed"
            )
        except Exception as broadcast_err:
            logger.debug(
                'Failed to broadcast hiring outreach error (WebSocket may be closed): %s',
                sanitize_log_value(broadcast_err),
            )
    finally:
        # Always clear the generating flag so clients don't get stuck on is_generating=True
        await clear_hiring_outreach_generating(session_id)
