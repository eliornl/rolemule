"""Set users.profile_completed when the profile matches POST /complete rules.

Revision ID: 20260429_020
Revises: 20260429_019
Create Date: 2026-04-29

Context
-------
Revisions 016–018 add ``education`` and backfill ``[]`` so the *education step*
is satisfied the same way as work experience (non-NULL ``[]`` = step saved).
019 clears cached ``GET /profile`` JSON.

Problem
-------
``users.profile_completed`` can stay ``FALSE`` for legacy accounts who already
had **basic info, work experience, skills, and career preferences** in good
shape, but never re-ran ``POST /profile/complete`` after the new education
column existed. The ``[]`` backfill fixes the *education* gap in data; this
revision fixes the **User** flag when the row now passes the **same five
checks** as ``POST /complete`` (we cannot detect “only education was ever
wrong” in SQL after the fact, so we require **all** checks—if skills or work
are still incomplete, we do not flip the flag).

Solution
--------
For each user with ``profile_completed = FALSE``, evaluate profile columns via
**raw SQL** (not the live ORM — the ``User`` / ``UserProfile`` models may have
columns added in later revisions). Require basic info, work experience, skills,
career preferences (pre-work_authorization rules), and education.

Then clear the user_profile Redis cache again so JWT and cached payloads align.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import sqlalchemy as sa
from alembic import op

revision = "20260429_020"
down_revision = "20260429_019"
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


def _career_ok_pre_work_auth(p: SimpleNamespace) -> bool:
    """Career step rules as of this revision (before work_authorization)."""
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
            WHERE u.profile_completed = false
            """
        )
    ).mappings().all()

    now = datetime.now(timezone.utc)
    for row in rows:
        prof = SimpleNamespace(**dict(row))
        if not (
            _basic_ok(prof)
            and _work_ok(prof)
            and _skills_ok(prof)
            and _career_ok_pre_work_auth(prof)
            and _education_ok(prof)
        ):
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
