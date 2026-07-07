"""Add interview_prep column to workflow_sessions table.

Revision ID: 004
Revises: 003
Create Date: 2026-01-16

This migration adds support for on-demand interview preparation materials.
The interview_prep column stores AI-generated interview prep content including
predicted questions, answer frameworks, and preparation tips.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Alembic reads these module-level identifiers; reference satisfies static analysis.
_ALEMBIC_METADATA = (revision, down_revision, branch_labels, depends_on)


def upgrade() -> None:
    """Add interview_prep JSONB column to workflow_sessions table."""
    op.add_column(
        "workflow_sessions",
        sa.Column("interview_prep", JSONB(), nullable=True),
    )


def downgrade() -> None:
    """Remove interview_prep column from workflow_sessions table."""
    op.drop_column("workflow_sessions", "interview_prep")
