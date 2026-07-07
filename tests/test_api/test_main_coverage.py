"""
Coverage tests for main.py — lifespan, middleware branches, health checks, page routes.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import main
from main import (
    _cleanup_orphaned_sessions,
    _is_html_request,
    _load_asset_manifest,
    create_app,
    lifespan,
)


class TestMainLifespan:
    @pytest.mark.asyncio
    async def test_lifespan_startup_and_shutdown(self) -> None:
        app = create_app()
        with (
            patch.object(main.settings, "debug", True),
            patch("main.connect_to_database", AsyncMock()),
            patch("main.get_initialized_workflow", AsyncMock()),
            patch("main._cleanup_orphaned_sessions", AsyncMock()),
            patch("utils.redis_client.connect_to_redis", AsyncMock()),
            patch("utils.tracing.setup_tracing"),
            patch.object(Path, "mkdir"),
        ):
            async with lifespan(app):
                assert main.templates is not None

    @pytest.mark.asyncio
    async def test_lifespan_production_encryption_key_required(self) -> None:
        app = create_app()
        with (
            patch.object(main.settings, "debug", False),
            patch.object(main.settings, "testing", False),
            patch.object(main.settings, "encryption_key", None),
        ):
            with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
                async with lifespan(app):
                    pass

    @pytest.mark.asyncio
    async def test_lifespan_production_debug_forbidden(self) -> None:
        app = create_app()
        with (
            patch.object(type(main.settings), "is_production", PropertyMock(return_value=True)),
            patch.object(main.settings, "debug", True),
            patch.object(main.settings, "encryption_key", "dummy"),
            patch.object(main.settings, "redis_url", "rediss://localhost:6379/0"),
        ):
            with pytest.raises(RuntimeError, match="DEBUG must be false"):
                async with lifespan(app):
                    pass

    @pytest.mark.asyncio
    async def test_lifespan_production_redis_required(self) -> None:
        app = create_app()
        with (
            patch.object(main.settings, "debug", False),
            patch.object(main.settings, "testing", False),
            patch.object(main.settings, "encryption_key", "dummy"),
            patch.object(main.settings, "redis_url", ""),
        ):
            with pytest.raises(RuntimeError, match="REDIS_URL is not set"):
                async with lifespan(app):
                    pass

    @pytest.mark.asyncio
    async def test_lifespan_production_redis_tls_required(self) -> None:
        app = create_app()
        with (
            patch.object(main.settings, "debug", False),
            patch.object(main.settings, "testing", False),
            patch.object(main.settings, "encryption_key", "dummy"),
            patch.object(main.settings, "redis_url", "redis://localhost:6379/0"),
        ):
            with pytest.raises(RuntimeError, match="rediss://"):
                async with lifespan(app):
                    pass

    @pytest.mark.asyncio
    async def test_lifespan_directory_permission_error(self) -> None:
        app = create_app()
        with (
            patch.object(main.settings, "debug", True),
            patch.object(Path, "mkdir", side_effect=PermissionError("denied")),
        ):
            with pytest.raises(PermissionError):
                async with lifespan(app):
                    pass

    @pytest.mark.asyncio
    async def test_lifespan_directory_os_error(self) -> None:
        app = create_app()
        with (
            patch.object(main.settings, "debug", True),
            patch.object(Path, "mkdir", side_effect=OSError("disk full")),
        ):
            with pytest.raises(OSError, match="disk full"):
                async with lifespan(app):
                    pass

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_error_logged(self) -> None:
        app = create_app()
        with (
            patch.object(main.settings, "debug", True),
            patch("main.connect_to_database", AsyncMock()),
            patch("main.get_initialized_workflow", AsyncMock()),
            patch("main._cleanup_orphaned_sessions", AsyncMock()),
            patch("utils.redis_client.connect_to_redis", AsyncMock()),
            patch("utils.tracing.setup_tracing"),
            patch.object(Path, "mkdir"),
            patch("main.close_database_connection", AsyncMock(side_effect=RuntimeError("shutdown fail"))),
            patch("main.close_redis_connection", AsyncMock()),
            patch("main.close_gemini_client", AsyncMock()),
        ):
            async with lifespan(app):
                pass

    @pytest.mark.asyncio
    async def test_lifespan_redis_unavailable_non_fatal(self) -> None:
        app = create_app()
        with (
            patch.object(main.settings, "debug", True),
            patch("main.connect_to_database", AsyncMock()),
            patch("main.get_initialized_workflow", AsyncMock()),
            patch("main._cleanup_orphaned_sessions", AsyncMock()),
            patch("utils.redis_client.connect_to_redis", AsyncMock(side_effect=RuntimeError("no redis"))),
            patch("utils.tracing.setup_tracing"),
            patch.object(Path, "mkdir"),
        ):
            async with lifespan(app):
                pass

    @pytest.mark.asyncio
    async def test_lifespan_orphan_cleanup_failure_non_fatal(self) -> None:
        app = create_app()
        with (
            patch.object(main.settings, "debug", True),
            patch("main.connect_to_database", AsyncMock()),
            patch("main.get_initialized_workflow", AsyncMock()),
            patch("main._cleanup_orphaned_sessions", AsyncMock(side_effect=RuntimeError("cleanup fail"))),
            patch("utils.redis_client.connect_to_redis", AsyncMock()),
            patch("utils.tracing.setup_tracing"),
            patch.object(Path, "mkdir"),
        ):
            async with lifespan(app):
                pass


class TestMainMiddleware:
    @pytest.mark.asyncio
    async def test_maintenance_middleware_html_with_templates(self, api_client) -> None:
        from starlette.responses import Response as StarletteResponse

        mock_response = StarletteResponse(content=b"maintenance", status_code=503)
        with (
            patch("utils.maintenance.should_bypass_maintenance", return_value=False),
            patch("utils.maintenance.is_maintenance_mode", AsyncMock(return_value=True)),
            patch(
                "utils.maintenance.get_maintenance_info",
                AsyncMock(return_value={"enabled": True, "message": "Down", "estimated_end": "soon"}),
            ),
            patch.object(main, "templates") as mock_tpl,
        ):
            mock_tpl.TemplateResponse.return_value = mock_response
            resp = await api_client.get("/dashboard", headers={"Accept": "text/html"})
        assert resp.status_code == 503


class TestMainHealthAndPages:
    @pytest.mark.asyncio
    async def test_health_gemini_degraded_on_check_failure(self, api_client) -> None:
        with (
            patch("utils.maintenance.should_bypass_maintenance", return_value=True),
            patch.object(main.settings, "gemini_api_key", "test-key"),
            patch.object(main.settings, "use_vertex_ai", False),
            patch("main.check_database_health", AsyncMock(return_value=True)),
            patch("main.check_gemini_health", AsyncMock(side_effect=RuntimeError("gemini down"))),
            patch("main.check_redis_health", AsyncMock(return_value=True)),
            patch("utils.maintenance.is_maintenance_mode", AsyncMock(return_value=False)),
        ):
            resp = await api_client.get("/health")
        assert resp.json()["services"]["gemini"] == "degraded"

    @pytest.mark.asyncio
    async def test_health_redis_degraded_on_check_failure(self, api_client) -> None:
        with (
            patch("main.check_database_health", AsyncMock(return_value=True)),
            patch("main.check_redis_health", AsyncMock(side_effect=RuntimeError("redis down"))),
            patch("utils.maintenance.is_maintenance_mode", AsyncMock(return_value=False)),
        ):
            resp = await api_client.get("/health")
        assert resp.json()["services"]["redis"] == "degraded"

    @pytest.mark.asyncio
    async def test_health_maintenance_check_failure(self, api_client) -> None:
        with (
            patch("main.check_database_health", AsyncMock(return_value=True)),
            patch("main.check_redis_health", AsyncMock(return_value=True)),
            patch("utils.maintenance.should_bypass_maintenance", return_value=True),
            patch("utils.maintenance.is_maintenance_mode", AsyncMock(side_effect=RuntimeError("maint err"))),
        ):
            resp = await api_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["maintenance"] is False

    @pytest.mark.asyncio
    async def test_health_outer_exception_returns_degraded(self, api_client) -> None:
        with patch("main.check_database_health", AsyncMock(side_effect=RuntimeError("fatal"))):
            resp = await api_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_dashboard_templates_none(self, api_client) -> None:
        with patch.object(main, "templates", None):
            resp = await api_client.get("/dashboard")
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_maintenance_page_success(self, api_client) -> None:
        with patch(
            "utils.maintenance.get_maintenance_info",
            AsyncMock(return_value={"enabled": False, "message": None, "estimated_end": None}),
        ):
            resp = await api_client.get("/maintenance")
        assert resp.status_code in (200, 503)

    @pytest.mark.asyncio
    async def test_maintenance_page_templates_none(self, api_client) -> None:
        with patch.object(main, "templates", None):
            resp = await api_client.get("/maintenance")
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_maintenance_page_template_error(self, api_client) -> None:
        mock_templates = MagicMock()
        mock_templates.TemplateResponse.side_effect = RuntimeError("tpl fail")
        with (
            patch.object(main, "templates", mock_templates),
            patch("utils.maintenance.get_maintenance_info", AsyncMock(return_value={"enabled": True})),
        ):
            resp = await api_client.get("/maintenance")
        assert resp.status_code == 503


class TestMainExceptionHandlers:
    @pytest.mark.asyncio
    async def test_http_404_html_template_rendered(self) -> None:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://localhost") as client:
            resp = await client.get("/nonexistent-page-xyz", headers={"Accept": "text/html"})
        assert resp.status_code == 404

    def test_is_html_request_default_browser(self) -> None:
        req = MagicMock()
        req.headers = {"accept": "*/*"}
        req.url.path = "/dashboard"
        assert _is_html_request(req) is True


class TestMainTrustedHostFallback:
    def test_trusted_host_middleware_error_uses_production_fallback(self) -> None:
        from fastapi import FastAPI
        from starlette.middleware.trustedhost import TrustedHostMiddleware

        real_add = FastAPI.add_middleware
        trusted_host_attempts = 0

        def _add_middleware(self, middleware_class, *args, **kwargs):
            nonlocal trusted_host_attempts
            if middleware_class is TrustedHostMiddleware:
                trusted_host_attempts += 1
                if trusted_host_attempts == 1:
                    raise RuntimeError("trusted host config failed")
            return real_add(self, middleware_class, *args, **kwargs)

        with (
            patch.object(FastAPI, "add_middleware", _add_middleware),
            patch.object(main.settings, "allowed_hosts", ["example.com"]),
            patch.object(type(main.settings), "is_production", PropertyMock(return_value=True)),
        ):
            app = create_app()
        assert app is not None
        assert trusted_host_attempts == 2


class TestMainEntryPoint:
    def test_main_block_invokes_uvicorn(self) -> None:
        import ast
        import uvicorn

        main_path = Path(main.__file__)
        tree = ast.parse(main_path.read_text(), filename=str(main_path))
        main_guard = tree.body[-1]
        assert isinstance(main_guard, ast.If)
        code = compile(
            ast.Module(body=main_guard.body, type_ignores=[]),
            str(main_path),
            "exec",
        )

        with patch.object(uvicorn, "run") as mock_run:
            namespace = {**vars(main), "uvicorn": uvicorn}
            exec(code, namespace)

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["access_log"] is False
        assert call_kwargs["log_config"] is None


class TestMainUtilities:
    def test_load_asset_manifest_missing_file(self, tmp_path: Path) -> None:
        with patch.object(main, "_MANIFEST_PATH", tmp_path / "missing.json"):
            assert _load_asset_manifest() == {}

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_sessions_no_rows(self) -> None:
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        @asynccontextmanager
        async def _fake():
            yield mock_db

        with patch("utils.database.get_session", _fake):
            await _cleanup_orphaned_sessions()
        mock_db.commit.assert_called_once()
