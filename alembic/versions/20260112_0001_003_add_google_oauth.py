"""Add google_id column to users table for Google OAuth.

Revision ID: 003
Revises: 002
Create Date: 2026-01-12

This migration adds Google OAuth support by adding a google_id column
to store the unique Google account identifier for OAuth users.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Add google_id column to users table with unique constraint and index."""
    op.add_column(
        "users",
        sa.Column("google_id", sa.String(255), nullable=True),
    )
    # Add unique constraint for google_id
    op.create_unique_constraint("uq_users_google_id", "users", ["google_id"])
    # Add index for faster lookups by google_id
    op.create_index("ix_users_google_id", "users", ["google_id"])


def downgrade() -> None:
    """Remove google_id column and its constraints from users table."""
    op.drop_index("ix_users_google_id", table_name="users")
    op.drop_constraint("uq_users_google_id", "users", type_="unique")
    op.drop_column("users", "google_id")
