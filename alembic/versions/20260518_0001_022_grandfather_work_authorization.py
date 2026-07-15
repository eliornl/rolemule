"""Keep profile_completed at 100% for users who finished setup before work_authorization.

Revision ID: 20260518_022
Revises: 20260515_021
Create Date: 2026-05-18

Does not set work_authorization — only restores users.profile_completed and
profile_completion_percentage for accounts that already completed profile setup
under the old rules. New users must still answer work_authorization on Step 5.

Uses raw SQL (not the live ORM) so later User columns (e.g. multi-provider BYOK)
do not break upgrades from an empty database.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import sqlalchemy as sa
from alembic import op

revision = "20260518_022"
down_revision = "20260515_021"
branch_labels = None
depends_on = None


def _basic_ok(p: SimpleNamespace) -> bool:
    return all(
        getattr(p, f) is not None
        for f in (
            "city",
            "state",
            "country",
            "professional_title",
            "years_experience",
            "summary",
        )
    )


def _work_ok(p: SimpleNamespace) -> bool:
    return p.work_experience is not None


def _education_ok(p: SimpleNamespace) -> bool:
    return p.education is not None


def _skills_ok(p: SimpleNamespace) -> bool:
    return len(p.skills or []) > 0


def _career_preferences_complete_legacy(p: SimpleNamespace) -> bool:
    """Career step complete under rules before work_authorization was required."""
    return (
        len(p.desired_company_sizes or []) > 0
        and len(p.job_types or []) > 0
        and len(p.work_arrangements or []) > 0
    )


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            """
            SELECT
                u.id AS user_id,
                u.profile_completed,
                p.city,
                p.state,
                p.country,
                p.professional_title,
                p.years_experience,
                p.summary,
                p.work_experience,
                p.education,
                p.skills,
                p.desired_company_sizes,
                p.job_types,
                p.work_arrangements
            FROM users AS u
            JOIN user_profiles AS p ON p.user_id = u.id
            """
        )
    ).mappings().all()

    now = datetime.now(timezone.utc)
    for row in rows:
        prof = SimpleNamespace(**dict(row))
        was_marked_complete = bool(row["profile_completed"])
        legacy_complete = (
            _basic_ok(prof)
            and _work_ok(prof)
            and _education_ok(prof)
            and _skills_ok(prof)
            and _career_preferences_complete_legacy(prof)
        )
        if not (was_marked_complete or legacy_complete):
            continue
        conn.execute(
            sa.text(
                """
                UPDATE users
                SET profile_completed = true,
                    profile_completion_percentage = 100,
                    updated_at = :now
                WHERE id = :user_id
                """
            ),
            {"now": now, "user_id": row["user_id"]},
        )

    from utils.cache import invalidate_all_user_profile_caches_sync

    invalidate_all_user_profile_caches_sync()


def downgrade() -> None:
    pass
