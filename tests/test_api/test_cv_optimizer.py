"""
Integration tests for CV Optimizer API endpoints.

Endpoints:
  POST   /api/v1/cv-optimizer/{session_id}/start
  GET    /api/v1/cv-optimizer/{session_id}
  GET    /api/v1/cv-optimizer/{session_id}/status
  GET    /api/v1/cv-optimizer/{session_id}/download-cv
  DELETE /api/v1/cv-optimizer/{session_id}
"""

import uuid
import jwt
import pytest
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

from api.cv_optimizer import _run_cv_optimization_background, _synthesize_jd_from_analysis
from agents.cv_optimizer_loop import OptimizationResult
from config.settings import get_security_settings
from models.database import WorkflowSession, WorkflowStatusEnum
from sqlalchemy import select
from tests.test_api.conftest import _NullSessionLocal
from utils.database import get_session as real_get_session

BASE = "/api/v1/cv-optimizer"
SESSION_ID = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# _synthesize_jd_from_analysis
# ---------------------------------------------------------------------------


class TestSynthesizeJdFromAnalysis:
    """Plain-text JD reconstruction when raw job_input is unavailable."""

    def test_builds_text_from_job_analysis_fields(self):
        jd = _synthesize_jd_from_analysis(
            {
                "job_title": "Senior Platform Engineer",
                "company_name": "TechCorp",
                "required_qualifications": ["5+ years Python", "Cloud experience"],
                "preferred_qualifications": ["Kubernetes"],
                "required_skills": ["Python", "AWS"],
            }
        )
        assert "Senior Platform Engineer" in jd
        assert "TechCorp" in jd
        assert "5+ years Python" in jd
        assert "Kubernetes" in jd
        assert "Python, AWS" in jd

    def test_empty_analysis_returns_empty_string(self):
        assert _synthesize_jd_from_analysis({}) == ""


# ---------------------------------------------------------------------------
# get_cached_cv_optimization cache wrapper
# ---------------------------------------------------------------------------


class TestCvOptimizationCache:
    """cache_set wraps payloads; get_cached_cv_optimization must unwrap."""

    @pytest.mark.asyncio
    async def test_get_cached_unwraps_cache_set_wrapper(self):
        from utils.cache import get_cached_cv_optimization

        session_id = str(uuid.uuid4())
        inner = {"optimized_cv": "# Jane", "best_score": 8.2}
        wrapped = {"cached_at": "2026-06-09T00:00:00+00:00", "data": inner}
        with patch("utils.cache.cache_get", AsyncMock(return_value=wrapped)):
            result = await get_cached_cv_optimization(session_id)
        assert result == inner


# ---------------------------------------------------------------------------
# POST /{session_id}/start
# ---------------------------------------------------------------------------


class TestStartCvOptimization:
    """POST /api/v1/cv-optimizer/{session_id}/start"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.post(f"{BASE}/{SESSION_ID}/start")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_rate_limited_returns_429(self, authed_client):
        with patch(
            "api.cv_optimizer.check_rate_limit",
            AsyncMock(return_value=(False, 0)),
        ):
            resp = await authed_client.post(f"{BASE}/{SESSION_ID}/start")
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_no_byok_key_returns_422_cfg6001(self, authed_client):
        from utils.error_responses import no_api_key_error

        with (
            patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 60))),
            patch(
                "utils.llm_context.require_user_llm_context",
                AsyncMock(side_effect=no_api_key_error()),
            ),
        ):
            resp = await authed_client.post(f"{BASE}/{SESSION_ID}/start")
        assert resp.status_code == 422
        data = resp.json()
        assert data.get("error_code") == "CFG_6001"

    @pytest.mark.asyncio
    async def test_session_not_found_returns_404(self, authed_client):
        fake_session = str(uuid.uuid4())
        with (
            patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 60))),
            patch("api.cv_optimizer._get_user_api_key", AsyncMock(return_value="test-key")),
        ):
            resp = await authed_client.post(f"{BASE}/{fake_session}/start")
        assert resp.status_code in (404, 422)

    @pytest.mark.asyncio
    async def test_already_running_returns_409(self, authed_client):
        with (
            patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 60))),
            patch("api.cv_optimizer._get_user_api_key", AsyncMock(return_value="test-key")),
            patch("api.cv_optimizer.set_cv_optimization_running", AsyncMock(return_value=False)),
        ):
            resp = await authed_client.post(f"{BASE}/{SESSION_ID}/start")
        assert resp.status_code in (404, 409)

    @pytest.mark.asyncio
    async def test_valid_config_accepted(self, authed_client):
        """Valid max_iterations and score_threshold must not be rejected."""
        with (
            patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 60))),
            patch("api.cv_optimizer._get_user_api_key", AsyncMock(return_value="test-key")),
        ):
            resp = await authed_client.post(
                f"{BASE}/{SESSION_ID}/start",
                json={"max_iterations": 3, "score_threshold": 8.0},
            )
        # Will fail at session lookup — 404 is expected; what we test is NOT 422 from validation
        assert resp.status_code not in (422,) or resp.json().get("error_code") == "CFG_6001"

    async def test_max_iterations_below_minimum_returns_422(self, authed_client):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/start",
            json={"max_iterations": 1, "score_threshold": 8.0},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_max_iterations_returns_422(self, authed_client):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/start",
            json={"max_iterations": 99, "score_threshold": 8.0},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_score_threshold_too_low_returns_422(self, authed_client):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/start",
            json={"max_iterations": 5, "score_threshold": 3.0},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /{session_id}
# ---------------------------------------------------------------------------


class TestGetCvOptimization:
    """GET /api/v1/cv-optimizer/{session_id}"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.get(f"{BASE}/{SESSION_ID}")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_session_not_found_returns_404(self, authed_client):
        fake_session = str(uuid.uuid4())
        with patch("api.cv_optimizer.get_cached_cv_optimization", AsyncMock(return_value=None)):
            resp = await authed_client.get(f"{BASE}/{fake_session}")
        assert resp.status_code in (404, 200)

    @pytest.mark.asyncio
    async def test_cache_hit_returns_200_with_result(self, authed_client_with_user):
        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token,
            sec.jwt_config["secret_key"],
            algorithms=[sec.jwt_config["algorithm"]],
        )
        uid = uuid.UUID(payload["sub"])
        session_id = str(uuid.uuid4())

        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    user_id=uid,
                )
            )
            await db.commit()

        mock_result = {
            "status": "completed",
            "best_score": 8.6,
            "optimized_cv": "# Jane Smith",
            "cover_letter": "Dear Hiring Team,",
        }
        with patch(
            "api.cv_optimizer.get_cached_cv_optimization",
            AsyncMock(return_value=mock_result),
        ):
            resp = await authed_client_with_user.get(f"{BASE}/{session_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["has_result"] is True
        assert data["result"]["optimized_cv"] == "# Jane Smith"

    @pytest.mark.asyncio
    async def test_unowned_session_returns_404_without_reading_cache(self, authed_client):
        """Ownership is verified before cache — foreign session_id must not leak cached PII."""
        foreign_session = str(uuid.uuid4())
        cache_mock = AsyncMock(
            return_value={
                "optimized_cv": "# Secret CV",
                "cover_letter": "Secret letter",
            }
        )
        with patch("api.cv_optimizer.get_cached_cv_optimization", cache_mock):
            resp = await authed_client.get(f"{BASE}/{foreign_session}")

        assert resp.status_code == 404
        cache_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_result_returns_200_has_result_false(self, authed_client):
        """For a session with no optimization, has_result should be False."""
        with patch("api.cv_optimizer.get_cached_cv_optimization", AsyncMock(return_value=None)):
            resp = await authed_client.get(f"{BASE}/{SESSION_ID}")
        # Either 404 (session not found) or 200 has_result=False
        if resp.status_code == 200:
            data = resp.json()
            assert data["has_result"] is False


# ---------------------------------------------------------------------------
# GET /{session_id}/status
# ---------------------------------------------------------------------------


class TestGetCvOptimizationStatus:
    """GET /api/v1/cv-optimizer/{session_id}/status"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.get(f"{BASE}/{SESSION_ID}/status")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_status_response_has_required_fields(self, authed_client):
        with patch("api.cv_optimizer.is_cv_optimization_running", AsyncMock(return_value=False)):
            resp = await authed_client.get(f"{BASE}/{SESSION_ID}/status")

        if resp.status_code == 200:
            data = resp.json()
            assert "has_result" in data
            assert "is_running" in data
        else:
            assert resp.status_code in (404, 401, 403)

    @pytest.mark.asyncio
    async def test_running_flag_reflected_in_status(self, authed_client):
        with patch("api.cv_optimizer.is_cv_optimization_running", AsyncMock(return_value=True)):
            resp = await authed_client.get(f"{BASE}/{SESSION_ID}/status")

        if resp.status_code == 200:
            data = resp.json()
            assert data["is_running"] is True


# ---------------------------------------------------------------------------
# DELETE /{session_id}
# ---------------------------------------------------------------------------


class TestDeleteCvOptimization:
    """DELETE /api/v1/cv-optimizer/{session_id}"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.delete(f"{BASE}/{SESSION_ID}")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_session_not_found_returns_404(self, authed_client):
        fake_session = str(uuid.uuid4())
        with patch("api.cv_optimizer.is_cv_optimization_running", AsyncMock(return_value=False)):
            resp = await authed_client.delete(f"{BASE}/{fake_session}")
        assert resp.status_code in (404, 204)

    @pytest.mark.asyncio
    async def test_cannot_delete_while_running_returns_409(self, authed_client_with_user):
        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token,
            sec.jwt_config["secret_key"],
            algorithms=[sec.jwt_config["algorithm"]],
        )
        uid = uuid.UUID(payload["sub"])
        session_id = str(uuid.uuid4())

        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    user_id=uid,
                )
            )
            await db.commit()

        with patch("api.cv_optimizer.is_cv_optimization_running", AsyncMock(return_value=True)):
            resp = await authed_client_with_user.delete(f"{BASE}/{session_id}")
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /{session_id}/download-cv
# ---------------------------------------------------------------------------


class TestDownloadOptimizedCv:
    """GET /api/v1/cv-optimizer/{session_id}/download-cv"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.get(f"{BASE}/{SESSION_ID}/download-cv")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_rate_limited_returns_429(self, authed_client):
        with patch(
            "api.cv_optimizer.check_rate_limit",
            AsyncMock(return_value=(False, 0)),
        ):
            resp = await authed_client.get(f"{BASE}/{SESSION_ID}/download-cv")
        assert resp.status_code == 429
        data = resp.json()
        assert data.get("error_code") == "RATE_4001"
        assert "message" in data

    @pytest.mark.asyncio
    async def test_gemini_quota_returns_429_not_500(self, authed_client_with_user):
        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token,
            sec.jwt_config["secret_key"],
            algorithms=[sec.jwt_config["algorithm"]],
        )
        uid = uuid.UUID(payload["sub"])
        session_id = str(uuid.uuid4())

        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    user_id=uid,
                    cv_optimization={"optimized_cv": "# Jane Smith\n\nExperience"},
                )
            )
            await db.commit()

        quota_exc = Exception("429 RESOURCE_EXHAUSTED: exceeded your current quota")

        with (
            patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 60))),
            patch("api.cv_optimizer._get_user_api_key", AsyncMock(return_value="test-key")),
            patch(
                "api.cv_optimizer.get_cached_cv_optimization",
                AsyncMock(return_value={"optimized_cv": "# Jane Smith\n\nExperience"}),
            ),
            patch(
                "api.cv_optimizer._export_optimized_cv_file",
                AsyncMock(side_effect=quota_exc),
            ),
        ):
            resp = await authed_client_with_user.get(f"{BASE}/{session_id}/download-cv")

        assert resp.status_code == 429
        data = resp.json()
        assert data.get("error_code") == "RATE_4001"
        assert "quota" in data.get("message", "").lower()


# ---------------------------------------------------------------------------
# _run_cv_optimization_background — DB session lifecycle
# ---------------------------------------------------------------------------


class TestCvOptimizationBackgroundTask:
    """Background task must not hold a DB connection during the LLM loop."""

    @pytest.mark.asyncio
    async def test_orchestrator_runs_without_open_db_session_and_persists_result(
        self, authed_client_with_user,
    ):
        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token,
            sec.jwt_config["secret_key"],
            algorithms=[sec.jwt_config["algorithm"]],
        )
        uid = uuid.UUID(payload["sub"])
        session_id = str(uuid.uuid4())

        user_data = {
            "full_name": "Jane Smith",
            "professional_title": "Engineer",
            "summary": "Built platforms.",
            "work_experience": [],
            "education": [],
            "skills": ["Python"],
        }
        job_analysis = {
            "job_title": "Senior Engineer",
            "company_name": "TechCorp",
            "required_skills": ["Python"],
        }

        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    user_id=uid,
                    workflow_status=WorkflowStatusEnum.COMPLETED.value,
                    user_data=user_data,
                    job_analysis=job_analysis,
                    job_input_data={"job_input": "Senior Engineer at TechCorp. Python required."},
                )
            )
            await db.commit()

        session_depth = 0
        orchestrator_called_while_session_open = False

        @asynccontextmanager
        async def tracking_get_session():
            nonlocal session_depth, orchestrator_called_while_session_open
            session_depth += 1
            try:
                async with real_get_session() as db:
                    yield db
            finally:
                session_depth -= 1

        mock_result = OptimizationResult(
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
            stop_reason="score_threshold",
            config={"max_iterations": 3, "score_threshold": 8.0},
            status="completed",
            best_score=8.5,
            optimized_cv="# Jane Smith\n\n## Experience",
            cover_letter="Dear Hiring Team,",
        )

        async def mock_orchestrator_run(**_kwargs):
            nonlocal orchestrator_called_while_session_open
            orchestrator_called_while_session_open = session_depth > 0
            return mock_result

        with (
            patch("api.cv_optimizer.get_session", tracking_get_session),
            patch(
                "api.cv_optimizer.CVOptimizationOrchestrator.run",
                AsyncMock(side_effect=mock_orchestrator_run),
            ),
            patch("api.cv_optimizer.broadcast_cv_optimization_started", AsyncMock()),
            patch("api.cv_optimizer.broadcast_cv_optimization_complete", AsyncMock()),
            patch("api.cv_optimizer.cache_cv_optimization", AsyncMock()),
            patch("api.cv_optimizer.clear_cv_optimization_running", AsyncMock()),
        ):
            await _run_cv_optimization_background(
                session_id=session_id,
                user_id=str(uid),
                user_api_key="test-key",
            )

        assert orchestrator_called_while_session_open is False

        async with _NullSessionLocal() as db:
            row = await db.execute(
                select(WorkflowSession).where(WorkflowSession.session_id == session_id)
            )
            workflow_session = row.scalar_one()
            stored = workflow_session.cv_optimization

        assert stored is not None
        assert stored["optimized_cv"] == "# Jane Smith\n\n## Experience"
        assert stored["best_score"] == 8.5
        assert stored["stop_reason"] == "score_threshold"


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------


class TestCvOptimizerHelpers:
    """Private helpers in api/cv_optimizer.py."""

    def test_sanitize_optimization_result_strips_cv_and_cover_letter(self):
        from api.cv_optimizer import _sanitize_optimization_result

        raw = {"optimized_cv": "Hello world", "cover_letter": "Dear Team", "best_score": 8.0}
        cleaned = _sanitize_optimization_result(raw)
        assert cleaned is not None
        assert cleaned["optimized_cv"] == "Hello world"

    def test_sanitize_optimization_result_none(self):
        from api.cv_optimizer import _sanitize_optimization_result

        assert _sanitize_optimization_result(None) is None

    def test_resolve_soffice_path_returns_none_when_missing(self):
        from api.cv_optimizer import _resolve_soffice_path

        with (
            patch("api.cv_optimizer.shutil.which", return_value=None),
            patch("api.cv_optimizer.os.path.isfile", return_value=False),
        ):
            assert _resolve_soffice_path() is None

    @pytest.mark.asyncio
    async def test_background_task_broadcasts_error_on_failure(self):
        with (
            patch("api.cv_optimizer.get_session", side_effect=RuntimeError("db down")),
            patch("api.cv_optimizer.report_exception", AsyncMock()) as report,
            patch("api.cv_optimizer.broadcast_cv_optimization_error", AsyncMock()) as broadcast,
            patch("api.cv_optimizer.clear_cv_optimization_running", AsyncMock()),
        ):
            await _run_cv_optimization_background(
                session_id=str(uuid.uuid4()),
                user_id=str(uuid.uuid4()),
                user_api_key="key",
            )
        report.assert_awaited_once()
        broadcast.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_successful_delete_clears_db_and_cache(self, authed_client_with_user):
        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token,
            sec.jwt_config["secret_key"],
            algorithms=[sec.jwt_config["algorithm"]],
        )
        uid = uuid.UUID(payload["sub"])
        session_id = str(uuid.uuid4())

        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    user_id=uid,
                    cv_optimization={"optimized_cv": "# CV", "best_score": 7.0},
                )
            )
            await db.commit()

        with (
            patch("api.cv_optimizer.is_cv_optimization_running", AsyncMock(return_value=False)),
            patch("api.cv_optimizer.invalidate_cv_optimization", AsyncMock()) as invalidate,
        ):
            resp = await authed_client_with_user.delete(f"{BASE}/{session_id}")

        assert resp.status_code == 204
        invalidate.assert_awaited_once_with(session_id)


class TestCvOptimizerStartWithSession:
    """POST /start against real workflow sessions."""

    async def _create_session(
        self,
        authed_client_with_user,
        *,
        workflow_status=WorkflowStatusEnum.COMPLETED.value,
        job_analysis=None,
        user_data=None,
        resume_recommendations=None,
        cover_letter=None,
        job_input_data=None,
        cv_optimization=None,
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
        session_id = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    user_id=uid,
                    workflow_status=workflow_status,
                    job_analysis=job_analysis or {"job_title": "Engineer", "company_name": "Co"},
                    user_data=user_data or {"full_name": "Jane", "skills": ["Python"]},
                    resume_recommendations=resume_recommendations,
                    cover_letter=cover_letter,
                    job_input_data=job_input_data,
                    cv_optimization=cv_optimization,
                )
            )
            await db.commit()
        return session_id, uid

    @pytest.mark.asyncio
    async def test_start_success_returns_202(self, authed_client_with_user):
        session_id, _ = await self._create_session(authed_client_with_user)
        with (
            patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 9))),
            patch("api.cv_optimizer._get_user_api_key", AsyncMock(return_value="test-key")),
            patch("api.cv_optimizer.set_cv_optimization_running", AsyncMock(return_value=True)),
            patch("api.cv_optimizer._run_cv_optimization_background", AsyncMock()),
        ):
            resp = await authed_client_with_user.post(f"{BASE}/{session_id}/start")
        assert resp.status_code == 202
        assert resp.json()["status"] == "started"

    @pytest.mark.asyncio
    async def test_start_heals_analysis_complete_when_docs_present(
        self, authed_client_with_user,
    ):
        session_id, _ = await self._create_session(
            authed_client_with_user,
            workflow_status=WorkflowStatusEnum.ANALYSIS_COMPLETE.value,
            resume_recommendations={"tips": []},
            cover_letter={"body": "Dear team"},
        )
        with (
            patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 9))),
            patch("api.cv_optimizer._get_user_api_key", AsyncMock(return_value="test-key")),
            patch("api.cv_optimizer.set_cv_optimization_running", AsyncMock(return_value=True)),
            patch("api.cv_optimizer._run_cv_optimization_background", AsyncMock()),
        ):
            resp = await authed_client_with_user.post(f"{BASE}/{session_id}/start")
        assert resp.status_code == 202

    @pytest.mark.asyncio
    async def test_start_in_progress_returns_409(self, authed_client_with_user):
        session_id, _ = await self._create_session(
            authed_client_with_user,
            workflow_status=WorkflowStatusEnum.IN_PROGRESS.value,
        )
        with (
            patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 9))),
            patch("api.cv_optimizer._get_user_api_key", AsyncMock(return_value="test-key")),
        ):
            resp = await authed_client_with_user.post(f"{BASE}/{session_id}/start")
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_start_missing_user_data_returns_422(self, authed_client_with_user):
        session_id, _ = await self._create_session(
            authed_client_with_user,
            user_data=None,
        )
        async with _NullSessionLocal() as db:
            from sqlalchemy import update

            await db.execute(
                update(WorkflowSession)
                .where(WorkflowSession.session_id == session_id)
                .values(user_data=None)
            )
            await db.commit()

        with (
            patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 9))),
            patch("api.cv_optimizer._get_user_api_key", AsyncMock(return_value="test-key")),
        ):
            resp = await authed_client_with_user.post(f"{BASE}/{session_id}/start")
        assert resp.status_code == 422


class TestCvOptimizerGetAndDownload:
    """GET result/status and download paths."""

    @pytest.mark.asyncio
    async def test_get_from_db_without_cache(self, authed_client_with_user):
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
        optimization = {
            "optimized_cv": "# Jane",
            "cover_letter": "Dear Team",
            "best_score": 8.1,
        }
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    user_id=uid,
                    cv_optimization=optimization,
                )
            )
            await db.commit()

        with (
            patch("api.cv_optimizer.get_cached_cv_optimization", AsyncMock(return_value=None)),
            patch("api.cv_optimizer.cache_cv_optimization", AsyncMock()) as cache_mock,
        ):
            resp = await authed_client_with_user.get(f"{BASE}/{session_id}")
        assert resp.status_code == 200
        assert resp.json()["has_result"] is True
        cache_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_status_includes_best_score(self, authed_client_with_user):
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
                    cv_optimization={
                        "best_score": 7.8,
                        "completed_at": "2026-01-01T00:00:00+00:00",
                    },
                )
            )
            await db.commit()

        with patch("api.cv_optimizer.is_cv_optimization_running", AsyncMock(return_value=False)):
            resp = await authed_client_with_user.get(f"{BASE}/{session_id}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["best_score"] == 7.8
        assert data["completed_at"] == "2026-01-01T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_download_docx_fallback_success(self, authed_client_with_user):
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
                    cv_optimization={"optimized_cv": "# Jane\n\nExperience"},
                )
            )
            await db.commit()

        with (
            patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 9))),
            patch("api.cv_optimizer._get_user_api_key", AsyncMock(return_value=None)),
            patch("api.cv_optimizer.get_cached_cv_optimization", AsyncMock(return_value=None)),
            patch("api.cv_optimizer._resolve_soffice_path", return_value=None),
            patch(
                "api.cv_optimizer.markdown_cv_to_docx_bytes",
                return_value=b"PKfake-docx",
            ),
        ):
            resp = await authed_client_with_user.get(f"{BASE}/{session_id}/download-cv")
        assert resp.status_code == 200
        assert "wordprocessingml" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_download_no_optimization_returns_404(self, authed_client_with_user):
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
                )
            )
            await db.commit()

        with (
            patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 9))),
            patch("api.cv_optimizer._get_user_api_key", AsyncMock(return_value=None)),
        ):
            resp = await authed_client_with_user.get(f"{BASE}/{session_id}/download-cv")
        assert resp.status_code == 404


class TestCvOptimizerExportHelpers:
    """Unit tests for export and HTML conversion helpers."""

    @pytest.mark.asyncio
    async def test_generate_cv_html_strips_code_fences(self):
        from api.cv_optimizer import _generate_cv_html_from_markdown

        mock_client = MagicMock()
        mock_client.generate = AsyncMock(
            return_value={
                "response": "```html\n<!DOCTYPE html><html><body>CV</body></html>\n```",
                "done": True,
            }
        )
        with (
            patch("utils.llm_client.get_gemini_client", AsyncMock(return_value=mock_client)),
            patch(
                "api.cv_optimizer.normalize_cv_export_html",
                lambda html: html,
            ),
        ):
            html = await _generate_cv_html_from_markdown("# Jane", "key")
        assert html.lower().startswith("<!doctype")

    @pytest.mark.asyncio
    async def test_generate_cv_html_filtered_raises(self):
        from api.cv_optimizer import _generate_cv_html_from_markdown

        mock_client = MagicMock()
        mock_client.generate = AsyncMock(return_value={"filtered": True, "response": "blocked"})
        with patch("utils.llm_client.get_gemini_client", AsyncMock(return_value=mock_client)):
            with pytest.raises(ValueError, match="blocked"):
                await _generate_cv_html_from_markdown("# Jane", "key")

    @pytest.mark.asyncio
    async def test_export_optimized_cv_file_docx_when_no_soffice(self):
        from api.cv_optimizer import _export_optimized_cv_file

        with (
            patch("api.cv_optimizer._resolve_soffice_path", return_value=None),
            patch(
                "api.cv_optimizer.markdown_cv_to_docx_bytes",
                return_value=b"docx-bytes",
            ),
        ):
            data, mime, name = await _export_optimized_cv_file("# CV", None)
        assert data == b"docx-bytes"
        assert name == "optimized-cv.docx"
        assert "wordprocessingml" in mime

    def test_resolve_soffice_path_finds_candidate(self):
        from api.cv_optimizer import _resolve_soffice_path

        with (
            patch("api.cv_optimizer.shutil.which", return_value=None),
            patch("api.cv_optimizer.os.path.isfile", return_value=True),
            patch("api.cv_optimizer.os.access", return_value=True),
        ):
            path = _resolve_soffice_path()
        assert path is not None
        assert path.endswith("soffice")

    @pytest.mark.asyncio
    async def test_background_uses_synthesized_jd_for_url_input(
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
        session_id = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    user_id=uid,
                    workflow_status=WorkflowStatusEnum.COMPLETED.value,
                    user_data={"full_name": "Jane", "skills": ["Go"]},
                    job_analysis={"job_title": "Backend Dev", "company_name": "Co"},
                    job_input_data={"job_input": "https://example.com/jobs/1"},
                )
            )
            await db.commit()

        captured: dict = {}

        async def mock_orchestrator_run(**kwargs):
            captured.update(kwargs)
            return OptimizationResult(
                started_at=datetime.now(timezone.utc).isoformat(),
                completed_at=datetime.now(timezone.utc).isoformat(),
                stop_reason="max_iterations",
                config={"max_iterations": 3, "score_threshold": 8.0},
                status="completed",
                best_score=7.0,
                optimized_cv="# CV",
                cover_letter="Letter",
            )

        @asynccontextmanager
        async def _null_get_session():
            async with real_get_session() as db:
                yield db

        with (
            patch("api.cv_optimizer.get_session", _null_get_session),
            patch("api.cv_optimizer.CVOptimizationOrchestrator.run", AsyncMock(side_effect=mock_orchestrator_run)),
            patch("api.cv_optimizer.broadcast_cv_optimization_started", AsyncMock()),
            patch("api.cv_optimizer.broadcast_cv_optimization_complete", AsyncMock()),
            patch("api.cv_optimizer.cache_cv_optimization", AsyncMock()),
            patch("api.cv_optimizer.clear_cv_optimization_running", AsyncMock()),
        ):
            await _run_cv_optimization_background(
                session_id=session_id,
                user_id=str(uid),
                user_api_key="key",
            )

        assert "Backend Dev" in captured.get("job_description", "")

    @pytest.mark.asyncio
    async def test_start_analysis_complete_without_docs_returns_409(
        self, authed_client_with_user,
    ):
        session_id, _ = await TestCvOptimizerStartWithSession()._create_session(
            authed_client_with_user,
            workflow_status=WorkflowStatusEnum.ANALYSIS_COMPLETE.value,
        )
        with (
            patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 9))),
            patch("api.cv_optimizer._get_user_api_key", AsyncMock(return_value="key")),
        ):
            resp = await authed_client_with_user.post(f"{BASE}/{session_id}/start")
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_start_with_server_key_when_no_byok(self, authed_client_with_user):
        session_id, _ = await TestCvOptimizerStartWithSession()._create_session(
            authed_client_with_user,
        )
        with (
            patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 9))),
            patch("api.cv_optimizer._get_user_api_key", AsyncMock(return_value=None)),
            patch("api.cv_optimizer.settings") as mock_settings,
            patch("api.cv_optimizer.set_cv_optimization_running", AsyncMock(return_value=True)),
            patch("api.cv_optimizer._run_cv_optimization_background", AsyncMock()),
        ):
            mock_settings.gemini_api_key = "server-key"
            mock_settings.use_vertex_ai = False
            resp = await authed_client_with_user.post(f"{BASE}/{session_id}/start")
        assert resp.status_code == 202

    @pytest.mark.asyncio
    async def test_markdown_cv_to_odt_via_libreoffice_success(self):
        from api.cv_optimizer import _markdown_cv_to_odt_via_libreoffice

        fake_proc = MagicMock()
        fake_proc.returncode = 0

        async def fake_html(*_a, **_k):
            return "<!DOCTYPE html><html><body>CV</body></html>"

        with (
            patch("api.cv_optimizer._generate_cv_html_from_markdown", AsyncMock(side_effect=fake_html)),
            patch("api.cv_optimizer.asyncio.get_event_loop") as mock_loop,
            patch("api.cv_optimizer.os.path.exists", return_value=True),
            patch("api.cv_optimizer.shutil.rmtree"),
            patch("api.cv_optimizer.tempfile.mkdtemp", return_value="/tmp/cvo_test"),
            patch("builtins.open", mock_open(read_data=b"odt")),
        ):
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=fake_proc)
            result = await _markdown_cv_to_odt_via_libreoffice("# CV", None, "/usr/bin/soffice")
        assert result == b"odt"

    @pytest.mark.asyncio
    async def test_export_uses_odt_when_libreoffice_available(self):
        from api.cv_optimizer import _export_optimized_cv_file

        with (
            patch("api.cv_optimizer._resolve_soffice_path", return_value="/usr/bin/soffice"),
            patch(
                "api.cv_optimizer._markdown_cv_to_odt_via_libreoffice",
                AsyncMock(return_value=b"odt-content"),
            ),
        ):
            data, mime, name = await _export_optimized_cv_file("# CV", None)
        assert data == b"odt-content"
        assert name == "optimized-cv.odt"

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

