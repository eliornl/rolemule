"""
Direct-handler coverage for remaining api/admin.py gaps.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from api.admin import get_metrics
from models.database import AuthMethod, JobApplication, User, WorkflowSession
from tests.test_api.conftest import _NullSessionLocal
from utils.error_responses import APIError


class TestAdminDirectHandlers:
    @pytest.mark.asyncio
    async def test_get_metrics_direct_real_db(self) -> None:
        uid = uuid.uuid4()
        async with _NullSessionLocal() as db:
            db.add(
                User(
                    id=uid,
                    email=f"metricsd_{uid.hex[:8]}@example.com",
                    password_hash="$2b$12$placeholder",
                    auth_method=AuthMethod.LOCAL.value,
                    full_name="Metrics Direct",
                    email_verified=True,
                    last_login=datetime.now(timezone.utc),
                    created_at=datetime.now(timezone.utc) - timedelta(days=5),
                )
            )
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=str(uuid.uuid4()),
                    user_id=uid,
                    workflow_status="completed",
                )
            )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    job_title="Engineer",
                    company_name="Co",
                    created_at=datetime.now(timezone.utc) - timedelta(days=2),
                )
            )
            await db.commit()
            metrics = await get_metrics(
                current_user={"id": str(uid), "is_admin": True},
                db=db,
            )
        assert metrics.users["total"] >= 1
        assert metrics.workflows.total >= 1
        assert metrics.applications["total"] >= 1
        assert metrics.workflows.success_rate_pct >= 0
        async with _NullSessionLocal() as db:
            from sqlalchemy import delete

            await db.execute(delete(JobApplication).where(JobApplication.user_id == uid))
            await db.execute(delete(WorkflowSession).where(WorkflowSession.user_id == uid))
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()

    @pytest.mark.asyncio
    async def test_get_metrics_internal_error(self) -> None:
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(side_effect=RuntimeError("db fail"))
        with pytest.raises(APIError) as exc:
            await get_metrics(current_user={"id": "admin", "is_admin": True}, db=mock_db)
        assert exc.value.status_code == 500
