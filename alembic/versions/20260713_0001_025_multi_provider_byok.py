"""Add multi-provider BYOK columns and preferred_provider.

Revision ID: 20260713_025
Revises: 20260708_024
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa

revision = "20260713_025"
down_revision = "20260708_024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("openai_api_key_encrypted", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("anthropic_api_key_encrypted", sa.Text(), nullable=True),
    )
    op.add_column(
        "user_workflow_preferences",
        sa.Column("preferred_provider", sa.String(length=32), nullable=True),
    )

    # Existing Gemini BYOK users get preferred_provider=gemini
    op.execute(
        """
        UPDATE user_workflow_preferences AS p
        SET preferred_provider = 'gemini'
        FROM users AS u
        WHERE p.user_id = u.id
          AND u.gemini_api_key_encrypted IS NOT NULL
          AND p.preferred_provider IS NULL
        """
    )
    # Users with a Gemini key but no preferences row yet
    op.execute(
        """
        INSERT INTO user_workflow_preferences (
            id, user_id, workflow_gate_threshold, auto_generate_documents,
            cover_letter_tone, resume_length, preferred_provider
        )
        SELECT
            gen_random_uuid(),
            u.id,
            0.5,
            false,
            'professional',
            'concise',
            'gemini'
        FROM users AS u
        WHERE u.gemini_api_key_encrypted IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM user_workflow_preferences p WHERE p.user_id = u.id
          )
        """
    )


def downgrade() -> None:
    op.drop_column("user_workflow_preferences", "preferred_provider")
    op.drop_column("users", "anthropic_api_key_encrypted")
    op.drop_column("users", "openai_api_key_encrypted")
