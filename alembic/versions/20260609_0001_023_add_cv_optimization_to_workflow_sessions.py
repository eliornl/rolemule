"""Add cv_optimization JSONB to workflow_sessions.

Revision ID: 20260609_023
Revises: 20260518_022
Create Date: 2026-06-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260609_023"
down_revision = "20260518_022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_sessions",
        sa.Column("cv_optimization", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workflow_sessions", "cv_optimization")
