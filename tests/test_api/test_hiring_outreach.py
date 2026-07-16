"""
Integration tests for Hiring Outreach API endpoints.

Endpoints:
  GET    /api/v1/hiring-outreach/{session_id}
  GET    /api/v1/hiring-outreach/{session_id}/status
  POST   /api/v1/hiring-outreach/{session_id}/generate
  DELETE /api/v1/hiring-outreach/{session_id}
"""

import uuid
import jwt
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from models.database import WorkflowSession
from config.settings import get_security_settings
from tests.test_api.conftest import _NullSessionLocal

BASE = "/api/v1/hiring-outreach"
SESSION_ID = str(uuid.uuid4())


@pytest_asyncio.fixture(autouse=True, scope="module")
async def ensure_hiring_outreach_column():
    """Ensure migration 027 column exists (local DB may lag behind model)."""
    from sqlalchemy import text

    async with _NullSessionLocal() as db:
        await db.execute(
            text(
                "ALTER TABLE workflow_sessions "
                "ADD COLUMN IF NOT EXISTS hiring_outreach JSONB"
            )
        )
        await db.commit()

SAMPLE_OUTREACH = {
    "version": "1.0",
    "contacts": [
        {
            "name": "Sarah Chen",
            "role_type": "hiring_manager",
            "likely_title": "Engineering Manager",
            "why_them": "Owns hiring for this team",
            "confidence": "high",
            "evidence": "Company team page",
            "source_hint": "company website",
            "short_message": "Hi Sarah, I applied for the role.",
            "subject_line": "Application follow-up",
            "email_body": "Hi Sarah,\n\nI recently applied.\n\nBest,",
        }
    ],
    "fallback": {"message": "Reach out via careers page"},
    "generated_at": "2026-01-01T00:00:00+00:00",
}


# ---------------------------------------------------------------------------
# GET /{session_id}
# ---------------------------------------------------------------------------


class TestGetHiringOutreach:
    """GET /api/v1/hiring-outreach/{session_id}"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.get(f"{BASE}/{SESSION_ID}")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_session_not_found_returns_404(self, authed_client):
        fake_session = str(uuid.uuid4())
        with patch(
            "api.hiring_outreach.get_cached_hiring_outreach",
            AsyncMock(return_value=None),
        ):
            resp = await authed_client.get(f"{BASE}/{fake_session}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_unowned_session_returns_404_without_reading_cache(self, authed_client):
        """Ownership is verified before cache — foreign session_id must not leak cached drafts."""
        foreign_session = str(uuid.uuid4())
        cache_mock = AsyncMock(
            return_value={
                "data": SAMPLE_OUTREACH,
                "cached_at": "2026-01-01T00:00:00+00:00",
            }
        )
        with patch("api.hiring_outreach.get_cached_hiring_outreach", cache_mock):
            resp = await authed_client.get(f"{BASE}/{foreign_session}")

        assert resp.status_code == 404
        cache_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_hit_returns_200(self, authed_client_with_user):
        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        uid = uuid.UUID(
            jwt.decode(
                token,
                sec.jwt_config["secret_key"],
                algorithms=[sec.jwt_config["algorithm"]],
            )["sub"]
        )
        session_id = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    user_id=uid,
                    workflow_status="completed",
                    job_analysis={"job_title": "Engineer", "company_name": "Co"},
                )
            )
            await db.commit()

        mock_cached = {
            "data": SAMPLE_OUTREACH,
            "cached_at": "2026-01-01T00:00:00+00:00",
        }
        with patch(
            "api.hiring_outreach.get_cached_hiring_outreach",
            AsyncMock(return_value=mock_cached),
        ):
            resp = await authed_client_with_user.get(f"{BASE}/{session_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["has_hiring_outreach"] is True
        assert data["session_id"] == session_id
        assert data["hiring_outreach"]["contacts"]


# ---------------------------------------------------------------------------
# GET /{session_id}/status
# ---------------------------------------------------------------------------


class TestHiringOutreachStatus:
    """GET /api/v1/hiring-outreach/{session_id}/status"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.get(f"{BASE}/{SESSION_ID}/status")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_session_not_found_returns_404(self, authed_client):
        fake_session = str(uuid.uuid4())
        resp = await authed_client.get(f"{BASE}/{fake_session}/status")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /{session_id}/generate
# ---------------------------------------------------------------------------


class TestGenerateHiringOutreach:
    """POST /api/v1/hiring-outreach/{session_id}/generate"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.post(f"{BASE}/{SESSION_ID}/generate")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# DELETE /{session_id}
# ---------------------------------------------------------------------------


class TestDeleteHiringOutreach:
    """DELETE /api/v1/hiring-outreach/{session_id}"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.delete(f"{BASE}/{SESSION_ID}")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_session_not_found_returns_404(self, authed_client):
        fake_session = str(uuid.uuid4())
        resp = await authed_client.delete(f"{BASE}/{fake_session}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Endpoints backed by real WorkflowSession rows
# ---------------------------------------------------------------------------


class TestHiringOutreachWithSession:
    """Generate, delete, and status with real DB sessions."""

    @pytest_asyncio.fixture
    async def session_id(self, authed_client_with_user):
        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        uid = uuid.UUID(
            jwt.decode(
                token,
                sec.jwt_config["secret_key"],
                algorithms=[sec.jwt_config["algorithm"]],
            )["sub"]
        )
        sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status="completed",
                    job_analysis={"job_title": "Engineer", "company_name": "Co"},
                )
            )
            await db.commit()
        return sid

    @pytest.mark.asyncio
    async def test_generate_missing_job_analysis_returns_422(
        self, authed_client_with_user,
    ):
        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        uid = uuid.UUID(
            jwt.decode(
                token,
                sec.jwt_config["secret_key"],
                algorithms=[sec.jwt_config["algorithm"]],
            )["sub"]
        )
        sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status="completed",
                    job_analysis=None,
                )
            )
            await db.commit()

        resp = await authed_client_with_user.post(f"{BASE}/{sid}/generate")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_generate_no_api_key_returns_cfg_6001(
        self, authed_client_with_user, session_id,
    ):
        from utils.error_responses import no_api_key_error

        with patch(
            "utils.llm_context.require_user_llm_context",
            AsyncMock(side_effect=no_api_key_error()),
        ):
            resp = await authed_client_with_user.post(
                f"{BASE}/{session_id}/generate",
            )
        assert resp.status_code == 422
        assert resp.json().get("error_code") == "CFG_6001"

    @pytest.mark.asyncio
    async def test_generate_conflict_when_already_generating(
        self, authed_client_with_user, session_id,
    ):
        llm_ctx = MagicMock(user_api_key="key", provider="gemini", ready=True)
        with (
            patch(
                "utils.llm_context.require_user_llm_context",
                AsyncMock(return_value=(MagicMock(), llm_ctx, None)),
            ),
            patch(
                "utils.llm_preferences.load_preferred_model",
                AsyncMock(return_value=None),
            ),
            patch(
                "api.hiring_outreach.set_hiring_outreach_generating",
                AsyncMock(return_value=False),
            ),
        ):
            resp = await authed_client_with_user.post(
                f"{BASE}/{session_id}/generate",
            )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_generate_already_exists_returns_exists_status(
        self, authed_client_with_user, session_id,
    ):
        async with _NullSessionLocal() as db:
            from sqlalchemy import update

            await db.execute(
                update(WorkflowSession)
                .where(WorkflowSession.session_id == session_id)
                .values(hiring_outreach=SAMPLE_OUTREACH)
            )
            await db.commit()

        rate_mock = AsyncMock(return_value=(True, 4))
        with patch("api.hiring_outreach.check_rate_limit", rate_mock):
            resp = await authed_client_with_user.post(f"{BASE}/{session_id}/generate")
        assert resp.status_code == 200
        assert resp.json()["status"] == "exists"
        rate_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_rate_limited_returns_429(
        self, authed_client_with_user, session_id,
    ):
        with patch(
            "api.hiring_outreach.check_rate_limit",
            AsyncMock(return_value=(False, 0)),
        ):
            resp = await authed_client_with_user.post(f"{BASE}/{session_id}/generate")
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_generate_happy_path_returns_generating(
        self, authed_client_with_user, session_id,
    ):
        llm_ctx = MagicMock(user_api_key="key", provider="gemini", ready=True)
        with (
            patch(
                "utils.llm_context.require_user_llm_context",
                AsyncMock(return_value=(MagicMock(), llm_ctx, None)),
            ),
            patch(
                "utils.llm_preferences.load_preferred_model",
                AsyncMock(return_value=None),
            ),
            patch(
                "api.hiring_outreach.set_hiring_outreach_generating",
                AsyncMock(return_value=True),
            ),
            patch(
                "api.hiring_outreach._generate_hiring_outreach_background",
                AsyncMock(),
            ),
        ):
            resp = await authed_client_with_user.post(
                f"{BASE}/{session_id}/generate",
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "generating"
        assert data["session_id"] == session_id

    @pytest.mark.asyncio
    async def test_generate_regenerate_invalidates_cache(
        self, authed_client_with_user, session_id,
    ):
        async with _NullSessionLocal() as db:
            from sqlalchemy import update

            await db.execute(
                update(WorkflowSession)
                .where(WorkflowSession.session_id == session_id)
                .values(hiring_outreach=SAMPLE_OUTREACH)
            )
            await db.commit()

        llm_ctx = MagicMock(user_api_key="key", provider="gemini", ready=True)
        with (
            patch(
                "utils.llm_context.require_user_llm_context",
                AsyncMock(return_value=(MagicMock(), llm_ctx, None)),
            ),
            patch(
                "utils.llm_preferences.load_preferred_model",
                AsyncMock(return_value=None),
            ),
            patch(
                "api.hiring_outreach.invalidate_hiring_outreach",
                AsyncMock(),
            ) as inv,
            patch(
                "api.hiring_outreach.set_hiring_outreach_generating",
                AsyncMock(return_value=True),
            ),
            patch(
                "api.hiring_outreach._generate_hiring_outreach_background",
                AsyncMock(),
            ),
        ):
            resp = await authed_client_with_user.post(
                f"{BASE}/{session_id}/generate?regenerate=true",
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "generating"
        inv.assert_awaited_once_with(session_id)

    @pytest.mark.asyncio
    async def test_delete_clears_outreach_returns_204(
        self, authed_client_with_user, session_id,
    ):
        async with _NullSessionLocal() as db:
            from sqlalchemy import update

            await db.execute(
                update(WorkflowSession)
                .where(WorkflowSession.session_id == session_id)
                .values(hiring_outreach=SAMPLE_OUTREACH)
            )
            await db.commit()

        with patch(
            "api.hiring_outreach.invalidate_hiring_outreach",
            AsyncMock(),
        ):
            resp = await authed_client_with_user.delete(f"{BASE}/{session_id}")
        assert resp.status_code == 204

        with patch(
            "api.hiring_outreach.get_cached_hiring_outreach",
            AsyncMock(return_value=None),
        ):
            get_resp = await authed_client_with_user.get(f"{BASE}/{session_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["has_hiring_outreach"] is False
        assert get_resp.json()["hiring_outreach"] is None

    @pytest.mark.asyncio
    async def test_status_with_generating_flag(
        self, authed_client_with_user, session_id,
    ):
        async with _NullSessionLocal() as db:
            from sqlalchemy import update

            await db.execute(
                update(WorkflowSession)
                .where(WorkflowSession.session_id == session_id)
                .values(hiring_outreach=SAMPLE_OUTREACH)
            )
            await db.commit()

        with patch(
            "api.hiring_outreach.is_hiring_outreach_generating",
            AsyncMock(return_value=True),
        ):
            resp = await authed_client_with_user.get(
                f"{BASE}/{session_id}/status",
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_generating"] is True
        assert data["has_hiring_outreach"] is True

    @pytest.mark.asyncio
    async def test_get_from_db_returns_outreach_and_caches(
        self, authed_client_with_user, session_id,
    ):
        async with _NullSessionLocal() as db:
            from sqlalchemy import update

            await db.execute(
                update(WorkflowSession)
                .where(WorkflowSession.session_id == session_id)
                .values(hiring_outreach=SAMPLE_OUTREACH)
            )
            await db.commit()

        with (
            patch(
                "api.hiring_outreach.get_cached_hiring_outreach",
                AsyncMock(return_value=None),
            ),
            patch(
                "api.hiring_outreach.cache_hiring_outreach",
                AsyncMock(),
            ) as cache_mock,
        ):
            resp = await authed_client_with_user.get(f"{BASE}/{session_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["has_hiring_outreach"] is True
        assert data["hiring_outreach"]["contacts"]
        cache_mock.assert_awaited_once()


class TestHiringOutreachBackgroundTask:
    """_generate_hiring_outreach_background success and failure paths."""

    @pytest.mark.asyncio
    async def test_background_success_persists_and_broadcasts(
        self, authed_client_with_user,
    ):
        from api.hiring_outreach import _generate_hiring_outreach_background
        from contextlib import asynccontextmanager

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        uid = uuid.UUID(
            jwt.decode(
                token,
                sec.jwt_config["secret_key"],
                algorithms=[sec.jwt_config["algorithm"]],
            )["sub"]
        )
        sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    job_analysis={"job_title": "Dev"},
                    company_research={},
                    profile_matching={},
                    user_data={"full_name": "Jane"},
                )
            )
            await db.commit()

        mock_outreach = dict(SAMPLE_OUTREACH)
        mock_agent = MagicMock()
        mock_agent.generate = AsyncMock(return_value=mock_outreach)

        @asynccontextmanager
        async def _null_get_session():
            async with _NullSessionLocal() as db:
                yield db

        with (
            patch("api.hiring_outreach.get_session", _null_get_session),
            patch("api.hiring_outreach.HiringOutreachAgent", return_value=mock_agent),
            patch("api.hiring_outreach.broadcast_hiring_outreach_started", AsyncMock()),
            patch("api.hiring_outreach.broadcast_hiring_outreach_complete", AsyncMock()),
            patch("api.hiring_outreach.cache_hiring_outreach", AsyncMock()),
            patch("api.hiring_outreach.clear_hiring_outreach_generating", AsyncMock()),
        ):
            await _generate_hiring_outreach_background(sid, user_id=str(uid))

        async with _NullSessionLocal() as db:
            from sqlalchemy import select

            row = await db.execute(
                select(WorkflowSession).where(WorkflowSession.session_id == sid)
            )
            assert row.scalar_one().hiring_outreach is not None

    @pytest.mark.asyncio
    async def test_background_missing_session_is_noop(self):
        from api.hiring_outreach import _generate_hiring_outreach_background

        with patch(
            "api.hiring_outreach.clear_hiring_outreach_generating",
            AsyncMock(),
        ) as clear_flag:
            await _generate_hiring_outreach_background(str(uuid.uuid4()))
        clear_flag.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_background_failure_broadcasts_and_reports(
        self, authed_client_with_user,
    ):
        from api.hiring_outreach import _generate_hiring_outreach_background
        from contextlib import asynccontextmanager

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        uid = uuid.UUID(
            jwt.decode(
                token,
                sec.jwt_config["secret_key"],
                algorithms=[sec.jwt_config["algorithm"]],
            )["sub"]
        )
        sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    job_analysis={"job_title": "Dev"},
                )
            )
            await db.commit()

        mock_agent = MagicMock()
        mock_agent.generate = AsyncMock(side_effect=RuntimeError("LLM failed"))

        @asynccontextmanager
        async def _null_get_session():
            async with _NullSessionLocal() as db:
                yield db

        with (
            patch("api.hiring_outreach.get_session", _null_get_session),
            patch("api.hiring_outreach.HiringOutreachAgent", return_value=mock_agent),
            patch("api.hiring_outreach.broadcast_hiring_outreach_started", AsyncMock()),
            patch("api.hiring_outreach.broadcast_hiring_outreach_error", AsyncMock()) as err_broadcast,
            patch("api.hiring_outreach.report_exception", AsyncMock()) as report,
            patch("api.hiring_outreach.clear_hiring_outreach_generating", AsyncMock()),
        ):
            await _generate_hiring_outreach_background(sid, user_id=str(uid))

        report.assert_awaited_once()
        err_broadcast.assert_awaited_once()


class TestHiringOutreachHelpers:
    """Private helper coverage."""

    def test_get_user_uuid_from_string(self):
        from api.hiring_outreach import _get_user_uuid

        uid = uuid.uuid4()
        assert _get_user_uuid({"id": str(uid)}) == uid

    def test_get_user_uuid_accepts_uuid_object(self):
        from api.hiring_outreach import _get_user_uuid

        uid = uuid.uuid4()
        assert _get_user_uuid({"id": uid}) == uid
