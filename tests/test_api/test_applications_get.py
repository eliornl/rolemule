"""Integration tests for GET /api/v1/applications/{id}."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import jwt
import pytest
from sqlalchemy import delete

from config.settings import get_security_settings
from main import app
from models.database import ApplicationStatus, JobApplication, WorkflowSession
from tests.test_api.conftest import _NullSessionLocal
from utils.auth import get_current_user_with_complete_profile

BASE = "/api/v1/applications"


def _user_id_from_client_headers(headers: dict) -> uuid.UUID:
    token = headers["Authorization"].split(" ", 1)[1]
    sec = get_security_settings()
    payload = jwt.decode(
        token,
        sec.jwt_config["secret_key"],
        algorithms=[sec.jwt_config["algorithm"]],
    )
    return uuid.UUID(payload["sub"])


async def _seed_application(
    user_id: uuid.UUID,
    *,
    workflow_status: str = "completed",
) -> uuid.UUID:
    app_id = uuid.uuid4()
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    async with _NullSessionLocal() as session:
        session.add(
            JobApplication(
                id=app_id,
                user_id=user_id,
                session_id=session_id,
                job_title="Backend Engineer",
                company_name="Acme Corp",
                status=ApplicationStatus.COMPLETED.value,
                match_score=0.82,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            WorkflowSession(
                session_id=session_id,
                user_id=user_id,
                workflow_status=workflow_status,
                job_analysis={"job_title": "Backend Engineer", "company_name": "Acme Corp"},
            )
        )
        await session.commit()
    return app_id


async def _cleanup_user_apps(user_id: uuid.UUID) -> None:
    async with _NullSessionLocal() as session:
        await session.execute(delete(WorkflowSession).where(WorkflowSession.user_id == user_id))
        await session.execute(delete(JobApplication).where(JobApplication.user_id == user_id))
        await session.commit()


@pytest.fixture
def complete_profile_override(authed_client_with_user):
    """Mark the authed_client_with_user as profile-complete for guarded endpoints."""
    original = app.dependency_overrides[get_current_user_with_complete_profile]

    async def _complete_user():
        user = await original()
        return {**user, "profile_completed": True}

    app.dependency_overrides[get_current_user_with_complete_profile] = _complete_user
    yield
    app.dependency_overrides[get_current_user_with_complete_profile] = original


class TestGetApplication:
    """GET /api/v1/applications/{application_id}."""

    @pytest.mark.asyncio
    async def test_get_requires_auth(self, api_client) -> None:
        resp = await api_client.get(f"{BASE}/{uuid.uuid4()}")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_get_invalid_uuid_returns_422(self, authed_client) -> None:
        resp = await authed_client.get(f"{BASE}/not-a-uuid")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_not_found(self, authed_client) -> None:
        resp = await authed_client.get(f"{BASE}/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_success(self, authed_client_with_user, complete_profile_override) -> None:
        user_id = _user_id_from_client_headers(authed_client_with_user.headers)
        app_id = await _seed_application(user_id)
        try:
            resp = await authed_client_with_user.get(f"{BASE}/{app_id}")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["id"] == str(app_id)
            assert body["job_title"] == "Backend Engineer"
            assert body["company_name"] == "Acme Corp"
            assert body["workflow_session_id"]
        finally:
            await _cleanup_user_apps(user_id)

    @pytest.mark.asyncio
    async def test_get_hides_workflow_failed(self, authed_client_with_user, complete_profile_override) -> None:
        user_id = _user_id_from_client_headers(authed_client_with_user.headers)
        app_id = await _seed_application(user_id, workflow_status="failed")
        try:
            resp = await authed_client_with_user.get(f"{BASE}/{app_id}")
            assert resp.status_code == 404
        finally:
            await _cleanup_user_apps(user_id)
