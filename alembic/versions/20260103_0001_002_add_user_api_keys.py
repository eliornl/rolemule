"""Add gemini_api_key_encrypted column to users table.

Revision ID: 002
Revises: 001
Create Date: 2026-01-03

This migration adds support for per-user API keys (BYOK - Bring Your Own Key).
Users can now store their own encrypted Gemini API key for LLM operations.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Add gemini_api_key_encrypted column to users table."""
    op.add_column(
        "users",
        sa.Column("gemini_api_key_encrypted", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove gemini_api_key_encrypted column from users table."""
    op.drop_column("users", "gemini_api_key_encrypted")



