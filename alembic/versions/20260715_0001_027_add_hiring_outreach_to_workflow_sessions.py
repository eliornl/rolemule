"""Add hiring_outreach JSONB to workflow_sessions.

Revision ID: 20260715_027
Revises: 20260714_026
Create Date: 2026-07-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260715_027"
down_revision = "20260714_026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_sessions",
        sa.Column("hiring_outreach", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workflow_sessions", "hiring_outreach")
