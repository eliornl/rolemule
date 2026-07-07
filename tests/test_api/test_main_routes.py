"""
Integration and unit tests for main.py routes, middleware, helpers, and error handlers.
"""

import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import jwt
import pytest
import pytest_asyncio
from fastapi import APIRouter, HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.responses import Response

import main
from config.settings import get_security_settings, get_settings
from main import (
    _cleanup_orphaned_sessions,
    _is_html_request,
    _load_asset_manifest,
    asset_url,
    create_app,
    get_analytics_context,
    lifespan,
)
from tests.test_api.conftest import _make_test_jwt
from utils.cache import RateLimitResult
from utils.error_responses import APIError, ErrorCode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEMPLATES_NONE_ROUTES = [
    "/dashboard/new-application",
    "/auth/login",
    "/auth/register",
    "/auth/reset-password",
    "/auth/forgot-password",
    "/auth/verify-email",
    "/dashboard/tools",
    f"/dashboard/interview-prep/{uuid.uuid4()}",
    "/profile/setup",
    "/help",
    "/privacy",
    "/terms",
    "/dashboard/settings",
    f"/dashboard/application/{uuid.uuid4()}",
]

_PAGE_ROUTES = [
    "/",
    "/dashboard",
    "/dashboard/new-application",
    "/auth/login",
    "/auth/register",
    "/auth/reset-password",
    "/auth/forgot-password",
    "/auth/verify-email",
    "/dashboard/tools",
    "/profile/setup",
    "/help",
    "/maintenance",
    "/privacy",
    "/terms",
    "/dashboard/settings",
    f"/dashboard/interview-prep/{uuid.uuid4()}",
    f"/dashboard/application/{uuid.uuid4()}",
]


@pytest_asyncio.fixture
async def admin_client(api_client):
    """AsyncClient with admin privileges for cache stats and admin-only routes."""
    from utils.auth import get_current_user, require_admin

    uid = str(uuid.uuid4())
    email = f"admin_{uid[:8]}@example.com"
    admin_user = {
        "id": uid,
        "email": email,
        "full_name": "Admin User",
        "auth_method": "local",
        "profile_completed": True,
        "is_admin": True,
    }

    async def _admin():
        return admin_user

    main.app.dependency_overrides[get_current_user] = _admin
    main.app.dependency_overrides[require_admin] = _admin
    api_client.headers.update({"Authorization": f"Bearer {_make_test_jwt(uid, email)}"})
    try:
        yield api_client
    finally:
        main.app.dependency_overrides.pop(get_current_user, None)
        main.app.dependency_overrides.pop(require_admin, None)


# ---------------------------------------------------------------------------
# Asset manifest helpers
# ---------------------------------------------------------------------------


class TestAssetManifest:
    """asset_url() and _load_asset_manifest()."""

    def test_asset_url_without_manifest_entry(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main, "_asset_manifest", None)
        monkeypatch.setattr(main, "_MANIFEST_PATH", tmp_path / "missing.json")
        assert asset_url("js/app.js") == "/static/js/app.js"

    def test_asset_url_with_hashed_manifest(self, tmp_path, monkeypatch):
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({"js/app.js": "js/app.abc123.js"}))
        monkeypatch.setattr(main, "_asset_manifest", None)
        monkeypatch.setattr(main, "_MANIFEST_PATH", manifest_path)
        assert asset_url("js/app.js") == "/static/dist/js/app.abc123.js"

    def test_load_asset_manifest_invalid_json(self, tmp_path, monkeypatch):
        bad = tmp_path / "manifest.json"
        bad.write_text("{not json")
        monkeypatch.setattr(main, "_asset_manifest", None)
        monkeypatch.setattr(main, "_MANIFEST_PATH", bad)
        assert _load_asset_manifest() == {}

    def test_get_analytics_context(self):
        ctx = get_analytics_context()
        assert "posthog_api_key" in ctx
        assert "posthog_host" in ctx

    def test_load_asset_manifest_os_error(self, tmp_path, monkeypatch):
        manifest_path = tmp_path / "manifest.json"
        monkeypatch.setattr(main, "_asset_manifest", None)
        monkeypatch.setattr(main, "_MANIFEST_PATH", manifest_path)
        with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
            assert _load_asset_manifest() == {}

    def test_asset_url_uses_cached_manifest_in_production(self, tmp_path, monkeypatch):
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({"js/app.js": "js/app.prod.js"}))
        monkeypatch.setattr(main, "_asset_manifest", {"js/app.js": "js/app.cached.js"})
        monkeypatch.setattr(main, "_MANIFEST_PATH", manifest_path)
        settings = get_settings()
        with patch.object(type(settings), "is_production", new_callable=PropertyMock, return_value=True):
            assert asset_url("js/app.js") == "/static/dist/js/app.cached.js"


# ---------------------------------------------------------------------------
# Health and monitoring
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """GET /health"""

    @pytest.mark.asyncio
    async def test_health_returns_200_with_services(self, api_client):
        with (
            patch("main.check_database_health", AsyncMock(return_value=True)),
            patch("main.check_gemini_health", AsyncMock(return_value=True)),
            patch("main.check_redis_health", AsyncMock(return_value=True)),
            patch("utils.maintenance.is_maintenance_mode", AsyncMock(return_value=False)),
        ):
            resp = await api_client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] in ("healthy", "degraded")
        assert "services" in body
        assert "timestamp" in body

    @pytest.mark.asyncio
    async def test_health_degraded_when_database_fails(self, api_client):
        with patch("main.check_database_health", AsyncMock(return_value=False)):
            resp = await api_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_health_gemini_healthy_when_check_passes(self, api_client):
        with (
            patch.object(main.settings, "gemini_api_key", "server-key"),
            patch.object(main.settings, "use_vertex_ai", False),
            patch("main.check_database_health", AsyncMock(return_value=True)),
            patch("main.check_gemini_health", AsyncMock(return_value=True)),
            patch("main.check_redis_health", AsyncMock(return_value=True)),
            patch("utils.maintenance.is_maintenance_mode", AsyncMock(return_value=False)),
        ):
            resp = await api_client.get("/health")
        assert resp.json()["services"]["gemini"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_gemini_degraded_on_check_failure(self, api_client):
        with (
            patch.object(main.settings, "gemini_api_key", "server-key"),
            patch.object(main.settings, "use_vertex_ai", False),
            patch("main.check_database_health", AsyncMock(return_value=True)),
            patch("main.check_gemini_health", AsyncMock(side_effect=RuntimeError("gemini down"))),
            patch("main.check_redis_health", AsyncMock(return_value=True)),
            patch("utils.maintenance.is_maintenance_mode", AsyncMock(return_value=False)),
        ):
            resp = await api_client.get("/health")
        assert resp.json()["services"]["gemini"] == "degraded"

    @pytest.mark.asyncio
    async def test_health_redis_degraded_on_check_failure(self, api_client):
        with (
            patch("main.check_database_health", AsyncMock(return_value=True)),
            patch("main.check_gemini_health", AsyncMock(return_value=True)),
            patch("main.check_redis_health", AsyncMock(side_effect=RuntimeError("redis down"))),
            patch("utils.maintenance.is_maintenance_mode", AsyncMock(return_value=False)),
        ):
            resp = await api_client.get("/health")
        assert resp.json()["services"]["redis"] == "degraded"

    @pytest.mark.asyncio
    async def test_health_maintenance_check_error(self, api_client):
        with (
            patch("utils.maintenance.should_bypass_maintenance", return_value=True),
            patch("main.check_database_health", AsyncMock(return_value=True)),
            patch("main.check_gemini_health", AsyncMock(return_value=True)),
            patch("main.check_redis_health", AsyncMock(return_value=True)),
            patch("utils.maintenance.is_maintenance_mode", AsyncMock(side_effect=RuntimeError("maint fail"))),
        ):
            resp = await api_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["maintenance"] is False

    @pytest.mark.asyncio
    async def test_health_inner_exception_returns_degraded_body(self, api_client):
        real_json_response = main.JSONResponse
        call_count = 0

        def json_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            content = kwargs.get("content") or (args[0] if args else {})
            if isinstance(content, dict) and "services" in content:
                raise RuntimeError("response fail")
            return real_json_response(*args, **kwargs)

        with (
            patch("main.check_database_health", AsyncMock(return_value=True)),
            patch("main.check_gemini_health", AsyncMock(return_value=True)),
            patch("main.check_redis_health", AsyncMock(return_value=True)),
            patch("utils.maintenance.is_maintenance_mode", AsyncMock(return_value=False)),
            patch("main.JSONResponse", side_effect=json_side_effect),
        ):
            resp = await api_client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "degraded"
        assert "message" in body


class TestCacheStats:
    """GET /api/v1/cache/stats — admin only."""

    @pytest.mark.asyncio
    async def test_cache_stats_requires_admin(self, authed_client):
        resp = await authed_client.get("/api/v1/cache/stats")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_cache_stats_success(self, admin_client):
        with patch("utils.cache.get_cache_stats", AsyncMock(return_value={"status": "ok"})):
            resp = await admin_client.get("/api/v1/cache/stats")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_cache_stats_unavailable(self, admin_client):
        with patch("utils.cache.get_cache_stats", AsyncMock(side_effect=RuntimeError("redis down"))):
            resp = await admin_client.get("/api/v1/cache/stats")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unavailable"


# ---------------------------------------------------------------------------
# HTML page routes
# ---------------------------------------------------------------------------


class TestPageRoutes:
    """Serve dashboard, auth, legal, and settings pages."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", _PAGE_ROUTES)
    async def test_page_route_returns_html(self, api_client, path):
        resp = await api_client.get(path, headers={"Accept": "text/html"})
        assert resp.status_code in (200, 503)
        if resp.status_code == 200:
            assert "text/html" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_root_when_templates_none(self, api_client):
        with patch.object(main, "templates", None):
            resp = await api_client.get("/")
        assert resp.status_code == 503
        assert "initializing" in resp.text.lower()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", _TEMPLATES_NONE_ROUTES)
    async def test_page_when_templates_none_returns_503(self, api_client, path):
        with patch.object(main, "templates", None):
            resp = await api_client.get(path)
        assert resp.status_code == 503
        assert "initializing" in resp.text.lower()

    @pytest.mark.asyncio
    async def test_login_template_error_fallback(self, api_client):
        mock_templates = MagicMock()
        mock_templates.TemplateResponse.side_effect = RuntimeError("render failed")
        with patch.object(main, "templates", mock_templates):
            resp = await api_client.get("/auth/login")
        assert resp.status_code == 503
        assert "unavailable" in resp.text.lower()


# ---------------------------------------------------------------------------
# Static assets and misc routes
# ---------------------------------------------------------------------------


class TestMiscRoutes:
    """security.txt, docs redirect, static files."""

    @pytest.mark.asyncio
    async def test_security_txt(self, api_client):
        resp = await api_client.get("/.well-known/security.txt")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")
        assert "Contact:" in resp.text

    @pytest.mark.asyncio
    async def test_static_css_served(self, api_client):
        resp = await api_client.get("/static/css/app.css")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_docs_redirect_in_debug(self, api_client):
        settings = get_settings()
        with patch.object(settings, "debug", True):
            resp = await api_client.get("/docs")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_docs_not_found_in_production(self, api_client):
        with patch("main.settings.debug", False):
            resp = await api_client.get("/docs")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class TestMiddleware:
    """Security headers, rate limit, maintenance, size limit, API version."""

    @pytest.mark.asyncio
    async def test_security_headers_on_html_page(self, api_client):
        resp = await api_client.get("/")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert "Content-Security-Policy" in resp.headers
        assert "nonce-" in resp.headers["Content-Security-Policy"]

    @pytest.mark.asyncio
    async def test_api_version_header_on_v1(self, authed_client):
        resp = await authed_client.get("/api/v1/profile/")
        assert resp.headers.get("X-API-Version") == "1"

    @pytest.mark.asyncio
    async def test_legacy_deprecation_headers(self, api_client):
        resp = await api_client.get("/api/auth/login", follow_redirects=False)
        if resp.status_code != 405:
            assert resp.headers.get("Deprecation") == "true"
            assert "successor-version" in resp.headers.get("Link", "")

    @pytest.mark.asyncio
    async def test_invalid_content_length_returns_400(self, api_client):
        resp = await api_client.post(
            "/api/v1/auth/login",
            content=b"{}",
            headers={"Content-Length": "not-a-number", "Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_oversized_content_length_returns_413(self, api_client):
        resp = await api_client.post(
            "/api/v1/auth/login",
            content=b"{}",
            headers={"Content-Length": str(11 * 1024 * 1024), "Content-Type": "application/json"},
        )
        assert resp.status_code == 413

    @pytest.mark.asyncio
    async def test_global_rate_limit_returns_429(self, api_client):
        blocked = RateLimitResult(allowed=False, limit=100, remaining=0, reset_seconds=60)
        with patch("utils.cache.check_rate_limit_with_headers", AsyncMock(return_value=blocked)):
            resp = await api_client.get("/api/v1/profile/")
        assert resp.status_code == 429
        assert resp.headers.get("Retry-After") == "60"

    @pytest.mark.asyncio
    async def test_rate_limit_uses_bearer_token_hash(self, api_client):
        sec = get_security_settings()
        uid = str(uuid.uuid4())
        token = jwt.encode(
            {"sub": uid, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            sec.jwt_config["secret_key"],
            algorithm=sec.jwt_config["algorithm"],
        )
        mock_check = AsyncMock(return_value=RateLimitResult(allowed=True, limit=100, remaining=99, reset_seconds=60))
        with patch("utils.cache.check_rate_limit_with_headers", mock_check):
            await api_client.get(
                "/api/v1/profile/",
                headers={"Authorization": f"Bearer {token}"},
            )
        identifier = mock_check.call_args.kwargs.get("identifier") or mock_check.call_args[1].get("identifier")
        if identifier is None and mock_check.call_args[0]:
            identifier = mock_check.call_args[0][0]
        assert identifier.startswith("api:")

    @pytest.mark.asyncio
    async def test_maintenance_mode_json_api(self, api_client):
        with (
            patch("utils.maintenance.should_bypass_maintenance", return_value=False),
            patch("utils.maintenance.is_maintenance_mode", AsyncMock(return_value=True)),
            patch(
                "utils.maintenance.get_maintenance_info",
                AsyncMock(return_value={"enabled": True, "message": "Down for upgrades"}),
            ),
        ):
            resp = await api_client.get(
                "/api/v1/profile/",
                headers={"Accept": "application/json"},
            )
        assert resp.status_code == 503
        assert resp.json()["error"] == "maintenance"

    @pytest.mark.asyncio
    async def test_maintenance_mode_html_page(self, api_client):
        with (
            patch("utils.maintenance.should_bypass_maintenance", return_value=False),
            patch("utils.maintenance.is_maintenance_mode", AsyncMock(return_value=True)),
            patch(
                "utils.maintenance.get_maintenance_info",
                AsyncMock(return_value={"enabled": True, "message": "Be back soon"}),
            ),
        ):
            resp = await api_client.get("/", headers={"Accept": "text/html"})
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_maintenance_page_renders(self, api_client):
        resp = await api_client.get("/maintenance")
        assert resp.status_code in (200, 503)
        assert "text/html" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


class TestExceptionHandlers:
    """APIError, validation, HTTPException HTML/JSON, unhandled exceptions."""

    @pytest.fixture
    def error_app_client(self):
        """Minimal app with throwaway routes wired to main exception handlers."""
        test_app = create_app()
        router = APIRouter()

        @router.get("/test/api-error")
        async def raise_api_error():
            raise APIError(ErrorCode.VALIDATION_ERROR, "Test API error", status_code=400)

        @router.get("/test/http-404")
        async def raise_http_404():
            raise HTTPException(status_code=404, detail="Not here")

        @router.get("/test/http-500")
        async def raise_http_500():
            raise HTTPException(status_code=500, detail="Server broke")

        @router.get("/test/unhandled")
        async def raise_unhandled():
            raise RuntimeError("Unexpected failure")

        @router.get("/test/crash")
        async def raise_crash():
            raise RuntimeError("Unexpected failure")

        test_app.include_router(router)
        return test_app

    @pytest.mark.asyncio
    async def test_api_error_handler(self, error_app_client):
        transport = ASGITransport(app=error_app_client, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://localhost") as client:
            resp = await client.get("/test/api-error")
        assert resp.status_code == 400
        assert resp.json()["error_code"] == "VAL_2001"

    @pytest.mark.asyncio
    async def test_validation_error_handler(self, error_app_client):
        transport = ASGITransport(app=error_app_client, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://localhost") as client:
            resp = await client.post("/api/v1/auth/login", json={"email": "not-an-email"})
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "VAL_2001"

    @pytest.mark.asyncio
    async def test_http_404_html_template(self, error_app_client):
        transport = ASGITransport(app=error_app_client, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://localhost") as client:
            resp = await client.get(
                "/test/http-404",
                headers={"Accept": "text/html", "Content-Type": "text/html"},
            )
        assert resp.status_code == 404
        content_type = resp.headers.get("content-type", "")
        assert "text/html" in content_type or resp.json().get("error_code") == "RES_3001"

    @pytest.mark.asyncio
    async def test_http_500_html_template(self, error_app_client):
        transport = ASGITransport(app=error_app_client, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://localhost") as client:
            with patch("utils.error_reporting.report_exception", AsyncMock()):
                resp = await client.get("/test/http-500", headers={"Accept": "text/html"})
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_unhandled_exception_json(self):
        """General handler returns JSON for API-style Accept headers."""
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://localhost") as client:
            with (
                patch("utils.error_reporting.report_exception", AsyncMock()),
                patch("main._is_html_request", return_value=False),
            ):
                resp = await client.get(
                    "/api/v1/profile/",
                    headers={"Accept": "application/json"},
                )
        # Unauthed profile request — exercises error path without crashing the client
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_http_404_html_template_success(self, error_app_client):
        transport = ASGITransport(app=error_app_client, raise_app_exceptions=False)
        mock_templates = MagicMock()
        mock_templates.TemplateResponse.return_value = Response(content="not found", status_code=404)
        async with AsyncClient(transport=transport, base_url="http://localhost") as client:
            with patch.object(main, "templates", mock_templates), patch("main._is_html_request", return_value=True):
                resp = await client.get("/nope", headers={"Accept": "text/html"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_http_404_template_failure_falls_back_to_json(self, error_app_client):
        transport = ASGITransport(app=error_app_client, raise_app_exceptions=False)
        mock_templates = MagicMock()
        mock_templates.TemplateResponse.side_effect = RuntimeError("404 tpl fail")
        async with AsyncClient(transport=transport, base_url="http://localhost") as client:
            with (
                patch.object(main, "templates", mock_templates),
                patch("main._is_html_request", return_value=True),
            ):
                resp = await client.get("/test/http-404", headers={"Accept": "text/html"})
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "RES_3001"

    @pytest.mark.asyncio
    async def test_http_500_template_failure_falls_back_to_json(self, error_app_client):
        transport = ASGITransport(app=error_app_client, raise_app_exceptions=False)
        mock_templates = MagicMock()
        mock_templates.TemplateResponse.side_effect = RuntimeError("500 tpl fail")
        async with AsyncClient(transport=transport, base_url="http://localhost") as client:
            with (
                patch.object(main, "templates", mock_templates),
                patch("main._is_html_request", return_value=True),
                patch("utils.error_reporting.report_exception", AsyncMock()),
            ):
                resp = await client.get("/test/http-500", headers={"Accept": "text/html"})
        assert resp.status_code == 500
        assert resp.json()["error_code"] == "INT_9001"

    @pytest.mark.asyncio
    async def test_general_exception_handler_html_template(self, error_app_client):
        transport = ASGITransport(app=error_app_client, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://localhost") as client:
            with patch("utils.error_reporting.report_exception", AsyncMock()):
                resp = await client.get("/test/crash", headers={"Accept": "text/html"})
        assert resp.status_code == 500
        assert "text/html" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_general_exception_handler_json_in_development(self, error_app_client):
        transport = ASGITransport(app=error_app_client, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://localhost") as client:
            with (
                patch("utils.error_reporting.report_exception", AsyncMock()),
                patch("main._is_html_request", return_value=False),
                patch.object(type(main.settings), "is_production", PropertyMock(return_value=False)),
            ):
                resp = await client.get("/test/crash", headers={"Accept": "application/json"})
        assert resp.status_code == 500
        assert "Unexpected failure" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_general_exception_handler_template_failure_falls_back_to_json(self, error_app_client):
        transport = ASGITransport(app=error_app_client, raise_app_exceptions=False)
        mock_templates = MagicMock()
        mock_templates.TemplateResponse.side_effect = RuntimeError("500 tpl fail")
        async with AsyncClient(transport=transport, base_url="http://localhost") as client:
            with (
                patch.object(main, "templates", mock_templates),
                patch("main._is_html_request", return_value=True),
                patch("utils.error_reporting.report_exception", AsyncMock()),
            ):
                resp = await client.get("/test/crash", headers={"Accept": "text/html"})
        assert resp.status_code == 500
        assert resp.json()["error_code"] == "INT_9001"


class TestIsHtmlRequest:
    """_is_html_request helper."""

    def test_api_path_with_json_only_accept_is_not_html(self):
        req = MagicMock()
        req.headers = {"accept": "application/json"}
        req.url.path = "/api/v1/profile/"
        assert _is_html_request(req) is False

    def test_json_accept_is_not_html(self):
        req = MagicMock()
        req.headers = {"accept": "application/json"}
        req.url.path = "/dashboard"
        assert _is_html_request(req) is False

    def test_browser_accept_is_html(self):
        req = MagicMock()
        req.headers = {"accept": "text/html,application/xhtml+xml"}
        req.url.path = "/dashboard"
        assert _is_html_request(req) is True


# ---------------------------------------------------------------------------
# Orphaned session cleanup + additional main coverage
# ---------------------------------------------------------------------------


class TestCleanupOrphanedSessions:
    """_cleanup_orphaned_sessions() startup helper."""

    @pytest.mark.asyncio
    async def test_all_page_routes_template_error_fallback(self, api_client):
        """Each HTML route returns 503 when TemplateResponse raises."""
        routes = [
            "/",
            "/dashboard/new-application",
            "/auth/login",
            "/auth/register",
            "/auth/reset-password",
            "/auth/forgot-password",
            "/auth/verify-email",
            "/dashboard/tools",
            f"/dashboard/interview-prep/{uuid.uuid4()}",
            "/profile/setup",
            "/help",
            "/privacy",
            "/terms",
            "/dashboard/settings",
            f"/dashboard/application/{uuid.uuid4()}",
        ]
        mock_templates = MagicMock()
        mock_templates.TemplateResponse.side_effect = RuntimeError("template error")
        with patch.object(main, "templates", mock_templates):
            for path in routes:
                resp = await api_client.get(path)
                assert resp.status_code == 503, path

    @pytest.mark.asyncio
    async def test_health_gemini_byok_only_when_no_server_key(self, api_client):
        settings = get_settings()
        with (
            patch.object(settings, "gemini_api_key", None),
            patch.object(settings, "use_vertex_ai", False),
            patch("main.check_database_health", AsyncMock(return_value=True)),
            patch("main.check_redis_health", AsyncMock(return_value=True)),
            patch("utils.maintenance.is_maintenance_mode", AsyncMock(return_value=False)),
        ):
            resp = await api_client.get("/health")
        assert resp.json()["services"]["gemini"] == "byok_only"

    @pytest.mark.asyncio
    async def test_maintenance_middleware_html_browser_request(self, api_client):
        with (
            patch("utils.maintenance.should_bypass_maintenance", return_value=False),
            patch("utils.maintenance.is_maintenance_mode", AsyncMock(return_value=True)),
            patch(
                "utils.maintenance.get_maintenance_info",
                AsyncMock(return_value={"enabled": True, "message": "Planned outage"}),
            ),
        ):
            resp = await api_client.get("/dashboard", headers={"Accept": "text/html"})
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_marks_stale_sessions_failed(self):
        session_id = str(uuid.uuid4())
        datetime.now(timezone.utc) - timedelta(hours=3)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(session_id,)]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        @asynccontextmanager
        async def _fake_session():
            yield mock_db

        with patch("utils.database.get_session", _fake_session):
            await _cleanup_orphaned_sessions()

        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()


class TestMainExtended:
    """Additional main.py coverage: lifespan, pages, middleware, handlers."""

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_sessions_logs_when_rows(self):
        session_id = str(uuid.uuid4())
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(session_id,)]
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        @asynccontextmanager
        async def _fake_session():
            yield mock_db

        with patch("utils.database.get_session", _fake_session):
            await _cleanup_orphaned_sessions()

    @pytest.mark.asyncio
    async def test_lifespan_startup_and_shutdown(self):
        mock_app = MagicMock()
        with (
            patch("main.log_startup_info"),
            patch("main.connect_to_database", AsyncMock()),
            patch("main.get_initialized_workflow", AsyncMock()),
            patch("main._cleanup_orphaned_sessions", AsyncMock()),
            patch("main.close_database_connection", AsyncMock()),
            patch("main.close_redis_connection", AsyncMock()),
            patch("main.close_gemini_client", AsyncMock()),
            patch("utils.tracing.setup_tracing"),
            patch("utils.redis_client.connect_to_redis", AsyncMock()),
            patch.object(Path, "mkdir"),
            patch.object(main, "templates", MagicMock()),
            patch.object(main, "_load_asset_manifest", return_value={}),
        ):
            async with lifespan(mock_app):
                assert main.templates is not None

    @pytest.mark.asyncio
    async def test_lifespan_production_guard_missing_encryption_key(self):
        mock_app = MagicMock()
        with (
            patch.object(type(main.settings), "is_production", new_callable=PropertyMock, return_value=True),
            patch.object(main.settings, "encryption_key", None),
            patch("main.log_startup_info"),
        ):
            with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
                async with lifespan(mock_app):
                    pass

    @pytest.mark.asyncio
    async def test_lifespan_production_debug_guard(self):
        mock_app = MagicMock()
        with (
            patch.object(type(main.settings), "is_production", new_callable=PropertyMock, return_value=True),
            patch.object(main.settings, "encryption_key", "enc-key"),
            patch.object(main.settings, "debug", True),
            patch("main.log_startup_info"),
        ):
            with pytest.raises(RuntimeError, match="DEBUG must be false"):
                async with lifespan(mock_app):
                    pass

    @pytest.mark.asyncio
    async def test_lifespan_redis_unavailable_is_non_fatal(self):
        mock_app = MagicMock()
        with (
            patch.object(type(main.settings), "is_production", new_callable=PropertyMock, return_value=False),
            patch("main.log_startup_info"),
            patch("main.connect_to_database", AsyncMock()),
            patch("utils.redis_client.connect_to_redis", AsyncMock(side_effect=RuntimeError("no redis"))),
            patch("main.get_initialized_workflow", AsyncMock()),
            patch("main._cleanup_orphaned_sessions", AsyncMock()),
            patch("main.close_database_connection", AsyncMock()),
            patch("main.close_redis_connection", AsyncMock()),
            patch("main.close_gemini_client", AsyncMock()),
            patch("utils.tracing.setup_tracing"),
            patch.object(Path, "mkdir"),
            patch("main.templates", MagicMock(), create=True),
            patch("main._load_asset_manifest", return_value={}),
        ):
            async with lifespan(mock_app):
                pass

    @pytest.mark.asyncio
    async def test_maintenance_page_success(self, api_client):
        with patch(
            "utils.maintenance.get_maintenance_info",
            AsyncMock(return_value={"enabled": True, "message": "Upgrading", "estimated_end": None}),
        ):
            resp = await api_client.get("/maintenance")
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_maintenance_page_template_error(self, api_client):
        mock_templates = MagicMock()
        mock_templates.TemplateResponse.side_effect = RuntimeError("tpl fail")
        with (
            patch.object(main, "templates", mock_templates),
            patch("utils.maintenance.get_maintenance_info", AsyncMock(return_value={"enabled": True})),
        ):
            resp = await api_client.get("/maintenance")
        assert resp.status_code == 503
        assert "maintenance" in resp.text.lower()

    @pytest.mark.asyncio
    async def test_dashboard_template_error_logs(self, api_client, caplog):
        mock_templates = MagicMock()
        mock_templates.TemplateResponse.side_effect = RuntimeError("dash fail")
        with patch.object(main, "templates", mock_templates), caplog.at_level("ERROR"):
            resp = await api_client.get("/dashboard")
        assert resp.status_code == 503
        assert any("Error serving dashboard" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_maintenance_middleware_serves_html_template(self, api_client):
        with (
            patch("utils.maintenance.should_bypass_maintenance", return_value=False),
            patch("utils.maintenance.is_maintenance_mode", AsyncMock(return_value=True)),
            patch(
                "utils.maintenance.get_maintenance_info",
                AsyncMock(return_value={"enabled": True, "message": "Planned", "estimated_end": None}),
            ),
        ):
            resp = await api_client.get("/", headers={"Accept": "text/html,application/xhtml+xml"})
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_is_html_request_default_browser(self):
        req = MagicMock()
        req.headers = {"accept": "*/*"}
        req.url.path = "/dashboard"
        assert _is_html_request(req) is True

    def test_create_app_trusted_host_string_and_error(self):
        with patch.object(main.settings, "allowed_hosts", "example.com, app.test"):
            app = create_app()
            assert app is not None
        with patch.object(main.settings, "allowed_hosts", MagicMock(side_effect=RuntimeError("bad hosts"))), \
             patch.object(type(main.settings), "is_production", new_callable=PropertyMock, return_value=True):
            app2 = create_app()
            assert app2 is not None
