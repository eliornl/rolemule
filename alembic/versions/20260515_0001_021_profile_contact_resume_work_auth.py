"""Add profile contact URLs, phone, work_authorization, and user resume assets.

Revision ID: 20260515_021
Revises: 20260429_020
Create Date: 2026-05-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "20260515_021"
down_revision: Union[str, None] = "20260429_020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Alembic reads these module-level identifiers; reference satisfies static analysis.
_ALEMBIC_METADATA = (revision, down_revision, branch_labels, depends_on)


def _profile_columns() -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns("user_profiles")}


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in inspect(bind).get_table_names()


def upgrade() -> None:
    cols = _profile_columns()

    if "phone" not in cols:
        op.add_column(
            "user_profiles",
            sa.Column("phone", sa.String(length=40), nullable=True),
        )
    if "linkedin_url" not in cols:
        op.add_column(
            "user_profiles",
            sa.Column("linkedin_url", sa.String(length=500), nullable=True),
        )
    if "github_url" not in cols:
        op.add_column(
            "user_profiles",
            sa.Column("github_url", sa.String(length=500), nullable=True),
        )
    if "portfolio_url" not in cols:
        op.add_column(
            "user_profiles",
            sa.Column("portfolio_url", sa.String(length=500), nullable=True),
        )
    if "work_authorization" not in cols:
        op.add_column(
            "user_profiles",
            sa.Column(
                "work_authorization",
                sa.String(length=40),
                nullable=True,
            ),
        )

    if not _table_exists("user_resume_assets"):
        op.create_table(
            "user_resume_assets",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("storage_relative_path", sa.String(length=512), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("mime_type", sa.String(length=100), nullable=False),
            sa.Column("byte_size", sa.BigInteger(), nullable=False),
            sa.Column("sha256_hex", sa.String(length=64), nullable=True),
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
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", name="uq_user_resume_assets_user_id"),
        )


def downgrade() -> None:
    if _table_exists("user_resume_assets"):
        op.drop_table("user_resume_assets")

    cols = _profile_columns()
    if "work_authorization" in cols:
        op.drop_column("user_profiles", "work_authorization")
    for col in ("portfolio_url", "github_url", "linkedin_url", "phone"):
        if col in cols:
            op.drop_column("user_profiles", col)
