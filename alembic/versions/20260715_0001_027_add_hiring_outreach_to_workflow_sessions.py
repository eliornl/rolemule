"""Add hiring_outreach JSONB to workflow_sessions.

Revision ID: 20260715_027
Revises: 20260714_026
Create Date: 2026-07-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260715_027"
down_revision = "20260714_026"
branch_labels = None
depends_on = None


def _workflow_session_columns() -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns("workflow_sessions")}


def upgrade() -> None:
    # Idempotent: local DBs may already have the column from an earlier apply
    # that did not stamp alembic_version.
    if "hiring_outreach" not in _workflow_session_columns():
        op.add_column(
            "workflow_sessions",
            sa.Column("hiring_outreach", JSONB, nullable=True),
        )


def downgrade() -> None:
    if "hiring_outreach" in _workflow_session_columns():
        op.drop_column("workflow_sessions", "hiring_outreach")
