"""Add personal_access_tokens table for CLI PAT auth.

Revision ID: 20260708_024
Revises: 20260609_023
Create Date: 2026-07-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260708_024"
down_revision = "20260609_023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personal_access_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("token_prefix", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_personal_access_tokens_user_id",
        "personal_access_tokens",
        ["user_id"],
    )
    op.create_index(
        "ix_personal_access_tokens_token_hash",
        "personal_access_tokens",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_personal_access_tokens_token_hash", table_name="personal_access_tokens")
    op.drop_index("ix_personal_access_tokens_user_id", table_name="personal_access_tokens")
    op.drop_table("personal_access_tokens")
