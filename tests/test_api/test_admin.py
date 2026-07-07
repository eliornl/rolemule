"""
Integration tests for api/admin.py — maintenance, metrics, scheduler cleanup.
"""

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from config.settings import get_settings
from main import app
from models.database import JobApplication, User, WorkflowSession
from tests.test_api.conftest import _NullSessionLocal
from utils.auth import get_current_user, require_admin


@pytest_asyncio.fixture
async def admin_client(api_client):
    """Authenticated client with is_admin=True."""
    uid = str(uuid.uuid4())
    admin_user = {
        "id": uid,
        "email": f"admin_{uid[:8]}@example.com",
        "full_name": "Admin",
        "auth_method": "local",
        "profile_completed": True,
        "is_admin": True,
    }

    async def _admin():
        return admin_user

    app.dependency_overrides[get_current_user] = _admin
    app.dependency_overrides[require_admin] = _admin
    try:
        yield api_client
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(require_admin, None)


@pytest.fixture
async def non_admin_client(authed_client):
    """Regular user — admin endpoints must return 403."""
    return authed_client


BASE = "/api/v1/admin"


class TestAdminMaintenance:
    """Maintenance mode admin endpoints."""

    @pytest.mark.asyncio
    async def test_get_maintenance_requires_admin(self, non_admin_client):
        resp = await non_admin_client.get(f"{BASE}/maintenance")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_get_maintenance_status(self, admin_client):
        with patch(
            "api.admin.get_maintenance_info",
            AsyncMock(return_value={"enabled": False, "message": None, "estimated_end": None}),
        ):
            resp = await admin_client.get(f"{BASE}/maintenance")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    @pytest.mark.asyncio
    async def test_get_maintenance_internal_error(self, admin_client):
        with patch("api.admin.get_maintenance_info", AsyncMock(side_effect=RuntimeError("redis"))):
            resp = await admin_client.get(f"{BASE}/maintenance")
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_enable_maintenance(self, admin_client):
        with (
            patch("api.admin.enable_maintenance_mode", AsyncMock(return_value=True)),
            patch(
                "api.admin.get_maintenance_info",
                AsyncMock(return_value={"enabled": True, "message": "Upgrade", "estimated_end": "1h"}),
            ),
        ):
            resp = await admin_client.post(
                f"{BASE}/maintenance",
                json={"enabled": True, "message": "Upgrade", "estimated_end": "1h"},
            )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    @pytest.mark.asyncio
    async def test_enable_maintenance_redis_failure(self, admin_client):
        with patch("api.admin.enable_maintenance_mode", AsyncMock(return_value=False)):
            resp = await admin_client.post(
                f"{BASE}/maintenance",
                json={"enabled": True, "message": "Down"},
            )
        assert resp.status_code == 500
        assert resp.json().get("error_code") == "INT_9001"

    @pytest.mark.asyncio
    async def test_disable_maintenance(self, admin_client):
        with (
            patch("api.admin.disable_maintenance_mode", AsyncMock(return_value=True)),
            patch(
                "api.admin.get_maintenance_info",
                AsyncMock(return_value={"enabled": False, "message": None, "estimated_end": None}),
            ),
        ):
            resp = await admin_client.post(f"{BASE}/maintenance", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    @pytest.mark.asyncio
    async def test_delete_maintenance(self, admin_client):
        with patch("api.admin.disable_maintenance_mode", AsyncMock(return_value=True)):
            resp = await admin_client.delete(f"{BASE}/maintenance")
        assert resp.status_code == 200
        assert "disabled" in resp.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_delete_maintenance_failure(self, admin_client):
        with patch("api.admin.disable_maintenance_mode", AsyncMock(return_value=False)):
            resp = await admin_client.delete(f"{BASE}/maintenance")
        assert resp.status_code == 500
        assert resp.json().get("error_code") == "INT_9001"


class TestAdminMetrics:
    """GET /admin/metrics"""

    @pytest.mark.asyncio
    async def test_metrics_requires_admin(self, non_admin_client):
        resp = await non_admin_client.get(f"{BASE}/metrics")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_metrics_returns_aggregate_counts(self, admin_client):
        uid = uuid.uuid4()
        async with _NullSessionLocal() as db:
            db.add(
                User(
                    id=uid,
                    email=f"metrics_{uid.hex[:8]}@example.com",
                    password_hash="$2b$12$placeholder",
                    auth_method="local",
                    full_name="Metrics User",
                    email_verified=True,
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
                )
            )
            await db.commit()

        try:
            resp = await admin_client.get(f"{BASE}/metrics")
            assert resp.status_code == 200
            data = resp.json()
            assert "users" in data
            assert "workflows" in data
            assert "applications" in data
            assert data["workflows"]["total"] >= 1
        finally:
            async with _NullSessionLocal() as db:
                from sqlalchemy import delete

                await db.execute(delete(JobApplication).where(JobApplication.user_id == uid))
                await db.execute(delete(WorkflowSession).where(WorkflowSession.user_id == uid))
                await db.execute(delete(User).where(User.id == uid))
                await db.commit()


class TestSchedulerCleanup:
    """POST /admin/internal/cleanup/orphaned-sessions"""

    @pytest.mark.asyncio
    async def test_cleanup_unauthorized_without_secret(self, api_client):
        resp = await api_client.post(f"{BASE}/internal/cleanup/orphaned-sessions")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_cleanup_wrong_secret(self, api_client):
        settings = get_settings()
        with patch.object(settings, "cloud_scheduler_secret", "expected-secret"):
            resp = await api_client.post(
                f"{BASE}/internal/cleanup/orphaned-sessions",
                headers={"X-Scheduler-Secret": "wrong"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_cleanup_success(self, api_client):
        settings = get_settings()
        secret = "test-scheduler-secret"
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        @asynccontextmanager
        async def _fake_session():
            yield mock_db

        with (
            patch.object(settings, "cloud_scheduler_secret", secret),
            patch("api.admin.get_session", _fake_session),
        ):
            resp = await api_client.post(
                f"{BASE}/internal/cleanup/orphaned-sessions",
                headers={"X-Scheduler-Secret": secret},
            )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_cleanup_db_failure_returns_500(self, api_client):
        settings = get_settings()
        secret = "test-scheduler-secret-fail"

        @asynccontextmanager
        async def _failing_session():
            raise RuntimeError("db unavailable")
            yield  # pragma: no cover

        with (
            patch.object(settings, "cloud_scheduler_secret", secret),
            patch("api.admin.get_session", _failing_session),
        ):
            resp = await api_client.post(
                f"{BASE}/internal/cleanup/orphaned-sessions",
                headers={"X-Scheduler-Secret": secret},
            )
        assert resp.status_code == 500
        assert resp.json().get("error_code") == "INT_9001"

    @pytest.mark.asyncio
    async def test_cleanup_resets_orphaned_sessions(self, api_client):
        settings = get_settings()
        secret = "test-scheduler-secret-rows"
        uid = uuid.uuid4()
        stale_sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                User(
                    id=uid,
                    email=f"orphan_{uid.hex[:8]}@example.com",
                    password_hash="$2b$12$placeholder",
                    auth_method="local",
                    full_name="Orphan User",
                )
            )
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=stale_sid,
                    user_id=uid,
                    workflow_status="in_progress",
                    processing_start_time=datetime.now(timezone.utc) - timedelta(hours=3),
                )
            )
            await db.commit()

        try:
            with patch.object(settings, "cloud_scheduler_secret", secret):
                resp = await api_client.post(
                    f"{BASE}/internal/cleanup/orphaned-sessions",
                    headers={"X-Scheduler-Secret": secret},
                )
            assert resp.status_code == 204
            async with _NullSessionLocal() as db:
                from sqlalchemy import select

                row = await db.execute(
                    select(WorkflowSession).where(WorkflowSession.session_id == stale_sid)
                )
                ws = row.scalar_one()
                assert ws.workflow_status == "failed"
                assert ws.error_messages
        finally:
            async with _NullSessionLocal() as db:
                from sqlalchemy import delete

                await db.execute(delete(WorkflowSession).where(WorkflowSession.user_id == uid))
                await db.execute(delete(User).where(User.id == uid))
                await db.commit()


class TestAdminMaintenanceErrors:
    """Exception and failure branches on maintenance endpoints."""

    @pytest.mark.asyncio
    async def test_disable_maintenance_redis_failure(self, admin_client):
        with patch("api.admin.disable_maintenance_mode", AsyncMock(return_value=False)):
            resp = await admin_client.post(f"{BASE}/maintenance", json={"enabled": False})
        assert resp.status_code == 500
        assert resp.json().get("error_code") == "INT_9001"

    @pytest.mark.asyncio
    async def test_set_maintenance_unexpected_exception(self, admin_client):
        with patch("api.admin.enable_maintenance_mode", AsyncMock(side_effect=RuntimeError("boom"))):
            resp = await admin_client.post(
                f"{BASE}/maintenance",
                json={"enabled": True, "message": "Down"},
            )
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_clear_maintenance_unexpected_exception(self, admin_client):
        with patch("api.admin.disable_maintenance_mode", AsyncMock(side_effect=RuntimeError("boom"))):
            resp = await admin_client.delete(f"{BASE}/maintenance")
        assert resp.status_code == 500


class TestAdminMetricsExtended:
    """Full metrics aggregation and error handling."""

    @pytest.mark.asyncio
    async def test_metrics_includes_user_and_workflow_breakdown(self, admin_client):
        uid = uuid.uuid4()
        now = datetime.now(timezone.utc)
        async with _NullSessionLocal() as db:
            db.add(
                User(
                    id=uid,
                    email=f"fullmetrics_{uid.hex[:8]}@example.com",
                    password_hash="$2b$12$placeholder",
                    auth_method="local",
                    full_name="Metrics Full",
                    email_verified=True,
                    created_at=now - timedelta(days=10),
                    last_login=now - timedelta(days=2),
                )
            )
            for status in ("completed", "failed", "in_progress", "initialized"):
                db.add(
                    WorkflowSession(
                        id=uuid.uuid4(),
                        session_id=str(uuid.uuid4()),
                        user_id=uid,
                        workflow_status=status,
                    )
                )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    job_title="Engineer",
                    company_name="Co",
                    created_at=now - timedelta(days=5),
                )
            )
            await db.commit()

        try:
            resp = await admin_client.get(f"{BASE}/metrics")
            assert resp.status_code == 200
            data = resp.json()
            assert data["users"]["email_verified"] >= 1
            assert data["users"]["active_last_7d"] >= 1
            assert data["users"]["new_last_30d"] >= 1
            assert data["workflows"]["total"] >= 4
            assert data["workflows"]["completed"] >= 1
            assert data["workflows"]["failed"] >= 1
            assert data["workflows"]["in_progress"] >= 1
            assert "success_rate_pct" in data["workflows"]
            assert data["applications"]["new_last_30d"] >= 1
        finally:
            async with _NullSessionLocal() as db:
                from sqlalchemy import delete

                await db.execute(delete(JobApplication).where(JobApplication.user_id == uid))
                await db.execute(delete(WorkflowSession).where(WorkflowSession.user_id == uid))
                await db.execute(delete(User).where(User.id == uid))
                await db.commit()

    @pytest.mark.asyncio
    async def test_metrics_db_failure_returns_500(self, admin_client):
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(side_effect=RuntimeError("db down"))

        from utils.database import get_database

        async def _broken_db():
            yield mock_db

        app.dependency_overrides[get_database] = _broken_db
        try:
            resp = await admin_client.get(f"{BASE}/metrics")
        finally:
            from tests.test_api.conftest import _get_null_pool_db

            app.dependency_overrides[get_database] = _get_null_pool_db

        assert resp.status_code == 500
        assert resp.json().get("error_code") == "INT_9001"
