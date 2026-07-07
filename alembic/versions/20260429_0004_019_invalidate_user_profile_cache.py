"""Invalidate Redis user_profile cache after education backfills.

Revision ID: 20260429_019
Revises: 20260429_018
Create Date: 2026-04-29

SQL migrations that change ``user_profiles`` do not go through the profile API,
so per-user ``invalidate_user_profile`` never runs. Clear all cached
``GET /api/v1/profile`` responses so completion_status matches the database.

Best-effort: if Redis is down, upgrade still succeeds (see
``invalidate_all_user_profile_caches_sync``).
"""


revision = "20260429_019"
down_revision = "20260429_018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from utils.cache import invalidate_all_user_profile_caches_sync

    invalidate_all_user_profile_caches_sync()


def downgrade() -> None:
    pass
