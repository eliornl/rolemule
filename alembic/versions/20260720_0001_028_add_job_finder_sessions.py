"""Add job_finder_sessions table.

Revision ID: 20260720_028
Revises: 20260715_027
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260720_028"
down_revision = "20260715_027"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    bind = op.get_bind()
    return set(inspect(bind).get_table_names())


def upgrade() -> None:
    if "job_finder_sessions" in _tables():
        return
    op.create_table(
        "job_finder_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("confirmed_filters", JSONB, nullable=True),
        sa.Column("messages", JSONB, nullable=True),
        sa.Column("last_board", JSONB, nullable=True),
        sa.Column("last_listings", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_job_finder_sessions_user_status",
        "job_finder_sessions",
        ["user_id", "status"],
    )


def downgrade() -> None:
    if "job_finder_sessions" not in _tables():
        return
    op.drop_index("ix_job_finder_sessions_user_status", table_name="job_finder_sessions")
    op.drop_table("job_finder_sessions")
