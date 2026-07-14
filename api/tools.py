"""
API endpoints for career communication tools.
Provides AI-powered generation of thank you notes, rejection analysis, reference requests,
job comparison, follow-up emails, and salary negotiation coaching.
"""

import uuid
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from utils.auth import get_current_user
from utils.database import get_database
from utils.cache import (
    check_rate_limit_with_headers,
    get_cached_tool_result,
    cache_tool_result,
)
from utils.encryption import decrypt_api_key
from utils.security import sanitize_text
from utils.logging_config import sanitize_log_value
from utils.error_responses import internal_error, no_api_key_error, rate_limit_error, validation_error
from models.database import User, JobApplication
from agents.thank_you_writer import ThankYouWriterAgent
from agents.rejection_analyzer import RejectionAnalyzerAgent
from agents.reference_request_writer import ReferenceRequestWriterAgent
from agents.job_comparison import JobComparisonAgent
from agents.followup_generator import FollowUpGeneratorAgent
from agents.salary_coach import SalaryCoachAgent
from config.settings import get_settings

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

logger: logging.Logger = logging.getLogger(__name__)
settings = get_settings()
router: APIRouter = APIRouter()

# Rate limiting: 10 uses per tool per hour
RATE_LIMIT = 10
RATE_LIMIT_WINDOW_SECONDS = 3600  # 1 hour


# =============================================================================
# RATE LIMIT HELPER
# =============================================================================


async def _check_rate_limit_and_get_headers(
    user_id: uuid.UUID,
    tool_name: str,
    limit: int = RATE_LIMIT,
) -> Dict[str, str]:
    """
    Check rate limit and return headers dict.
    
    Args:
        user_id: User's UUID
        tool_name: Name of the tool for rate limit key
        limit: Maximum requests allowed (default: RATE_LIMIT)
        
    Returns:
        Dict of rate limit headers to include in response
        
    Raises:
        HTTPException: 429 if rate limit exceeded
    """
    rate_result = await check_rate_limit_with_headers(
        identifier=f"{user_id}:{tool_name}",
        limit=limit,
        window_seconds=RATE_LIMIT_WINDOW_SECONDS,
    )
    
    if not rate_result.allowed:
        raise rate_limit_error(f"Rate limit exceeded. Maximum {limit} requests per hour. Resets in {rate_result.reset_seconds} seconds.")
    
    return rate_result.get_headers()


# =============================================================================
# REQUEST/RESPONSE MODELS - THANK YOU NOTE
# =============================================================================


class ThankYouNoteRequest(BaseModel):
    """Request model for generating thank you notes."""
    
    application_id: Optional[str] = Field(
        None, description="Optional application ID to use job context"
    )
    interviewer_name: str = Field(
        ..., min_length=1, max_length=100, description="Name of the interviewer"
    )
    interviewer_role: Optional[str] = Field(
        None, max_length=100, description="Role/title of the interviewer"
    )
    interview_type: str = Field(
        ..., max_length=50, description="Type of interview (phone, video, onsite, technical, etc.)"
    )
    key_discussion_points: Optional[List[str]] = Field(
        None, max_length=20, description="Key topics discussed during the interview"
    )
    company_name: Optional[str] = Field(
        None, max_length=200, description="Company name (if no application_id)"
    )
    job_title: Optional[str] = Field(
        None, max_length=200, description="Job title (if no application_id)"
    )
    additional_notes: Optional[str] = Field(
        None, max_length=1000, description="Any additional context"
    )


class ThankYouNoteResponse(BaseModel):
    """Response model for thank you note generation."""
    
    subject_line: str = Field(..., description="Email subject line")
    email_body: str = Field(..., description="Full email body")
    key_points_referenced: List[str] = Field(
        default_factory=list, description="Discussion points referenced in the note"
    )
    tone: str = Field(..., description="Tone of the email (professional, warm, etc.)")
    generated_at: str = Field(..., description="Generation timestamp")


# =============================================================================
# REQUEST/RESPONSE MODELS - REJECTION ANALYSIS
# =============================================================================


class RejectionAnalysisRequest(BaseModel):
    """Request model for rejection analysis."""
    
    rejection_email: str = Field(
        ..., min_length=10, max_length=5000, description="The rejection email text"
    )
    application_id: Optional[str] = Field(
        None, description="Optional application ID for context"
    )
    job_title: Optional[str] = Field(
        None, max_length=200, description="Job title applied for"
    )
    company_name: Optional[str] = Field(
        None, max_length=200, description="Company name"
    )
    interview_stage: Optional[str] = Field(
        None, max_length=100, description="Stage at which rejection occurred"
    )


class RejectionAnalysisResponse(BaseModel):
    """Response model for rejection analysis."""
    
    analysis_summary: str = Field(..., description="Overall analysis summary")
    likely_reasons: List[str] = Field(
        default_factory=list, description="Potential reasons for rejection"
    )
    improvement_suggestions: List[str] = Field(
        default_factory=list, description="Actionable improvement suggestions"
    )
    positive_signals: List[str] = Field(
        default_factory=list, description="Any positive signs in the rejection"
    )
    follow_up_recommended: bool = Field(
        ..., description="Whether follow-up is recommended"
    )
    follow_up_template: Optional[str] = Field(
        None, description="Optional follow-up email template"
    )
    encouragement: str = Field(..., description="Encouraging message")
    generated_at: str = Field(..., description="Generation timestamp")


# =============================================================================
# REQUEST/RESPONSE MODELS - REFERENCE REQUEST
# =============================================================================


class ReferenceRequestRequest(BaseModel):
    """Request model for reference request generation."""
    
    reference_name: str = Field(
        ..., min_length=1, max_length=100, description="Name of the reference"
    )
    reference_relationship: str = Field(
        ..., max_length=100, description="Relationship (former manager, colleague, mentor, etc.)"
    )
    reference_company: Optional[str] = Field(
        None, max_length=200, description="Company where you worked together"
    )
    years_worked_together: Optional[int] = Field(
        None, ge=0, le=50, description="Years you worked together"
    )
    target_job_title: Optional[str] = Field(
        None, max_length=200, description="Job you're applying for"
    )
    target_company: Optional[str] = Field(
        None, max_length=200, description="Company you're applying to"
    )
    key_accomplishments: Optional[List[str]] = Field(
        None, max_length=20, description="Key accomplishments to highlight"
    )
    time_since_contact: Optional[str] = Field(
        None, max_length=100, description="How long since you last contacted them"
    )
    user_name: Optional[str] = Field(
        None, max_length=100, description="Your name for the email"
    )


class ReferenceRequestResponse(BaseModel):
    """Response model for reference request generation."""
    
    subject_line: str = Field(..., description="Email subject line")
    email_body: str = Field(..., description="Full email body")
    talking_points: List[str] = Field(
        default_factory=list, description="Points to mention if they need context"
    )
    follow_up_timeline: str = Field(
        ..., description="Suggested follow-up timeline"
    )
    tips: List[str] = Field(
        default_factory=list, description="Tips for the reference request"
    )
    generated_at: str = Field(..., description="Generation timestamp")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _get_user_uuid(current_user: Dict[str, Any]) -> uuid.UUID:
    """Extract and convert user ID to UUID."""
    user_id = current_user.get("id") or current_user.get("_id")
    if isinstance(user_id, str):
        return uuid.UUID(user_id)
    return user_id


async def _resolve_llm(db: AsyncSession, user_id: uuid.UUID):
    """Return UserLLMContext or raise no_api_key_error."""
    from utils.llm_context import require_user_llm_context

    _u, ctx, _p = await require_user_llm_context(db, user_id)
    return ctx


async def _get_user_api_key(db: AsyncSession, user_id: uuid.UUID) -> Optional[str]:
    """Get decrypted BYOK key for the user's preferred provider (if ready)."""
    try:
        ctx = await _resolve_llm(db, user_id)
        return ctx.user_api_key
    except Exception as e:
        from utils.error_responses import APIError

        if isinstance(e, APIError) and getattr(e, "error_code", None) and getattr(e.error_code, "value", e.error_code) == "CFG_6001":
            return None
        logger.warning('Failed to resolve user API key: %s', sanitize_log_value(e))
    return None


async def _check_api_key_available(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Check if the user has configured provider + credentials."""
    try:
        await _resolve_llm(db, user_id)
        return True
    except Exception:
        return False


async def _get_application_context(
    db: AsyncSession, 
    user_id: uuid.UUID, 
    application_id: str
) -> Optional[Dict[str, Any]]:
    """Get job application context for enriching requests."""
    try:
        app_uuid = uuid.UUID(application_id)
        
        result = await db.execute(
            select(JobApplication).where(
                and_(
                    JobApplication.id == app_uuid,
                    JobApplication.user_id == user_id,
                )
            )
        )
        application = result.scalar_one_or_none()
        
        if not application:
            return None
        
        return {
            "job_title": application.job_title,
            "company_name": application.company_name,
        }
        
    except (ValueError, Exception) as e:
        logger.warning('Failed to get application context: %s', sanitize_log_value(e))
        return None


# =============================================================================
# API ENDPOINTS - THANK YOU NOTE
# =============================================================================


@router.post("/thank-you", response_model=ThankYouNoteResponse)
async def generate_thank_you_note(
    request: ThankYouNoteRequest,
    response: Response,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> ThankYouNoteResponse:
    """
    Generate a personalized thank you note after a job interview.
    
    Can use an existing application for context or standalone inputs.
    
    Args:
        request: Thank you note request with interview details
        current_user: Authenticated user from JWT
        db: Database session
        
    Returns:
        ThankYouNoteResponse with generated email
        
    Raises:
        HTTPException: 400 if missing required info, 429 if rate limited
    """
    try:
        user_id = _get_user_uuid(current_user)
        
        # Rate limiting with headers
        rate_headers = await _check_rate_limit_and_get_headers(user_id, "thank_you")
        for header, value in rate_headers.items():
            response.headers[header] = value
        
        # Check API key availability
        if not await _check_api_key_available(db, user_id):
            raise no_api_key_error()
        
        # Get application context if provided
        company_name = request.company_name
        job_title = request.job_title
        
        if request.application_id:
            context = await _get_application_context(db, user_id, request.application_id)
            if context:
                company_name = company_name or context.get("company_name")
                job_title = job_title or context.get("job_title")
        
        # Validate we have required info
        if not company_name or not job_title:
            raise validation_error("Company name and job title are required. Provide them directly or via application_id.")
        
        # Get user API key for BYOK
        from utils.llm_preferences import load_preferred_model
        llm_ctx = await _resolve_llm(db, user_id)
        user_api_key = llm_ctx.user_api_key
        llm_provider = llm_ctx.provider
        preferred_model = await load_preferred_model(
            db, user_id, user_api_key, has_credentials=True
        )

        # Build sanitized payload for cache key
        sanitized_payload = {
            "tool": "thank_you",
            "interviewer_name": sanitize_text(request.interviewer_name),
            "interview_type": sanitize_text(request.interview_type),
            "company_name": sanitize_text(company_name),
            "job_title": sanitize_text(job_title),
            "interviewer_role": sanitize_text(request.interviewer_role) if request.interviewer_role else None,
            "key_discussion_points": [sanitize_text(p) for p in request.key_discussion_points] if request.key_discussion_points else None,
            "additional_notes": sanitize_text(request.additional_notes) if request.additional_notes else None,
        }

        cached = await get_cached_tool_result("thank_you", sanitized_payload)
        if cached:
            result = cached
        else:
            agent = ThankYouWriterAgent()
            result = await agent.generate(
                **{k: v for k, v in sanitized_payload.items() if k != "tool"},
                user_api_key=user_api_key,
                model=preferred_model,
            llm_provider=llm_provider,
            )
            await cache_tool_result("thank_you", sanitized_payload, result)

        logger.info('Generated thank you note for user %s', sanitize_log_value(user_id))

        return ThankYouNoteResponse(
            subject_line=result.get("subject_line", ""),
            email_body=result.get("email_body", ""),
            key_points_referenced=result.get("key_points_referenced", []),
            tone=result.get("tone", "professional"),
            generated_at=result.get("generated_at", datetime.now(timezone.utc).isoformat()),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Failed to generate thank you note: %s', sanitize_log_value(e), exc_info=True)
        raise internal_error("Failed to generate thank you note")


# =============================================================================
# API ENDPOINTS - REJECTION ANALYSIS
# =============================================================================


@router.post("/rejection-analysis", response_model=RejectionAnalysisResponse)
async def analyze_rejection(
    request: RejectionAnalysisRequest,
    response: Response,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> RejectionAnalysisResponse:
    """
    Analyze a job rejection email and provide constructive feedback.
    
    Helps users understand what might have happened and how to improve.
    
    Args:
        request: Rejection analysis request with email text
        current_user: Authenticated user from JWT
        db: Database session
        
    Returns:
        RejectionAnalysisResponse with analysis and suggestions
        
    Raises:
        HTTPException: 429 if rate limited
    """
    try:
        user_id = _get_user_uuid(current_user)
        
        # Rate limiting with headers
        rate_headers = await _check_rate_limit_and_get_headers(user_id, "rejection_analysis")
        for header, value in rate_headers.items():
            response.headers[header] = value
        
        # Check API key availability
        if not await _check_api_key_available(db, user_id):
            raise no_api_key_error()
        
        # Get application context if provided
        job_title = request.job_title
        company_name = request.company_name
        
        if request.application_id:
            context = await _get_application_context(db, user_id, request.application_id)
            if context:
                job_title = job_title or context.get("job_title")
                company_name = company_name or context.get("company_name")
        
        # Get user API key for BYOK
        from utils.llm_preferences import load_preferred_model
        llm_ctx = await _resolve_llm(db, user_id)
        user_api_key = llm_ctx.user_api_key
        llm_provider = llm_ctx.provider
        preferred_model = await load_preferred_model(
            db, user_id, user_api_key, has_credentials=True
        )

        sanitized_payload = {
            "tool": "rejection_analysis",
            "rejection_email": sanitize_text(request.rejection_email),
            "job_title": sanitize_text(job_title) if job_title else None,
            "company_name": sanitize_text(company_name) if company_name else None,
            "interview_stage": sanitize_text(request.interview_stage) if request.interview_stage else None,
        }

        cached = await get_cached_tool_result("rejection_analysis", sanitized_payload)
        if cached:
            result = cached
        else:
            agent = RejectionAnalyzerAgent()
            result = await agent.analyze(
                **{k: v for k, v in sanitized_payload.items() if k != "tool"},
                user_api_key=user_api_key,
                model=preferred_model,
            llm_provider=llm_provider,
            )
            await cache_tool_result("rejection_analysis", sanitized_payload, result)

        logger.info('Generated rejection analysis for user %s', sanitize_log_value(user_id))
        
        return RejectionAnalysisResponse(
            analysis_summary=result.get("analysis_summary", ""),
            likely_reasons=result.get("likely_reasons", []),
            improvement_suggestions=result.get("improvement_suggestions", []),
            positive_signals=result.get("positive_signals", []),
            follow_up_recommended=result.get("follow_up_recommended", False),
            follow_up_template=result.get("follow_up_template"),
            encouragement=result.get("encouragement", "Keep going!"),
            generated_at=result.get("generated_at", datetime.now(timezone.utc).isoformat()),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Failed to analyze rejection: %s', sanitize_log_value(e), exc_info=True)
        raise internal_error("Failed to analyze rejection")


# =============================================================================
# API ENDPOINTS - REFERENCE REQUEST
# =============================================================================


@router.post("/reference-request", response_model=ReferenceRequestResponse)
async def generate_reference_request(
    request: ReferenceRequestRequest,
    response: Response,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> ReferenceRequestResponse:
    """
    Generate a professional email requesting someone to be a job reference.
    
    Creates a polite, professional request that respects the reference's time.
    
    Args:
        request: Reference request with relationship details
        current_user: Authenticated user from JWT
        db: Database session
        
    Returns:
        ReferenceRequestResponse with generated email and tips
        
    Raises:
        HTTPException: 429 if rate limited
    """
    try:
        user_id = _get_user_uuid(current_user)
        
        # Rate limiting with headers
        rate_headers = await _check_rate_limit_and_get_headers(user_id, "reference_request")
        for header, value in rate_headers.items():
            response.headers[header] = value

        # Check API key availability
        if not await _check_api_key_available(db, user_id):
            raise no_api_key_error()
        
        # Get user's name from current_user if not provided
        user_name = request.user_name or current_user.get("full_name", "")
        
        # Get user API key for BYOK
        from utils.llm_preferences import load_preferred_model
        llm_ctx = await _resolve_llm(db, user_id)
        user_api_key = llm_ctx.user_api_key
        llm_provider = llm_ctx.provider
        preferred_model = await load_preferred_model(
            db, user_id, user_api_key, has_credentials=True
        )

        sanitized_payload = {
            "tool": "reference_request",
            "reference_name": sanitize_text(request.reference_name),
            "reference_relationship": sanitize_text(request.reference_relationship),
            "reference_company": sanitize_text(request.reference_company) if request.reference_company else None,
            "years_worked_together": request.years_worked_together,
            "target_job_title": sanitize_text(request.target_job_title) if request.target_job_title else None,
            "target_company": sanitize_text(request.target_company) if request.target_company else None,
            "key_accomplishments": [sanitize_text(a) for a in request.key_accomplishments] if request.key_accomplishments else None,
            "time_since_contact": sanitize_text(request.time_since_contact) if request.time_since_contact else None,
            "user_name": sanitize_text(user_name) if user_name else None,
        }

        cached = await get_cached_tool_result("reference_request", sanitized_payload)
        if cached:
            result = cached
        else:
            agent = ReferenceRequestWriterAgent()
            result = await agent.generate(
                **{k: v for k, v in sanitized_payload.items() if k != "tool"},
                user_api_key=user_api_key,
                model=preferred_model,
            llm_provider=llm_provider,
            )
            await cache_tool_result("reference_request", sanitized_payload, result)

        logger.info('Generated reference request for user %s', sanitize_log_value(user_id))
        
        return ReferenceRequestResponse(
            subject_line=result.get("subject_line", ""),
            email_body=result.get("email_body", ""),
            talking_points=result.get("talking_points", []),
            follow_up_timeline=result.get("follow_up_timeline", "Follow up in 1 week"),
            tips=result.get("tips", []),
            generated_at=result.get("generated_at", datetime.now(timezone.utc).isoformat()),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Failed to generate reference request: %s', sanitize_log_value(e), exc_info=True)
        raise internal_error("Failed to generate reference request")


# =============================================================================
# REQUEST/RESPONSE MODELS - JOB COMPARISON
# =============================================================================


class JobInput(BaseModel):
    """Model for a single job in comparison."""
    
    title: str = Field(..., min_length=1, max_length=200, description="Job title")
    company: str = Field(..., min_length=1, max_length=200, description="Company name")
    location: Optional[str] = Field(None, max_length=200, description="Job location")
    salary: Optional[str] = Field(None, max_length=100, description="Salary range")
    job_type: Optional[str] = Field("Full-time", description="Job type")
    remote_policy: Optional[str] = Field(None, description="Remote work policy")
    description: Optional[str] = Field(None, max_length=5000, description="Job description")


class UserContext(BaseModel):
    """User context for job comparison."""
    
    career_goals: Optional[str] = Field(None, max_length=500, description="Career goals")
    priorities: Optional[str] = Field(None, max_length=500, description="Top priorities")
    experience_years: Optional[int] = Field(None, ge=0, le=50, description="Years of experience")
    work_style: Optional[str] = Field(None, description="Preferred work style")
    location_preference: Optional[str] = Field(None, description="Location preference")
    salary_expectations: Optional[str] = Field(None, description="Salary expectations")


class JobComparisonRequest(BaseModel):
    """Request model for job comparison."""
    
    jobs: List[JobInput] = Field(
        ..., min_length=2, max_length=3, description="2-3 jobs to compare"
    )
    user_context: Optional[UserContext] = Field(None, description="User context for personalized comparison")


class JobAnalysis(BaseModel):
    """Analysis of a single job."""
    
    job_identifier: str
    title: str
    company: str
    overall_score: int = Field(..., ge=0, le=100)
    scores: Dict[str, int]
    pros: List[str]
    cons: List[str]
    ideal_for: str
    concerns: List[str]


class DecisionFactor(BaseModel):
    """A factor in the decision."""
    
    factor: str
    importance: str
    winner: str
    explanation: str


class JobComparisonResponse(BaseModel):
    """Response model for job comparison."""
    
    executive_summary: str = Field(..., description="Summary of comparison")
    recommended_job: str = Field(..., description="Recommended job or 'No clear winner'")
    recommendation_confidence: str = Field(..., description="Confidence level")
    recommendation_reasoning: str = Field(..., description="Why this job is recommended")
    jobs_analysis: List[JobAnalysis] = Field(default_factory=list)
    comparison_matrix: Dict[str, str] = Field(default_factory=dict)
    decision_factors: List[DecisionFactor] = Field(default_factory=list)
    questions_to_ask: List[str] = Field(default_factory=list)
    final_advice: str = Field(..., description="Final advice")
    jobs_compared: int = Field(..., description="Number of jobs compared")
    generated_at: str = Field(..., description="Generation timestamp")


# =============================================================================
# REQUEST/RESPONSE MODELS - FOLLOW-UP GENERATOR
# =============================================================================


class FollowUpStage(str, Enum):
    """Valid follow-up stages — validated at the API boundary."""

    AFTER_APPLICATION = "after_application"
    AFTER_PHONE_SCREEN = "after_phone_screen"
    AFTER_INTERVIEW = "after_interview"
    AFTER_FINAL_ROUND = "after_final_round"
    NO_RESPONSE = "no_response"
    AFTER_REJECTION = "after_rejection"
    AFTER_OFFER = "after_offer"


class FollowUpRequest(BaseModel):
    """Request model for follow-up email generation."""

    stage: FollowUpStage = Field(
        ...,
        description="Follow-up stage",
    )
    company_name: str = Field(..., min_length=1, max_length=200, description="Company name")
    job_title: str = Field(..., min_length=1, max_length=200, description="Job title")
    contact_name: Optional[str] = Field(None, max_length=100, description="Contact person's name")
    contact_role: Optional[str] = Field(None, max_length=100, description="Contact person's role")
    days_since_contact: Optional[int] = Field(None, ge=0, le=365, description="Days since last contact")
    previous_interactions: Optional[str] = Field(None, max_length=500, description="Previous interactions")
    key_points: Optional[List[str]] = Field(None, description="Key points to mention")
    user_name: Optional[str] = Field(None, max_length=100, description="Your name")


class FollowUpResponse(BaseModel):
    """Response model for follow-up email generation."""
    
    subject_line: str = Field(..., description="Email subject line")
    email_body: str = Field(..., description="Full email body")
    key_elements: List[str] = Field(default_factory=list, description="Key elements of the email")
    tone: str = Field(..., description="Tone of the email")
    timing_advice: str = Field(..., description="Best time to send")
    next_steps: str = Field(..., description="What to do if no response")
    alternative_subject: str = Field(..., description="Alternative subject line")
    stage: str = Field(..., description="Follow-up stage")
    generated_at: str = Field(..., description="Generation timestamp")


class FollowUpStagesResponse(BaseModel):
    """Response model for available follow-up stages."""
    
    stages: List[Dict[str, str]] = Field(..., description="Available stages with descriptions")


# =============================================================================
# REQUEST/RESPONSE MODELS - SALARY COACH
# =============================================================================


class SalaryCoachRequest(BaseModel):
    """Request model for salary negotiation coaching."""
    
    job_title: str = Field(..., min_length=1, max_length=200, description="Job title")
    company_name: str = Field(..., min_length=1, max_length=200, description="Company name")
    offered_salary: str = Field(..., min_length=1, max_length=100, description="Offered salary")
    years_experience: Optional[int] = Field(None, ge=0, le=50, description="Years of experience (auto-filled from profile if not provided)")
    additional_context: Optional[str] = Field(None, max_length=2000, description="Additional context (target salary, achievements, other offers, etc.)")
    location: Optional[str] = Field(None, max_length=200, description="Job location")
    company_size: Optional[str] = Field(None, description="Company size (startup, mid-size, enterprise)")
    industry: Optional[str] = Field(None, max_length=100, description="Industry")
    offered_benefits: Optional[str] = Field(None, max_length=500, description="Offered benefits")
    current_salary: Optional[str] = Field(None, max_length=100, description="Current/previous salary")
    achievements: Optional[List[str]] = Field(None, description="Key achievements")
    unique_value: Optional[List[str]] = Field(None, description="Unique value propositions")
    other_offers: Optional[str] = Field(None, max_length=500, description="Other offers/leverage")
    urgency: Optional[str] = Field(None, description="Timeline urgency")
    target_range: Optional[str] = Field(None, max_length=100, description="Target salary range")
    market_info: Optional[str] = Field(None, max_length=500, description="Market rate information")
    priority_areas: Optional[List[str]] = Field(None, description="Priority negotiation areas")
    flexibility_areas: Optional[List[str]] = Field(None, description="Areas of flexibility")
    non_negotiables: Optional[List[str]] = Field(None, description="Non-negotiables")
    style_preference: Optional[str] = Field(None, description="Negotiation style preference")


class MarketAnalysis(BaseModel):
    """Market analysis section of salary coaching."""
    
    salary_assessment: str
    market_position: str
    recommended_target: str
    negotiation_room: str
    leverage_assessment: str


class StrategyOverview(BaseModel):
    """Strategy overview section."""
    
    approach: str
    key_messages: List[str]
    timing_recommendation: str
    confidence_level: str


class MainScript(BaseModel):
    """Main negotiation script."""
    
    opening: str
    value_statement: str
    counter_offer: str
    closing: str


class PushbackResponse(BaseModel):
    """Response to a pushback scenario."""
    
    scenario: str
    response_script: str
    key_points: List[str]


class AlternativeAsk(BaseModel):
    """Alternative item to negotiate."""
    
    item: str
    value: str
    script: str
    likelihood: str


class EmailTemplate(BaseModel):
    """Email template for written negotiation."""
    
    subject: str
    body: str


class DosAndDonts(BaseModel):
    """Dos and don'ts for negotiation."""
    
    dos: List[str]
    donts: List[str]


class SalaryCoachResponse(BaseModel):
    """Response model for salary negotiation coaching."""
    
    market_analysis: MarketAnalysis
    strategy_overview: StrategyOverview
    main_script: MainScript
    pushback_responses: List[PushbackResponse] = Field(default_factory=list)
    alternative_asks: List[AlternativeAsk] = Field(default_factory=list)
    email_template: EmailTemplate
    dos_and_donts: DosAndDonts
    red_flags: List[str] = Field(default_factory=list)
    walk_away_point: str = Field(..., description="When to walk away")
    final_tips: List[str] = Field(default_factory=list)
    job_title: str
    company_name: str
    offered_salary: str
    generated_at: str = Field(..., description="Generation timestamp")


# =============================================================================
# API ENDPOINTS - JOB COMPARISON
# =============================================================================


@router.post("/job-comparison", response_model=JobComparisonResponse)
async def compare_jobs(
    request: JobComparisonRequest,
    response: Response,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> JobComparisonResponse:
    """
    Compare 2-3 job opportunities side-by-side.
    
    Provides detailed analysis and recommendation based on user priorities.
    
    Args:
        request: Job comparison request with jobs and optional user context
        current_user: Authenticated user from JWT
        db: Database session
        
    Returns:
        JobComparisonResponse with analysis and recommendation
        
    Raises:
        HTTPException: 400 if invalid input, 429 if rate limited
    """
    try:
        user_id = _get_user_uuid(current_user)
        
        # Rate limiting with headers
        rate_headers = await _check_rate_limit_and_get_headers(user_id, "job_comparison")
        for header, value in rate_headers.items():
            response.headers[header] = value

        # Check API key availability
        if not await _check_api_key_available(db, user_id):
            raise no_api_key_error()
        
        # Get user API key for BYOK
        from utils.llm_preferences import load_preferred_model
        llm_ctx = await _resolve_llm(db, user_id)
        user_api_key = llm_ctx.user_api_key
        llm_provider = llm_ctx.provider
        preferred_model = await load_preferred_model(
            db, user_id, user_api_key, has_credentials=True
        )
        
        # Prepare jobs data
        jobs_data = []
        for job in request.jobs:
            jobs_data.append({
                "title": sanitize_text(job.title),
                "company": sanitize_text(job.company),
                "location": sanitize_text(job.location) if job.location else None,
                "salary": sanitize_text(job.salary) if job.salary else None,
                "job_type": sanitize_text(job.job_type) if job.job_type else "Full-time",
                "remote_policy": sanitize_text(job.remote_policy) if job.remote_policy else None,
                "description": sanitize_text(job.description) if job.description else None,
            })
        
        # Prepare user context
        user_context = None
        if request.user_context:
            ctx = request.user_context
            user_context = {
                "career_goals": sanitize_text(ctx.career_goals) if ctx.career_goals else None,
                "priorities": sanitize_text(ctx.priorities) if ctx.priorities else None,
                "experience_years": ctx.experience_years,
                "work_style": sanitize_text(ctx.work_style) if ctx.work_style else None,
                "location_preference": sanitize_text(ctx.location_preference) if ctx.location_preference else None,
                "salary_expectations": sanitize_text(ctx.salary_expectations) if ctx.salary_expectations else None,
            }
        
        sanitized_payload = {"tool": "job_comparison", "jobs": jobs_data, "user_context": user_context}
        cached = await get_cached_tool_result("job_comparison", sanitized_payload)
        if cached:
            result = cached
        else:
            agent = JobComparisonAgent()
            result = await agent.compare(
                jobs=jobs_data,
                user_context=user_context,
                user_api_key=user_api_key,
                model=preferred_model,
            llm_provider=llm_provider,
            )
            await cache_tool_result("job_comparison", sanitized_payload, result)

        logger.info('Generated job comparison for user %s', sanitize_log_value(user_id))
        
        # Build response with proper type handling
        jobs_analysis = []
        for analysis in result.get("jobs_analysis", []):
            jobs_analysis.append(JobAnalysis(
                job_identifier=analysis.get("job_identifier", ""),
                title=analysis.get("title", ""),
                company=analysis.get("company", ""),
                overall_score=analysis.get("overall_score", 0),
                scores=analysis.get("scores", {}),
                pros=analysis.get("pros", []),
                cons=analysis.get("cons", []),
                ideal_for=analysis.get("ideal_for", ""),
                concerns=analysis.get("concerns", []),
            ))
        
        decision_factors = []
        for factor in result.get("decision_factors", []):
            decision_factors.append(DecisionFactor(
                factor=factor.get("factor", ""),
                importance=factor.get("importance", "medium"),
                winner=factor.get("winner", ""),
                explanation=factor.get("explanation", ""),
            ))
        
        return JobComparisonResponse(
            executive_summary=result.get("executive_summary", ""),
            recommended_job=result.get("recommended_job", "No clear winner"),
            recommendation_confidence=result.get("recommendation_confidence", "medium"),
            recommendation_reasoning=result.get("recommendation_reasoning", ""),
            jobs_analysis=jobs_analysis,
            comparison_matrix=result.get("comparison_matrix", {}),
            decision_factors=decision_factors,
            questions_to_ask=result.get("questions_to_ask", []),
            final_advice=result.get("final_advice", ""),
            jobs_compared=result.get("jobs_compared", len(request.jobs)),
            generated_at=result.get("generated_at", datetime.now(timezone.utc).isoformat()),
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        raise validation_error(str(e))
    except Exception as e:
        logger.error('Failed to compare jobs: %s', sanitize_log_value(e), exc_info=True)
        raise internal_error("Failed to compare jobs")


# =============================================================================
# API ENDPOINTS - FOLLOW-UP GENERATOR
# =============================================================================


@router.get("/followup-stages", response_model=FollowUpStagesResponse)
async def get_followup_stages(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> FollowUpStagesResponse:
    """
    Get available follow-up stages with descriptions.
    
    Returns:
        List of available stages
    """
    stages = FollowUpGeneratorAgent.get_available_stages()
    return FollowUpStagesResponse(stages=stages)


@router.post("/followup", response_model=FollowUpResponse)
async def generate_followup(
    request: FollowUpRequest,
    response: Response,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> FollowUpResponse:
    """
    Generate a follow-up email for a specific stage of the job application process.
    
    Args:
        request: Follow-up request with stage and context
        current_user: Authenticated user from JWT
        db: Database session
        
    Returns:
        FollowUpResponse with generated email
        
    Raises:
        HTTPException: 400 if invalid stage, 429 if rate limited
    """
    try:
        user_id = _get_user_uuid(current_user)
        
        # Rate limiting with headers
        rate_headers = await _check_rate_limit_and_get_headers(user_id, "followup")
        for header, value in rate_headers.items():
            response.headers[header] = value
        
        # Check API key availability
        if not await _check_api_key_available(db, user_id):
            raise no_api_key_error()
        
        # Get user API key for BYOK
        from utils.llm_preferences import load_preferred_model
        llm_ctx = await _resolve_llm(db, user_id)
        user_api_key = llm_ctx.user_api_key
        llm_provider = llm_ctx.provider
        preferred_model = await load_preferred_model(
            db, user_id, user_api_key, has_credentials=True
        )
        
        # Get user's name from current_user if not provided
        user_name = request.user_name or current_user.get("full_name", "")
        
        sanitized_payload = {
            "tool": "followup",
            "stage": request.stage.value,
            "company_name": sanitize_text(request.company_name),
            "job_title": sanitize_text(request.job_title),
            "contact_name": sanitize_text(request.contact_name) if request.contact_name else None,
            "contact_role": sanitize_text(request.contact_role) if request.contact_role else None,
            "days_since_contact": request.days_since_contact,
            "previous_interactions": sanitize_text(request.previous_interactions) if request.previous_interactions else None,
            "key_points": [sanitize_text(p) for p in request.key_points] if request.key_points else None,
            "user_name": sanitize_text(user_name) if user_name else None,
        }

        cached = await get_cached_tool_result("followup", sanitized_payload)
        if cached:
            result = cached
        else:
            agent = FollowUpGeneratorAgent()
            result = await agent.generate(
                **{k: v for k, v in sanitized_payload.items() if k != "tool"},
                user_api_key=user_api_key,
                model=preferred_model,
            llm_provider=llm_provider,
            )
            await cache_tool_result("followup", sanitized_payload, result)

        logger.info(
            "Generated follow-up email for user %s, stage: %s",
            sanitize_log_value(user_id),
            sanitize_log_value(request.stage),
        )
        
        return FollowUpResponse(
            subject_line=result.get("subject_line", ""),
            email_body=result.get("email_body", ""),
            key_elements=result.get("key_elements", []),
            tone=result.get("tone", "professional"),
            timing_advice=result.get("timing_advice", ""),
            next_steps=result.get("next_steps", ""),
            alternative_subject=result.get("alternative_subject", ""),
            stage=result.get("stage", request.stage.value),
            generated_at=result.get("generated_at", datetime.now(timezone.utc).isoformat()),
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        raise validation_error(str(e))
    except Exception as e:
        logger.error('Failed to generate follow-up: %s', sanitize_log_value(e), exc_info=True)
        raise internal_error("Failed to generate follow-up email")


# =============================================================================
# API ENDPOINTS - SALARY COACH
# =============================================================================


@router.post("/salary-coach", response_model=SalaryCoachResponse)
async def get_salary_coaching(
    request: SalaryCoachRequest,
    response: Response,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> SalaryCoachResponse:
    """
    Generate comprehensive salary negotiation strategy and scripts.
    
    Provides personalized negotiation guidance based on offer details,
    candidate profile, and market conditions.
    
    Args:
        request: Salary coaching request with offer and profile details
        current_user: Authenticated user from JWT
        db: Database session
        
    Returns:
        SalaryCoachResponse with strategy and scripts
        
    Raises:
        HTTPException: 429 if rate limited
    """
    try:
        user_id = _get_user_uuid(current_user)
        
        # Rate limiting with headers (fewer per hour due to complexity)
        rate_headers = await _check_rate_limit_and_get_headers(user_id, "salary_coach", limit=5)
        for header, value in rate_headers.items():
            response.headers[header] = value
        
        # Check API key availability
        if not await _check_api_key_available(db, user_id):
            raise no_api_key_error()
        
        # Get user API key for BYOK
        from utils.llm_preferences import load_preferred_model
        llm_ctx = await _resolve_llm(db, user_id)
        user_api_key = llm_ctx.user_api_key
        llm_provider = llm_ctx.provider
        preferred_model = await load_preferred_model(
            db, user_id, user_api_key, has_credentials=True
        )
        
        # Get years_experience from profile if not provided
        years_experience = request.years_experience
        if years_experience is None:
            from models.database import UserProfile
            from sqlalchemy import select
            result_profile = await db.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = result_profile.scalar_one_or_none()
            if profile and profile.years_experience is not None:
                years_experience = profile.years_experience
        
        sanitized_payload = {
            "tool": "salary_coach",
            "job_title": sanitize_text(request.job_title),
            "company_name": sanitize_text(request.company_name),
            "offered_salary": sanitize_text(request.offered_salary),
            "years_experience": years_experience,
            "additional_context": sanitize_text(request.additional_context) if request.additional_context else None,
            "location": sanitize_text(request.location) if request.location else None,
            "company_size": sanitize_text(request.company_size) if request.company_size else None,
            "industry": sanitize_text(request.industry) if request.industry else None,
            "offered_benefits": sanitize_text(request.offered_benefits) if request.offered_benefits else None,
            "current_salary": sanitize_text(request.current_salary) if request.current_salary else None,
            "achievements": [sanitize_text(a) for a in request.achievements] if request.achievements else None,
            "unique_value": [sanitize_text(v) for v in request.unique_value] if request.unique_value else None,
            "other_offers": sanitize_text(request.other_offers) if request.other_offers else None,
            "urgency": sanitize_text(request.urgency) if request.urgency else None,
            "target_range": sanitize_text(request.target_range) if request.target_range else None,
            "market_info": sanitize_text(request.market_info) if request.market_info else None,
            "priority_areas": [sanitize_text(p) for p in request.priority_areas] if request.priority_areas else None,
            "flexibility_areas": [sanitize_text(f) for f in request.flexibility_areas] if request.flexibility_areas else None,
            "non_negotiables": [sanitize_text(n) for n in request.non_negotiables] if request.non_negotiables else None,
            "style_preference": sanitize_text(request.style_preference) if request.style_preference else None,
        }

        cached = await get_cached_tool_result("salary_coach", sanitized_payload)
        if cached:
            result = cached
        else:
            agent = SalaryCoachAgent()
            result = await agent.generate_strategy(
                **{k: v for k, v in sanitized_payload.items() if k != "tool"},
                user_api_key=user_api_key,
                model=preferred_model,
            llm_provider=llm_provider,
            )
            await cache_tool_result("salary_coach", sanitized_payload, result)

        logger.info('Generated salary coaching for user %s', sanitize_log_value(user_id))
        
        # Build response with proper type handling
        market_analysis = result.get("market_analysis", {})
        strategy_overview = result.get("strategy_overview", {})
        main_script = result.get("main_script", {})
        email_template = result.get("email_template", {})
        dos_and_donts = result.get("dos_and_donts", {"dos": [], "donts": []})
        
        pushback_responses = []
        for pb in result.get("pushback_responses", []):
            pushback_responses.append(PushbackResponse(
                scenario=pb.get("scenario", ""),
                response_script=pb.get("response_script", ""),
                key_points=pb.get("key_points", []),
            ))
        
        alternative_asks = []
        for alt in result.get("alternative_asks", []):
            alternative_asks.append(AlternativeAsk(
                item=alt.get("item", ""),
                value=alt.get("value", ""),
                script=alt.get("script", ""),
                likelihood=alt.get("likelihood", "medium"),
            ))
        
        return SalaryCoachResponse(
            market_analysis=MarketAnalysis(
                salary_assessment=market_analysis.get("salary_assessment", ""),
                market_position=market_analysis.get("market_position", ""),
                recommended_target=market_analysis.get("recommended_target", ""),
                negotiation_room=market_analysis.get("negotiation_room", ""),
                leverage_assessment=market_analysis.get("leverage_assessment", ""),
            ),
            strategy_overview=StrategyOverview(
                approach=strategy_overview.get("approach", ""),
                key_messages=strategy_overview.get("key_messages", []),
                timing_recommendation=strategy_overview.get("timing_recommendation", ""),
                confidence_level=strategy_overview.get("confidence_level", "medium"),
            ),
            main_script=MainScript(
                opening=main_script.get("opening", ""),
                value_statement=main_script.get("value_statement", ""),
                counter_offer=main_script.get("counter_offer", ""),
                closing=main_script.get("closing", ""),
            ),
            pushback_responses=pushback_responses,
            alternative_asks=alternative_asks,
            email_template=EmailTemplate(
                subject=email_template.get("subject", ""),
                body=email_template.get("body", ""),
            ),
            dos_and_donts=DosAndDonts(
                dos=dos_and_donts.get("dos", []),
                donts=dos_and_donts.get("donts", []),
            ),
            red_flags=result.get("red_flags", []),
            walk_away_point=result.get("walk_away_point", ""),
            final_tips=result.get("final_tips", []),
            job_title=result.get("job_title", request.job_title),
            company_name=result.get("company_name", request.company_name),
            offered_salary=result.get("offered_salary", request.offered_salary),
            generated_at=result.get("generated_at", datetime.now(timezone.utc).isoformat()),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Failed to generate salary coaching: %s', sanitize_log_value(e), exc_info=True)
        raise internal_error("Failed to generate salary negotiation strategy")
