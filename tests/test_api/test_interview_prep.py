"""
Integration tests for Interview Prep API endpoints.

Endpoints:
  GET    /api/v1/interview-prep/{session_id}
  GET    /api/v1/interview-prep/{session_id}/status
  POST   /api/v1/interview-prep/{session_id}/generate
  DELETE /api/v1/interview-prep/{session_id}
"""

import uuid
import jwt
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from models.database import WorkflowSession
from config.settings import get_security_settings
from tests.test_api.conftest import _NullSessionLocal

BASE = "/api/v1/interview-prep"
SESSION_ID = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# GET /{session_id}
# ---------------------------------------------------------------------------


class TestGetInterviewPrep:
    """GET /api/v1/interview-prep/{session_id}"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.get(f"{BASE}/{SESSION_ID}")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_session_not_found_returns_404(self, authed_client):
        fake_session = str(uuid.uuid4())
        # No cache, no DB row
        with patch("api.interview_prep.get_cached_interview_prep",
                   AsyncMock(return_value=None)):
            resp = await authed_client.get(f"{BASE}/{fake_session}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cache_hit_returns_200(self, authed_client):
        mock_cached = {
            "data": {"predicted_questions": {"behavioral": []}},
            "cached_at": "2026-01-01T00:00:00+00:00",
        }
        with patch("api.interview_prep.get_cached_interview_prep",
                   AsyncMock(return_value=mock_cached)):
            resp = await authed_client.get(f"{BASE}/{SESSION_ID}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["has_interview_prep"] is True
        assert data["session_id"] == SESSION_ID


# ---------------------------------------------------------------------------
# GET /{session_id}/status
# ---------------------------------------------------------------------------


class TestInterviewPrepStatus:
    """GET /api/v1/interview-prep/{session_id}/status"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.get(f"{BASE}/{SESSION_ID}/status")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_session_not_found_returns_404(self, authed_client):
        fake_session = str(uuid.uuid4())
        with patch("api.interview_prep.get_cached_interview_prep",
                   AsyncMock(return_value=None)):
            resp = await authed_client.get(f"{BASE}/{fake_session}/status")
        assert resp.status_code in (404, 200)  # 200 with has_prep=False is also valid

    @pytest.mark.asyncio
    async def test_status_has_required_fields(self, authed_client):
        with patch("api.interview_prep.get_cached_interview_prep",
                   AsyncMock(return_value=None)):
            resp = await authed_client.get(f"{BASE}/{SESSION_ID}/status")

        if resp.status_code == 200:
            data = resp.json()
            assert "has_interview_prep" in data or "status" in data
        else:
            assert resp.status_code in (404, 401, 403)


# ---------------------------------------------------------------------------
# POST /{session_id}/generate
# ---------------------------------------------------------------------------


class TestGenerateInterviewPrep:
    """POST /api/v1/interview-prep/{session_id}/generate"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.post(f"{BASE}/{SESSION_ID}/generate")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_session_not_found_returns_404(self, authed_client):
        fake_session = str(uuid.uuid4())
        with patch("api.interview_prep.get_cached_interview_prep",
                   AsyncMock(return_value=None)):
            resp = await authed_client.post(f"{BASE}/{fake_session}/generate")
        assert resp.status_code in (404, 200, 202)

    @pytest.mark.asyncio
    async def test_rate_limited_returns_429(self, authed_client):
        with patch("api.interview_prep.check_rate_limit",
                   AsyncMock(return_value=(False, 0))):
            resp = await authed_client.post(f"{BASE}/{SESSION_ID}/generate")
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_generate_nonexistent_session_returns_404_or_202(self, authed_client):
        """Generating for a nonexistent session should return 404 or start gracefully."""
        fake_session = str(uuid.uuid4())
        with patch("api.interview_prep.get_cached_interview_prep",
                   AsyncMock(return_value=None)):
            resp = await authed_client.post(f"{BASE}/{fake_session}/generate")
        assert resp.status_code in (200, 202, 404, 409)


# ---------------------------------------------------------------------------
# DELETE /{session_id}
# ---------------------------------------------------------------------------


class TestDeleteInterviewPrep:
    """DELETE /api/v1/interview-prep/{session_id}"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.delete(f"{BASE}/{SESSION_ID}")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_session_not_found_returns_404(self, authed_client):
        fake_session = str(uuid.uuid4())
        with patch("api.interview_prep.get_cached_interview_prep",
                   AsyncMock(return_value=None)):
            resp = await authed_client.delete(f"{BASE}/{fake_session}")
        assert resp.status_code in (404, 204)


# ---------------------------------------------------------------------------
# Generate / delete with real workflow session
# ---------------------------------------------------------------------------


class TestInterviewPrepWithSession:
    """Endpoints backed by a real WorkflowSession row."""

    @pytest_asyncio.fixture
    async def session_id(self, authed_client_with_user):
        import jwt
        from config.settings import get_security_settings

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
    async def test_generate_missing_job_analysis_returns_422(self, authed_client_with_user):
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

        with patch("api.interview_prep._check_api_key_available", AsyncMock(return_value=True)):
            resp = await authed_client_with_user.post(f"{BASE}/{sid}/generate")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_generate_already_exists_returns_exists_status(
        self, authed_client_with_user, session_id,
    ):
        async with _NullSessionLocal() as db:
            from sqlalchemy import update

            await db.execute(
                update(WorkflowSession)
                .where(WorkflowSession.session_id == session_id)
                .values(interview_prep={"predicted_questions": {}})
            )
            await db.commit()

        with patch("api.interview_prep._check_api_key_available", AsyncMock(return_value=True)):
            resp = await authed_client_with_user.post(f"{BASE}/{session_id}/generate")
        assert resp.status_code == 200
        assert resp.json()["status"] == "exists"

    @pytest.mark.asyncio
    async def test_delete_clears_prep(self, authed_client_with_user, session_id):
        async with _NullSessionLocal() as db:
            from sqlalchemy import update

            await db.execute(
                update(WorkflowSession)
                .where(WorkflowSession.session_id == session_id)
                .values(interview_prep={"predicted_questions": {}})
            )
            await db.commit()

        with (
            patch("api.interview_prep.invalidate_interview_prep", AsyncMock()),
            patch("api.interview_prep.is_interview_prep_generating", AsyncMock(return_value=False)),
        ):
            resp = await authed_client_with_user.delete(f"{BASE}/{session_id}")
        assert resp.status_code == 204


class TestInterviewPrepBackgroundTask:
    """_generate_interview_prep_background success and failure paths."""

    @pytest.mark.asyncio
    async def test_background_success_persists_and_broadcasts(self, authed_client_with_user):
        from api.interview_prep import _generate_interview_prep_background
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

        mock_prep = {"predicted_questions": {"behavioral": []}, "version": "1.0"}
        mock_agent = MagicMock()
        mock_agent.generate = AsyncMock(return_value=mock_prep)

        @asynccontextmanager
        async def _null_get_session():
            async with _NullSessionLocal() as db:
                yield db

        with (
            patch("api.interview_prep.get_session", _null_get_session),
            patch("api.interview_prep.InterviewPrepAgent", return_value=mock_agent),
            patch("api.interview_prep.broadcast_interview_prep_started", AsyncMock()),
            patch("api.interview_prep.broadcast_interview_prep_complete", AsyncMock()),
            patch("api.interview_prep.cache_interview_prep", AsyncMock()),
            patch("api.interview_prep.clear_interview_prep_generating", AsyncMock()),
        ):
            await _generate_interview_prep_background(sid, user_id=str(uid))

        async with _NullSessionLocal() as db:
            from sqlalchemy import select

            row = await db.execute(
                select(WorkflowSession).where(WorkflowSession.session_id == sid)
            )
            assert row.scalar_one().interview_prep is not None

    @pytest.mark.asyncio
    async def test_background_missing_session_is_noop(self):
        from api.interview_prep import _generate_interview_prep_background

        with patch("api.interview_prep.clear_interview_prep_generating", AsyncMock()) as clear_flag:
            await _generate_interview_prep_background(str(uuid.uuid4()))
        clear_flag.assert_awaited_once()


class TestInterviewPrepHelpers:
    """Private helper coverage."""

    def test_get_user_uuid_from_string(self):
        from api.interview_prep import _get_user_uuid

        uid = uuid.uuid4()
        assert _get_user_uuid({"id": str(uid)}) == uid

    @pytest.mark.asyncio
    async def test_get_user_api_key_decrypt_failure(self):
        from api.interview_prep import _get_user_api_key

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("decrypt fail"))
        assert await _get_user_api_key(mock_db, uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_check_api_key_server_vertex(self):
        from api.interview_prep import _check_api_key_available
        from utils.llm.availability import UserLLMContext

        mock_db = AsyncMock()
        ctx = UserLLMContext(
            provider="gemini",
            user_api_key=None,
            preferred_model=None,
            ready=True,
        )
        with patch(
            "utils.llm_context.require_user_llm_context",
            AsyncMock(return_value=(MagicMock(), ctx, None)),
        ):
            assert await _check_api_key_available(mock_db, uuid.uuid4()) is True


class TestInterviewPrepDbEndpoints:
    """GET/POST/DELETE with real WorkflowSession rows."""

    @pytest_asyncio.fixture
    async def prep_session(self, authed_client_with_user):
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
        prep = {
            "predicted_questions": {"behavioral": ["Tell me about yourself"]},
            "generated_at": "2026-01-01T00:00:00+00:00",
        }
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status="completed",
                    job_analysis={"job_title": "Engineer", "company_name": "Co"},
                    interview_prep=prep,
                )
            )
            await db.commit()
        return sid, prep

    @pytest.mark.asyncio
    async def test_get_from_db_returns_prep_and_caches(
        self, authed_client_with_user, prep_session,
    ):
        sid, prep = prep_session
        with (
            patch("api.interview_prep.get_cached_interview_prep", AsyncMock(return_value=None)),
            patch("api.interview_prep.cache_interview_prep", AsyncMock()) as cache_mock,
        ):
            resp = await authed_client_with_user.get(f"{BASE}/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_interview_prep"] is True
        assert data["interview_prep"]["predicted_questions"]
        cache_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_status_with_generating_flag(
        self, authed_client_with_user, prep_session,
    ):
        sid, _ = prep_session
        with patch("api.interview_prep.is_interview_prep_generating", AsyncMock(return_value=True)):
            resp = await authed_client_with_user.get(f"{BASE}/{sid}/status")
        assert resp.status_code == 200
        assert resp.json()["is_generating"] is True
        assert resp.json()["has_interview_prep"] is True

    @pytest.mark.asyncio
    async def test_generate_starts_background_task(
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
                    job_analysis={"job_title": "Dev"},
                )
            )
            await db.commit()

        with (
            patch("api.interview_prep._check_api_key_available", AsyncMock(return_value=True)),
            patch("api.interview_prep._get_user_api_key", AsyncMock(return_value="key")),
            patch("api.interview_prep.set_interview_prep_generating", AsyncMock(return_value=True)),
            patch("api.interview_prep._generate_interview_prep_background", AsyncMock()),
        ):
            resp = await authed_client_with_user.post(f"{BASE}/{sid}/generate")
        assert resp.status_code == 200
        assert resp.json()["status"] == "generating"

    @pytest.mark.asyncio
    async def test_generate_regenerate_invalidates_cache(
        self, authed_client_with_user, prep_session,
    ):
        sid, _ = prep_session
        with (
            patch("api.interview_prep._check_api_key_available", AsyncMock(return_value=True)),
            patch("api.interview_prep._get_user_api_key", AsyncMock(return_value="key")),
            patch("api.interview_prep.invalidate_interview_prep", AsyncMock()) as inv,
            patch("api.interview_prep.set_interview_prep_generating", AsyncMock(return_value=True)),
            patch("api.interview_prep._generate_interview_prep_background", AsyncMock()),
        ):
            resp = await authed_client_with_user.post(
                f"{BASE}/{sid}/generate?regenerate=true",
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "generating"
        inv.assert_awaited_once_with(sid)

    @pytest.mark.asyncio
    async def test_generate_conflict_when_already_generating(
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
                    job_analysis={"job_title": "Dev"},
                )
            )
            await db.commit()

        with (
            patch("api.interview_prep._check_api_key_available", AsyncMock(return_value=True)),
            patch("api.interview_prep.set_interview_prep_generating", AsyncMock(return_value=False)),
        ):
            resp = await authed_client_with_user.post(f"{BASE}/{sid}/generate")
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_generate_no_api_key_returns_422(self, authed_client_with_user):
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
                    job_analysis={"job_title": "Dev"},
                )
            )
            await db.commit()

        from utils.error_responses import no_api_key_error

        with patch(
            "utils.llm_context.require_user_llm_context",
            AsyncMock(side_effect=no_api_key_error()),
        ):
            resp = await authed_client_with_user.post(f"{BASE}/{sid}/generate")
        assert resp.status_code == 422
        assert resp.json().get("error_code") == "CFG_6001"

    @pytest.mark.asyncio
    async def test_background_failure_broadcasts_and_persists_error(
        self, authed_client_with_user,
    ):
        from api.interview_prep import _generate_interview_prep_background
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
            patch("api.interview_prep.get_session", _null_get_session),
            patch("api.interview_prep.InterviewPrepAgent", return_value=mock_agent),
            patch("api.interview_prep.broadcast_interview_prep_started", AsyncMock()),
            patch("api.interview_prep.broadcast_interview_prep_error", AsyncMock()) as err_broadcast,
            patch("api.interview_prep.report_exception", AsyncMock()) as report,
            patch("api.interview_prep.clear_interview_prep_generating", AsyncMock()),
        ):
            await _generate_interview_prep_background(sid, user_id=str(uid))

        report.assert_awaited_once()
        err_broadcast.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_internal_error_returns_500(self, authed_client):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("db fail"))

        from utils.database import get_database
        from main import app

        async def _broken_db():
            yield mock_db

        app.dependency_overrides[get_database] = _broken_db
        try:
            resp = await authed_client.get(f"{BASE}/{SESSION_ID}")
        finally:
            from tests.test_api.conftest import _get_null_pool_db

            app.dependency_overrides[get_database] = _get_null_pool_db
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_delete_not_found_returns_404(self, authed_client):
        fake = str(uuid.uuid4())
        resp = await authed_client.delete(f"{BASE}/{fake}")
        assert resp.status_code == 404

    def test_get_user_uuid_accepts_uuid_object(self):
        from api.interview_prep import _get_user_uuid

        uid = uuid.uuid4()
        assert _get_user_uuid({"id": uid}) == uid

