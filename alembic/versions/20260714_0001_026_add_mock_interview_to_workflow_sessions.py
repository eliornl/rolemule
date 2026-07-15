"""Add mock_interview JSONB to workflow_sessions.

Revision ID: 20260714_026
Revises: 20260713_025
Create Date: 2026-07-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260714_026"
down_revision = "20260713_025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_sessions",
        sa.Column("mock_interview", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workflow_sessions", "mock_interview")
