"""
Database models for the ApplyPilot.
Defines PostgreSQL table schemas using SQLAlchemy ORM with async support.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum

from sqlalchemy import (
    String,
    Boolean,
    Integer,
    BigInteger,
    Float,
    DateTime,
    Text,
    ForeignKey,
    Index,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)
from sqlalchemy.sql import func


# =============================================================================
# ENUMS
# =============================================================================


class AuthMethod(str, Enum):
    """Authentication method types."""

    LOCAL = "local"
    GOOGLE = "google"


class ApplicationStatus(str, Enum):
    """Job application status types."""

    DRAFT = "draft"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    APPLIED = "applied"
    INTERVIEW = "interview"
    REJECTED = "rejected"
    ACCEPTED = "accepted"


class WorkflowStatusEnum(str, Enum):
    """Workflow status types for database."""

    INITIALIZED = "initialized"
    IN_PROGRESS = "in_progress"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    ANALYSIS_COMPLETE = "analysis_complete"
    COMPLETED = "completed"
    FAILED = "failed"


# =============================================================================
# BASE MODEL
# =============================================================================


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


# =============================================================================
# MODELS
# =============================================================================


class User(Base):
    """
    User account model - Authentication and basic identity only.

    Stores authentication credentials and basic user information.
    Extended profile data is stored in the UserProfile table.

    Indexes:
        - email (unique): Fast user lookup by email for authentication
    """

    __tablename__ = "users"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Authentication Fields
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    auth_method: Mapped[str] = mapped_column(
        String(50), nullable=False, default=AuthMethod.LOCAL.value
    )

    # User Information
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    profile_completion_percentage: Mapped[int] = mapped_column(Integer, default=0)
    
    # Admin Role
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    # Email Verification
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # OAuth Fields
    google_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    
    # API Keys (encrypted BYOK — one column per cloud provider)
    gemini_api_key_encrypted: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None
    )
    openai_api_key_encrypted: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None
    )
    anthropic_api_key_encrypted: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None
    )

    # Timestamps
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "(auth_method != 'local') OR (password_hash IS NOT NULL)",
            name="ck_users_local_auth_has_password",
        ),
    )

    # Relationships with proper cascade
    # Use lazy="noload" for collections to prevent N+1 queries - load explicitly when needed
    profile: Mapped[Optional["UserProfile"]] = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    applications: Mapped[List["JobApplication"]] = relationship(
        "JobApplication",
        back_populates="user",
        lazy="noload",
        cascade="all, delete-orphan",
    )
    workflow_sessions: Mapped[List["WorkflowSession"]] = relationship(
        "WorkflowSession",
        back_populates="user",
        lazy="noload",
        cascade="all, delete-orphan",
    )
    workflow_preferences: Mapped[Optional["UserWorkflowPreferences"]] = relationship(
        "UserWorkflowPreferences",
        back_populates="user",
        uselist=False,
        lazy="noload",
        cascade="all, delete-orphan",
    )
    resume_asset: Mapped[Optional["UserResumeAsset"]] = relationship(
        "UserResumeAsset",
        back_populates="user",
        uselist=False,
        lazy="noload",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary for API responses."""
        return {
            "id": str(self.id),
            "email": self.email,
            "auth_method": self.auth_method,
            "full_name": self.full_name,
            "is_admin": self.is_admin,
            "email_verified": self.email_verified,
            "profile_completed": self.profile_completed,
            "profile_completion_percentage": self.profile_completion_percentage,
            "has_gemini_api_key": self.gemini_api_key_encrypted is not None,
            "has_openai_api_key": self.openai_api_key_encrypted is not None,
            "has_anthropic_api_key": self.anthropic_api_key_encrypted is not None,
            "has_google_linked": self.google_id is not None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PersonalAccessToken(Base):
    """Long-lived personal access token for CLI and automation (hashed at rest)."""

    __tablename__ = "personal_access_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UserProfile(Base):
    """
    Extended user profile information.

    Stores detailed profile data including work experience, skills,
    and job preferences. Uses JSONB for flexible nested data.

    Indexes:
        - user_id (unique): One-to-one relationship with User
    """

    __tablename__ = "user_profiles"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Foreign Key to User
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )

    # Basic Information
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    professional_title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    years_experience: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_student: Mapped[bool] = mapped_column(Boolean, default=False)

    # Contact & application links (autofill, employer forms)
    phone: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    github_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    portfolio_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Profile Sections (JSONB for flexibility) - use None as default, not mutable objects
    work_experience: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True, default=None
    )
    education: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True, default=None
    )
    skills: Mapped[Optional[List[str]]] = mapped_column(
        JSONB, nullable=True, default=None
    )

    # Job Preferences (JSONB for flexibility)
    desired_salary_range: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, default=None
    )
    desired_company_sizes: Mapped[Optional[List[str]]] = mapped_column(
        JSONB, nullable=True, default=None
    )
    job_types: Mapped[Optional[List[str]]] = mapped_column(
        JSONB, nullable=True, default=None
    )
    work_arrangements: Mapped[Optional[List[str]]] = mapped_column(
        JSONB, nullable=True, default=None
    )
    willing_to_relocate: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_visa_sponsorship: Mapped[bool] = mapped_column(Boolean, default=False)
    work_authorization: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True, default=None
    )
    has_security_clearance: Mapped[bool] = mapped_column(Boolean, default=False)
    max_travel_preference: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="profile")

    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to dictionary for API responses."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "city": self.city,
            "state": self.state,
            "country": self.country,
            "professional_title": self.professional_title,
            "years_experience": self.years_experience,
            "summary": self.summary,
            "is_student": self.is_student,
            "phone": self.phone,
            "linkedin_url": self.linkedin_url,
            "github_url": self.github_url,
            "portfolio_url": self.portfolio_url,
            "work_experience": self.work_experience or [],
            "education": self.education or [],
            "skills": self.skills or [],
            "desired_salary_range": self.desired_salary_range or {},
            "desired_company_sizes": self.desired_company_sizes or [],
            "job_types": self.job_types or [],
            "work_arrangements": self.work_arrangements or [],
            "willing_to_relocate": self.willing_to_relocate,
            "requires_visa_sponsorship": self.requires_visa_sponsorship,
            "work_authorization": self.work_authorization,
            "has_security_clearance": self.has_security_clearance,
            "max_travel_preference": self.max_travel_preference,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class UserResumeAsset(Base):
    """
    Stored resume file metadata (binary on disk or object storage path).

    One row per user (replaced on re-upload).
    """

    __tablename__ = "user_resume_assets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    storage_relative_path: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256_hex: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="resume_asset")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "original_filename": self.original_filename,
            "mime_type": self.mime_type,
            "byte_size": self.byte_size,
            "sha256_hex": self.sha256_hex,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class UserWorkflowPreferences(Base):
    """
    Per-user workflow behaviour preferences.

    1-to-1 with the User table (unique user_id). Rows are created on first
    PATCH; if no row exists the application falls back to column defaults.

    Indexes:
        - user_id (unique): direct lookup by user
    """

    __tablename__ = "user_workflow_preferences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    # Match-score threshold (0.0–1.0) below which the workflow pauses for
    # user confirmation before continuing with document generation.
    workflow_gate_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5
    )

    # When True, resume advice + cover letter are generated automatically
    # after company research.  When False (default), they are generated
    # on demand via POST /workflow/{session_id}/generate-documents.
    auto_generate_documents: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Tone used by the cover letter writer agent.
    # Values: 'professional' | 'conversational' | 'enthusiastic'
    cover_letter_tone: Mapped[str] = mapped_column(
        String(32), nullable=False, default="professional"
    )

    # How detailed the resume advice should be.
    # Values: 'concise' | 'detailed'
    resume_length: Mapped[str] = mapped_column(
        String(16), nullable=False, default="concise"
    )

    # Preferred model for the user's chosen provider.
    # NULL means "use the system default for that provider".
    preferred_model: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, default=None
    )

    # Required per-user LLM provider (gemini|openai|anthropic|ollama).
    # NULL means the user has not configured AI yet → CFG_6001.
    preferred_provider: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, default=None
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="workflow_preferences")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses and workflow injection."""
        return {
            "workflow_gate_threshold": self.workflow_gate_threshold,
            "auto_generate_documents": self.auto_generate_documents,
            "cover_letter_tone": self.cover_letter_tone,
            "resume_length": self.resume_length,
            "preferred_model": self.preferred_model,
            "preferred_provider": self.preferred_provider,
        }


class WorkflowSession(Base):
    """
    Workflow processing session.

    Stores the state and results of a job application workflow,
    including all agent outputs. Uses JSONB for complex nested data.

    Indexes:
        - session_id (unique): Fast lookup by session identifier
        - user_id: Filter sessions by user
        - ix_workflow_user_status: Composite for filtering user's sessions by status
        - ix_workflow_user_created: Composite for listing user's recent sessions
    """

    __tablename__ = "workflow_sessions"

    # Primary Key - using session_id as the main identifier
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, index=True
    )

    # Foreign Key to User
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # Workflow Control and Status
    workflow_status: Mapped[str] = mapped_column(
        String(50), default=WorkflowStatusEnum.INITIALIZED.value
    )
    current_phase: Mapped[str] = mapped_column(String(50), default="initialization")
    current_agent: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Agent Status Tracking (JSONB) - use None as default
    agent_status: Mapped[Optional[Dict[str, str]]] = mapped_column(
        JSONB, nullable=True, default=None
    )
    completed_agents: Mapped[Optional[List[str]]] = mapped_column(
        JSONB, nullable=True, default=None
    )
    failed_agents: Mapped[Optional[List[str]]] = mapped_column(
        JSONB, nullable=True, default=None
    )

    # Error Handling (JSONB)
    error_messages: Mapped[Optional[List[str]]] = mapped_column(
        JSONB, nullable=True, default=None
    )
    warning_messages: Mapped[Optional[List[str]]] = mapped_column(
        JSONB, nullable=True, default=None
    )

    # Input Data (JSONB)
    job_input_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, default=None
    )
    user_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, default=None
    )

    # Agent Processing Results (JSONB for complex nested data)
    job_analysis: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, default=None
    )
    company_research: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, default=None
    )
    profile_matching: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, default=None
    )
    resume_recommendations: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, default=None
    )
    cover_letter: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, default=None
    )
    
    # Interview Prep (generated on-demand after workflow completion)
    interview_prep: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, default=None
    )

    # CV Optimization Loop (generated on-demand after workflow completion)
    cv_optimization: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, default=None
    )

    # Conversational mock interview practice (on-demand; HR / Pro / Manager)
    mock_interview: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, default=None
    )

    # Hiring outreach — public-web contact finder + drafts (on-demand; no LinkedIn)
    hiring_outreach: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, default=None
    )

    # Timing - Use proper DateTime instead of String for time-based queries
    processing_start_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_end_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    agent_start_times: Mapped[Optional[Dict[str, str]]] = mapped_column(
        JSONB, nullable=True, default=None
    )
    agent_durations: Mapped[Optional[Dict[str, float]]] = mapped_column(
        JSONB, nullable=True, default=None
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="workflow_sessions")
    application: Mapped[Optional["JobApplication"]] = relationship(
        "JobApplication", back_populates="workflow_session", uselist=False
    )

    # Composite Indexes for common query patterns
    __table_args__ = (
        # For filtering user's sessions by status (e.g., "show my in-progress workflows")
        Index("ix_workflow_user_status", "user_id", "workflow_status"),
        # For listing user's recent sessions ordered by time
        Index("ix_workflow_user_created", "user_id", "created_at"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert workflow session to dictionary for API responses."""
        return {
            "id": str(self.id),
            "session_id": self.session_id,
            "user_id": str(self.user_id),
            "workflow_status": self.workflow_status,
            "current_phase": self.current_phase,
            "current_agent": self.current_agent,
            "agent_status": self.agent_status or {},
            "completed_agents": self.completed_agents or [],
            "failed_agents": self.failed_agents or [],
            "error_messages": self.error_messages or [],
            "warning_messages": self.warning_messages or [],
            "job_input_data": self.job_input_data or {},
            "user_data": self.user_data or {},
            "job_analysis": self.job_analysis or {},
            "company_research": self.company_research or {},
            "profile_matching": self.profile_matching or {},
            "resume_recommendations": self.resume_recommendations or {},
            "cover_letter": self.cover_letter or {},
            "interview_prep": self.interview_prep or {},
            "cv_optimization": self.cv_optimization or {},
            "mock_interview": self.mock_interview or {},
            "hiring_outreach": self.hiring_outreach or {},
            "processing_start_time": (
                self.processing_start_time.isoformat()
                if self.processing_start_time
                else None
            ),
            "processing_end_time": (
                self.processing_end_time.isoformat()
                if self.processing_end_time
                else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class JobApplication(Base):
    """
    Job application document.

    Stores essential job tracking information and references the workflow session
    for AI-generated content and analysis. This design reduces data duplication
    and ensures a single source of truth for workflow results.

    Indexes:
        - user_id: Filter applications by user
        - session_id: Link to workflow session
        - status: Filter by application status
        - created_at: Sort by creation date
        - ix_job_applications_user_status: Composite for user's applications by status
        - ix_job_applications_user_created: Composite for user's recent applications
    """

    __tablename__ = "job_applications"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Foreign Keys
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("workflow_sessions.session_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Job Information
    job_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    company_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    job_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # NEW: Original job posting URL

    # Match Score - store for quick access without loading full workflow
    match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # NEW: 0.0-1.0

    # Application Status Tracking
    status: Mapped[str] = mapped_column(
        String(50), default=ApplicationStatus.DRAFT.value, index=True
    )
    applied_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    response_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # User Notes - personal notes about this application
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # NEW: User's notes

    # Soft delete — set instead of hard DELETE to preserve audit history
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None, index=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="applications")
    workflow_session: Mapped[Optional["WorkflowSession"]] = relationship(
        "WorkflowSession", back_populates="application"
    )

    # Constraints and Indexes
    __table_args__ = (
        # Partial unique index — only active (non-deleted) applications are constrained,
        # so a soft-deleted slot can be reused (migration 015 swaps the old full constraint).
        UniqueConstraint(
            "user_id", "job_title", "company_name", name="uq_user_job_company"
        ),
        # For filtering user's applications by status (e.g., "show my interviews")
        Index("ix_job_applications_user_status", "user_id", "status"),
        # For listing user's recent applications
        Index("ix_job_applications_user_created", "user_id", "created_at"),
        # For filtering by match score (e.g., "show my best matches")
        Index("ix_job_applications_user_score", "user_id", "match_score"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert application to dictionary for API responses."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "session_id": self.session_id,
            "job_title": self.job_title,
            "company_name": self.company_name,
            "job_url": self.job_url,
            "match_score": self.match_score,
            "status": self.status,
            "applied_date": self.applied_date.isoformat() if self.applied_date else None,
            "response_date": (
                self.response_date.isoformat() if self.response_date else None
            ),
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def uuid_to_str(uid: uuid.UUID) -> Optional[str]:
    """Convert UUID to string safely."""
    return str(uid) if uid else None


def str_to_uuid(uid_str: str) -> Optional[uuid.UUID]:
    """Convert string to UUID safely."""
    if not uid_str:
        return None
    try:
        return uuid.UUID(uid_str)
    except (ValueError, TypeError):
        return None
