"""Add mock_interview JSONB to workflow_sessions.

Revision ID: 20260714_026
Revises: 20260713_025
Create Date: 2026-07-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260714_026"
down_revision = "20260713_025"
branch_labels = None
depends_on = None


def _workflow_session_columns() -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns("workflow_sessions")}


def upgrade() -> None:
    # Idempotent: local DBs may already have the column from an earlier apply
    # that did not stamp alembic_version.
    if "mock_interview" not in _workflow_session_columns():
        op.add_column(
            "workflow_sessions",
            sa.Column("mock_interview", JSONB, nullable=True),
        )


def downgrade() -> None:
    if "mock_interview" in _workflow_session_columns():
        op.drop_column("workflow_sessions", "mock_interview")
