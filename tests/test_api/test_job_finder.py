"""
Integration tests for Job Finder API endpoints.

Endpoints:
  POST   /api/v1/job-finder/sessions
  GET    /api/v1/job-finder/sessions/active
  GET    /api/v1/job-finder/sessions/{session_id}
  POST   /api/v1/job-finder/sessions/{session_id}/messages
  POST   /api/v1/job-finder/sessions/{session_id}/careers-url
  POST   /api/v1/job-finder/sessions/{session_id}/select
  DELETE /api/v1/job-finder/sessions/{session_id}
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
import pytest_asyncio
from sqlalchemy import text, update

from config.settings import get_security_settings
from models.database import JobFinderSession, User, UserProfile
from tests.test_api.conftest import _NullSessionLocal
from utils.cache import RateLimitResult

BASE = "/api/v1/job-finder"


@pytest_asyncio.fixture(autouse=True, scope="module")
async def ensure_job_finder_sessions_table():
    """Ensure migration 028 table exists (local DB may lag behind model)."""
    async with _NullSessionLocal() as db:
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS job_finder_sessions (
                    id UUID PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    status VARCHAR(32) NOT NULL DEFAULT 'active',
                    confirmed_filters JSONB,
                    messages JSONB,
                    last_board JSONB,
                    last_listings JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_job_finder_sessions_user_status "
                "ON job_finder_sessions (user_id, status)"
            )
        )
        await db.commit()


async def _uid_from_client(client) -> uuid.UUID:
    token = client.headers["Authorization"].split(" ", 1)[1]
    sec = get_security_settings()
    payload = jwt.decode(
        token,
        sec.jwt_config["secret_key"],
        algorithms=[sec.jwt_config["algorithm"]],
    )
    return uuid.UUID(payload["sub"])


async def _ensure_profile(client) -> uuid.UUID:
    uid = await _uid_from_client(client)
    async with _NullSessionLocal() as db:
        await db.execute(
            update(User).where(User.id == uid).values(profile_completed=True)
        )
        existing = await db.execute(
            text("SELECT 1 FROM user_profiles WHERE user_id = :uid"),
            {"uid": uid},
        )
        if existing.scalar_one_or_none() is None:
            db.add(
                UserProfile(
                    id=uuid.uuid4(),
                    user_id=uid,
                    professional_title="Engineer",
                    years_experience=5,
                    summary="Job finder test profile.",
                    city="Austin",
                    state="TX",
                    country="US",
                )
            )
        await db.commit()
    return uid


def _llm_ctx_mock():
    return type(
        "Ctx",
        (),
        {
            "user_api_key": "test-key",
            "provider": "gemini",
            "preferred_model": None,
        },
    )()


async def _create_session(client) -> str:
    with patch(
        "api.job_finder.require_user_llm_context",
        AsyncMock(return_value=(MagicMock(), _llm_ctx_mock(), None)),
    ):
        resp = await client.post(f"{BASE}/sessions")
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Auth + session creation
# ---------------------------------------------------------------------------


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_requires_auth(self, api_client):
        resp = await api_client.post(f"{BASE}/sessions")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_create_session_success(self, authed_client):
        await _ensure_profile(authed_client)
        session_id = await _create_session(authed_client)
        assert session_id

    @pytest.mark.asyncio
    async def test_no_api_key_returns_cfg_6001(self, authed_client):
        from utils.error_responses import no_api_key_error

        await _ensure_profile(authed_client)
        with patch(
            "api.job_finder.require_user_llm_context",
            AsyncMock(side_effect=no_api_key_error()),
        ):
            resp = await authed_client.post(f"{BASE}/sessions")
        assert resp.status_code == 422
        assert resp.json().get("error_code") == "CFG_6001"


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------


class TestSessionOwnership:
    @pytest.mark.asyncio
    async def test_get_foreign_session_returns_404(self, authed_client):
        await _ensure_profile(authed_client)
        foreign = str(uuid.uuid4())
        resp = await authed_client.get(f"{BASE}/sessions/{foreign}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_post_message_foreign_session_returns_404(self, authed_client):
        await _ensure_profile(authed_client)
        foreign = str(uuid.uuid4())
        with patch(
            "api.job_finder.require_user_llm_context",
            AsyncMock(return_value=(MagicMock(), _llm_ctx_mock(), None)),
        ):
            resp = await authed_client.post(
                f"{BASE}/sessions/{foreign}/messages",
                json={"content": "hello"},
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestJobFinderRateLimit:
    @pytest.mark.asyncio
    async def test_message_rate_limited_returns_429(self, authed_client):
        await _ensure_profile(authed_client)
        session_id = await _create_session(authed_client)
        blocked = RateLimitResult(
            allowed=False,
            limit=30,
            remaining=0,
            reset_seconds=3600,
        )
        with patch(
            "api.job_finder.require_user_llm_context",
            AsyncMock(return_value=(MagicMock(), _llm_ctx_mock(), None)),
        ), patch(
            "api.job_finder.check_rate_limit_with_headers",
            AsyncMock(return_value=blocked),
        ):
            resp = await authed_client.post(
                f"{BASE}/sessions/{session_id}/messages",
                json={"content": "Acme"},
            )
        assert resp.status_code == 429
        assert resp.json().get("error_code") == "RATE_4001"


# ---------------------------------------------------------------------------
# Select jobs
# ---------------------------------------------------------------------------


class TestSelectJobs:
    @pytest.mark.asyncio
    async def test_select_starts_workflow_for_listing(self, authed_client):
        uid = await _ensure_profile(authed_client)
        session_id = await _create_session(authed_client)
        job_id = "greenhouse:101"
        listing = {
            "id": job_id,
            "title": "Software Engineer",
            "company": "Acme",
            "location": "Remote",
            "url": "https://boards.greenhouse.io/acme/jobs/101",
            "provider": "greenhouse",
            "description_text": "Build APIs with Python and PostgreSQL for cloud services.",
        }

        async with _NullSessionLocal() as db:
            row = await db.get(JobFinderSession, uuid.UUID(session_id))
            assert row is not None
            row.last_listings = [listing]
            await db.commit()

        workflow_out = {
            "application_id": str(uuid.uuid4()),
            "session_id": str(uuid.uuid4()),
        }
        with patch(
            "api.job_finder.require_user_llm_context",
            AsyncMock(return_value=(MagicMock(), _llm_ctx_mock(), None)),
        ), patch(
            "api.job_finder.start_workflow_from_job_finder",
            AsyncMock(return_value=workflow_out),
        ):
            resp = await authed_client.post(
                f"{BASE}/sessions/{session_id}/select",
                json={"job_ids": [job_id]},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["started"] == 1
        assert data["failed"] == 0
        assert data["results"][0]["ok"] is True
        assert data["results"][0]["application_id"] == workflow_out["application_id"]

        async with _NullSessionLocal() as db:
            row = await db.get(JobFinderSession, uuid.UUID(session_id))
            assert row is not None
            assert row.user_id == uid

    @pytest.mark.asyncio
    async def test_select_unknown_job_id_returns_partial_failure(self, authed_client):
        await _ensure_profile(authed_client)
        session_id = await _create_session(authed_client)
        missing_id = "greenhouse:missing"

        with patch(
            "api.job_finder.require_user_llm_context",
            AsyncMock(return_value=(MagicMock(), _llm_ctx_mock(), None)),
        ):
            resp = await authed_client.post(
                f"{BASE}/sessions/{session_id}/select",
                json={"job_ids": [missing_id]},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["started"] == 0
        assert data["failed"] == 1
        assert data["results"][0]["error_code"] == "VAL_2001"

    @pytest.mark.asyncio
    async def test_select_foreign_session_returns_404(self, authed_client):
        await _ensure_profile(authed_client)
        foreign = str(uuid.uuid4())
        with patch(
            "api.job_finder.require_user_llm_context",
            AsyncMock(return_value=(MagicMock(), _llm_ctx_mock(), None)),
        ):
            resp = await authed_client.post(
                f"{BASE}/sessions/{foreign}/select",
                json={"job_ids": ["greenhouse:1"]},
            )
        assert resp.status_code == 404
