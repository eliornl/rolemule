"""Initial schema migration - captures existing database structure.

Revision ID: 001
Revises: None
Create Date: 2026-01-02

This migration creates all tables for RoleMule:
- users: User authentication and basic identity
- user_profiles: Extended profile information with JSONB fields
- workflow_sessions: Workflow state and agent results
- job_applications: Application tracking with workflow reference
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Create all database tables."""
    
    # ==========================================================================
    # USERS TABLE
    # ==========================================================================
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("auth_method", sa.String(50), nullable=False, server_default="local"),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("profile_completed", sa.Boolean(), server_default="false"),
        sa.Column("profile_completion_percentage", sa.Integer(), server_default="0"),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # ==========================================================================
    # USER_PROFILES TABLE
    # ==========================================================================
    op.create_table(
        "user_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            unique=True,
            index=True,
        ),
        # Basic Information
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("professional_title", sa.String(200), nullable=True),
        sa.Column("years_experience", sa.Integer(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("is_student", sa.Boolean(), server_default="false"),
        # Profile Sections (JSONB)
        sa.Column("work_experience", postgresql.JSONB(), nullable=True),
        sa.Column("skills", postgresql.JSONB(), nullable=True),
        # Job Preferences (JSONB)
        sa.Column("desired_salary_range", postgresql.JSONB(), nullable=True),
        sa.Column("desired_company_sizes", postgresql.JSONB(), nullable=True),
        sa.Column("job_types", postgresql.JSONB(), nullable=True),
        sa.Column("work_arrangements", postgresql.JSONB(), nullable=True),
        sa.Column("willing_to_relocate", sa.Boolean(), server_default="false"),
        sa.Column("requires_visa_sponsorship", sa.Boolean(), server_default="false"),
        sa.Column("has_security_clearance", sa.Boolean(), server_default="false"),
        sa.Column("max_travel_preference", sa.String(50), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # ==========================================================================
    # WORKFLOW_SESSIONS TABLE
    # ==========================================================================
    op.create_table(
        "workflow_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", sa.String(36), unique=True, nullable=False, index=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            index=True,
        ),
        # Workflow Control and Status
        sa.Column("workflow_status", sa.String(50), server_default="initialized"),
        sa.Column("current_phase", sa.String(50), server_default="initialization"),
        sa.Column("current_agent", sa.String(100), nullable=True),
        # Agent Status Tracking (JSONB)
        sa.Column("agent_status", postgresql.JSONB(), nullable=True),
        sa.Column("completed_agents", postgresql.JSONB(), nullable=True),
        sa.Column("failed_agents", postgresql.JSONB(), nullable=True),
        # Error Handling (JSONB)
        sa.Column("error_messages", postgresql.JSONB(), nullable=True),
        sa.Column("warning_messages", postgresql.JSONB(), nullable=True),
        # Input Data (JSONB)
        sa.Column("job_input_data", postgresql.JSONB(), nullable=True),
        sa.Column("user_data", postgresql.JSONB(), nullable=True),
        # Agent Processing Results (JSONB)
        sa.Column("job_analysis", postgresql.JSONB(), nullable=True),
        sa.Column("company_research", postgresql.JSONB(), nullable=True),
        sa.Column("profile_matching", postgresql.JSONB(), nullable=True),
        sa.Column("resume_recommendations", postgresql.JSONB(), nullable=True),
        sa.Column("cover_letter", postgresql.JSONB(), nullable=True),
        # Timing
        sa.Column("processing_start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("agent_start_times", postgresql.JSONB(), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # Composite indexes for workflow_sessions
    op.create_index(
        "ix_workflow_user_status",
        "workflow_sessions",
        ["user_id", "workflow_status"],
    )
    op.create_index(
        "ix_workflow_user_created",
        "workflow_sessions",
        ["user_id", "created_at"],
    )

    # ==========================================================================
    # JOB_APPLICATIONS TABLE
    # ==========================================================================
    op.create_table(
        "job_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            index=True,
        ),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("workflow_sessions.session_id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        # Job Information
        sa.Column("job_title", sa.String(500), nullable=True),
        sa.Column("company_name", sa.String(500), nullable=True),
        sa.Column("job_url", sa.Text(), nullable=True),
        # Match Score
        sa.Column("match_score", sa.Float(), nullable=True),
        # Application Status Tracking
        sa.Column("status", sa.String(50), server_default="draft", index=True),
        sa.Column("applied_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_date", sa.DateTime(timezone=True), nullable=True),
        # User Notes
        sa.Column("notes", sa.Text(), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            index=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # Unique constraint for job_applications
    op.create_unique_constraint(
        "uq_user_job_company",
        "job_applications",
        ["user_id", "job_title", "company_name"],
    )

    # Composite indexes for job_applications
    op.create_index(
        "ix_job_applications_user_status",
        "job_applications",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_job_applications_user_created",
        "job_applications",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_job_applications_user_score",
        "job_applications",
        ["user_id", "match_score"],
    )


def downgrade() -> None:
    """Drop all database tables."""
    # Drop in reverse order of creation (respecting foreign key constraints)
    
    # Drop indexes first
    op.drop_index("ix_job_applications_user_score", table_name="job_applications")
    op.drop_index("ix_job_applications_user_created", table_name="job_applications")
    op.drop_index("ix_job_applications_user_status", table_name="job_applications")
    op.drop_constraint("uq_user_job_company", "job_applications", type_="unique")
    
    op.drop_index("ix_workflow_user_created", table_name="workflow_sessions")
    op.drop_index("ix_workflow_user_status", table_name="workflow_sessions")
    
    # Drop tables
    op.drop_table("job_applications")
    op.drop_table("workflow_sessions")
    op.drop_table("user_profiles")
    op.drop_table("users")

