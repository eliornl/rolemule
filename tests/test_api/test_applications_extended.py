"""
Extended integration tests for api/applications.py — list filters, stats, pagination,
status/notes updates, soft delete, and incomplete-profile 403 guard.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from main import app
from models.database import ApplicationStatus, AuthMethod, JobApplication, User, UserProfile, WorkflowSession
from tests.test_api.conftest import _NullSessionLocal, _make_test_jwt
from utils.auth import get_current_user, get_current_user_with_complete_profile

BASE = "/api/v1/applications"


async def _create_complete_user(
    *,
    email: Optional[str] = None,
    profile_completed: bool = True,
) -> tuple[uuid.UUID, str]:
    uid = uuid.uuid4()
    email = email or f"apps_{uid.hex[:10]}@example.com"
    async with _NullSessionLocal() as session:
        session.add(
            User(
                id=uid,
                email=email,
                password_hash="$2b$12$placeholder",
                auth_method=AuthMethod.LOCAL.value,
                full_name="Apps Test User",
                profile_completed=profile_completed,
                profile_completion_percentage=100 if profile_completed else 0,
                email_verified=True,
            )
        )
        if profile_completed:
            session.add(
                UserProfile(
                    id=uuid.uuid4(),
                    user_id=uid,
                    professional_title="Engineer",
                    years_experience=3,
                    summary="Summary text for applications tests.",
                    city="City",
                    state="ST",
                    country="US",
                )
            )
        await session.commit()
    return uid, email


async def _cleanup_user(uid: uuid.UUID) -> None:
    async with _NullSessionLocal() as session:
        await session.execute(delete(JobApplication).where(JobApplication.user_id == uid))
        await session.execute(delete(WorkflowSession).where(WorkflowSession.user_id == uid))
        await session.execute(delete(UserProfile).where(UserProfile.user_id == uid))
        await session.execute(delete(User).where(User.id == uid))
        await session.commit()


async def _seed_application(
    uid: uuid.UUID,
    *,
    job_title: str,
    company_name: str,
    status: str = ApplicationStatus.COMPLETED.value,
    created_at: Optional[datetime] = None,
    session_id: Optional[str] = None,
) -> uuid.UUID:
    app_id = uuid.uuid4()
    created_at = created_at or datetime.now(timezone.utc)
    async with _NullSessionLocal() as session:
        if session_id:
            session.add(
                WorkflowSession(
                    session_id=session_id,
                    user_id=uid,
                    workflow_status="completed",
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
        session.add(
            JobApplication(
                id=app_id,
                user_id=uid,
                session_id=session_id,
                job_title=job_title,
                company_name=company_name,
                status=status,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await session.commit()
    return app_id


async def _client_for(uid: uuid.UUID, email: str, *, profile_completed: bool = True) -> AsyncClient:
    now = datetime.now(timezone.utc)
    user_dict = {
        "id": str(uid),
        "_id": str(uid),
        "email": email,
        "full_name": "Apps Test User",
        "auth_method": "local",
        "is_admin": False,
        "profile_completed": profile_completed,
        "profile_completion_percentage": 100 if profile_completed else 0,
        "has_google_linked": False,
        "has_password": True,
        "created_at": now,
        "updated_at": now,
        "last_login": now,
    }

    async def _mock():
        return user_dict

    async def _mock_complete():
        if not profile_completed:
            from utils.error_responses import forbidden_error

            raise forbidden_error("Profile setup required")
        return user_dict

    app.dependency_overrides[get_current_user] = _mock
    app.dependency_overrides[get_current_user_with_complete_profile] = _mock_complete

    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://localhost",
        headers={"Authorization": f"Bearer {_make_test_jwt(str(uid), email)}"},
    )


def _clear_overrides() -> None:
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_with_complete_profile, None)


# ---------------------------------------------------------------------------
# Incomplete profile guard
# ---------------------------------------------------------------------------


class TestIncompleteProfileGuard:
    @pytest.mark.asyncio
    async def test_list_applications_incomplete_profile_returns_403(self):
        uid, email = await _create_complete_user(profile_completed=False)
        client = await _client_for(uid, email, profile_completed=False)
        try:
            resp = await client.get(f"{BASE}/")
            assert resp.status_code == 403
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_stats_incomplete_profile_returns_403(self):
        uid, email = await _create_complete_user(profile_completed=False)
        client = await _client_for(uid, email, profile_completed=False)
        try:
            resp = await client.get(f"{BASE}/stats/overview")
            assert resp.status_code == 403
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)


# ---------------------------------------------------------------------------
# List filters / search / pagination
# ---------------------------------------------------------------------------


class TestListApplicationsExtended:
    @pytest.mark.asyncio
    async def test_list_filters_by_status_and_search(self):
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        try:
            await _seed_application(uid, job_title="Python Engineer", company_name="Alpha Corp", status="applied")
            await _seed_application(uid, job_title="Java Developer", company_name="Beta Inc", status="completed")
            resp = await client.get(f"{BASE}/", params={"status_filter": "applied", "search": "python"})
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["total"] >= 1
            for app in body["applications"]:
                assert app["status"].lower() == "applied"
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_list_company_legacy_filter(self):
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        try:
            await _seed_application(uid, job_title="Role A", company_name="UniqueCo")
            resp = await client.get(f"{BASE}/", params={"company": "uniqueco"})
            assert resp.status_code == 200
            assert resp.json()["total"] >= 1
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_list_days_filter_excludes_old_rows(self):
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        try:
            old = datetime.now(timezone.utc) - timedelta(days=60)
            await _seed_application(uid, job_title="Old Role", company_name="OldCo", created_at=old)
            await _seed_application(uid, job_title="New Role", company_name="NewCo")
            resp = await client.get(f"{BASE}/", params={"days": 30})
            assert resp.status_code == 200
            titles = [a.get("job_title", "") for a in resp.json()["applications"]]
            assert "New Role" in titles
            assert "Old Role" not in titles
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_pagination_page_two(self):
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        try:
            for i in range(3):
                await _seed_application(uid, job_title=f"Role {i}", company_name=f"Co {i}")
            resp = await client.get(f"{BASE}/", params={"per_page": 2, "page": 2})
            assert resp.status_code == 200
            body = resp.json()
            assert body["page"] == 2
            assert body["has_prev"] is True
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_sort_company_asc(self):
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        try:
            await _seed_application(uid, job_title="A", company_name="Zebra LLC")
            await _seed_application(uid, job_title="B", company_name="Alpha LLC")
            resp = await client.get(f"{BASE}/", params={"sort": "company_asc"})
            assert resp.status_code == 200
            companies = [a.get("company_name", "") for a in resp.json()["applications"]]
            assert companies == sorted(companies, key=str.lower)
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestApplicationStats:
    @pytest.mark.asyncio
    async def test_stats_overview_counts(self):
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        try:
            await _seed_application(uid, job_title="R1", company_name="C1", status="applied")
            await _seed_application(uid, job_title="R2", company_name="C2", status="interview")
            await _seed_application(uid, job_title="R3", company_name="C3", status="completed")
            resp = await client.get(f"{BASE}/stats/overview")
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["total"] >= 3
            assert data["applied"] >= 2
            assert data["interviews"] >= 1
            assert "response_rate" in data
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)


# ---------------------------------------------------------------------------
# Status / notes / delete
# ---------------------------------------------------------------------------


class TestApplicationMutations:
    @pytest.mark.asyncio
    async def test_update_status_sets_applied_date(self):
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        try:
            app_id = await _seed_application(uid, job_title="Role", company_name="Co", status="completed")
            resp = await client.patch(
                f"{BASE}/{app_id}/status",
                json={"new_status": "applied"},
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["status"] == "applied"
            assert resp.json().get("applied_date") is not None
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_update_status_interview_sets_response_date(self):
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        try:
            app_id = await _seed_application(uid, job_title="Role", company_name="Co", status="applied")
            resp = await client.patch(
                f"{BASE}/{app_id}/status",
                json={"new_status": "interview"},
            )
            assert resp.status_code == 200
            assert resp.json().get("response_date") is not None
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_update_notes(self):
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        try:
            app_id = await _seed_application(uid, job_title="Role", company_name="Co")
            resp = await client.patch(
                f"{BASE}/{app_id}/notes",
                json={"notes": "Follow up next week."},
            )
            assert resp.status_code == 200
            assert resp.json()["notes"] == "Follow up next week."
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_update_invalid_uuid_returns_422(self):
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        try:
            resp = await client.patch(f"{BASE}/not-a-uuid/status", json={"new_status": "applied"})
            assert resp.status_code == 422
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_soft_delete_hides_from_list(self):
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        try:
            app_id = await _seed_application(uid, job_title="Delete Me", company_name="Co")
            del_resp = await client.delete(f"{BASE}/{app_id}")
            assert del_resp.status_code == 200
            list_resp = await client.get(f"{BASE}/")
            ids = [a["id"] for a in list_resp.json()["applications"]]
            assert str(app_id) not in ids
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self):
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        try:
            resp = await client.delete(f"{BASE}/{uuid.uuid4()}")
            assert resp.status_code == 404
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


class TestApplicationDownload:
    @pytest.mark.asyncio
    async def test_download_with_workflow_session(self):
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        session_id = str(uuid.uuid4())
        try:
            app_id = await _seed_application(
                uid,
                job_title="Backend Engineer",
                company_name="Acme",
                session_id=session_id,
            )
            async with _NullSessionLocal() as session:
                ws = await session.execute(
                    select(WorkflowSession).where(WorkflowSession.session_id == session_id)
                )
                row = ws.scalar_one()
                row.job_analysis = {"job_title": "Backend Engineer"}
                row.cover_letter = {"content": "Dear hiring manager"}
                await session.commit()
            resp = await client.get(f"{BASE}/{app_id}/download")
            assert resp.status_code == 200
            assert "text/plain" in resp.headers.get("content-type", "")
            assert len(resp.content) > 0
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_download_without_session_returns_404(self):
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        try:
            app_id = await _seed_application(uid, job_title="No Session", company_name="Co")
            resp = await client.get(f"{BASE}/{app_id}/download")
            assert resp.status_code == 404
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)
