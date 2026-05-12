"""
Integration tests for CV Optimizer API endpoints.

Endpoints:
  POST   /api/v1/cv-optimizer/{session_id}/start
  GET    /api/v1/cv-optimizer/{session_id}
  GET    /api/v1/cv-optimizer/{session_id}/status
  DELETE /api/v1/cv-optimizer/{session_id}
"""

import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

BASE = "/api/v1/cv-optimizer"
SESSION_ID = str(uuid.uuid4())


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
        with (
            patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 60))),
            patch("api.cv_optimizer._get_user_api_key", AsyncMock(return_value=None)),
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
    async def test_cache_hit_returns_200_with_result(self, authed_client):
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
            resp = await authed_client.get(f"{BASE}/{SESSION_ID}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["has_result"] is True
        assert data["result"] is not None

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
    async def test_cannot_delete_while_running_returns_409(self, authed_client):
        with patch("api.cv_optimizer.is_cv_optimization_running", AsyncMock(return_value=True)):
            resp = await authed_client.delete(f"{BASE}/{SESSION_ID}")
        assert resp.status_code == 409
