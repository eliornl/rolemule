"""Keep profile_completed at 100% for users who finished setup before work_authorization.

Revision ID: 20260518_022
Revises: 20260515_021
Create Date: 2026-05-18

Does not set work_authorization — only restores users.profile_completed and
profile_completion_percentage for accounts that already completed profile setup
under the old rules. New users must still answer work_authorization on Step 5.
"""

from datetime import datetime, timezone

from alembic import op
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

revision = "20260518_022"
down_revision = "20260515_021"
branch_labels = None
depends_on = None


def _career_preferences_complete_legacy(prof) -> bool:
    """Career step complete under rules before work_authorization was required."""
    return (
        len(prof.desired_company_sizes or []) > 0
        and len(prof.job_types or []) > 0
        and len(prof.work_arrangements or []) > 0
    )


def _restore_completion_for_existing_users(session: Session) -> None:
    from api.profile import (
        _check_basic_info_completion,
        _check_education_completion,
        _check_skills_qualifications_completion,
        _check_work_experience_completion,
    )
    from models.database import User, UserProfile as UserProfileModel

    users = session.scalars(select(User)).all()
    now = datetime.now(timezone.utc)
    for user in users:
        prof = session.scalar(
            select(UserProfileModel).where(UserProfileModel.user_id == user.id)
        )
        if prof is None:
            continue

        was_marked_complete = bool(user.profile_completed)
        legacy_complete = (
            _check_basic_info_completion(prof)
            and _check_work_experience_completion(prof)
            and _check_education_completion(prof)
            and _check_skills_qualifications_completion(prof)
            and _career_preferences_complete_legacy(prof)
        )
        if not (was_marked_complete or legacy_complete):
            continue

        user.profile_completed = True
        user.profile_completion_percentage = 100
        user.updated_at = now

    session.commit()


def upgrade() -> None:
    bind = op.get_bind()
    SessionLocal = sessionmaker(bind=bind, class_=Session, autoflush=False)
    session = SessionLocal()
    try:
        _restore_completion_for_existing_users(session)
        from utils.cache import invalidate_all_user_profile_caches_sync

        invalidate_all_user_profile_caches_sync()
    finally:
        session.close()


def downgrade() -> None:
    pass
