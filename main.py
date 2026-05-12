"""
Main FastAPI application for ApplyPilot.
This module sets up the web server, API routes, middleware, and application lifecycle.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any, Dict
import uvicorn
import json
from utils.bcrypt_patch import apply_bcrypt_patch
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from config.settings import get_settings
from utils.database import (
    connect_to_database,
    check_database_health,
    close_database_connection,
)
from utils.llm_client import check_gemini_health, close_gemini_client
from utils.redis_client import check_redis_health, close_redis_connection
from utils.logging_config import setup_logging, log_startup_info
from utils.request_middleware import RequestLoggingMiddleware, SlowRequestMiddleware
from api.auth import router as auth_router
from api.profile import router as profile_router
from api.applications import router as applications_router
from api.workflow import router as workflow_router
from api.websocket import router as websocket_router
from api.interview_prep import router as interview_prep_router
from api.cv_optimizer import router as cv_optimizer_router
from api.tools import router as tools_router
from api.extension_autofill import router as extension_autofill_router
from api.admin import router as admin_router
from workflows.job_application_workflow import get_initialized_workflow
from utils.json_utils import serialize_object_for_json
from utils.error_responses import APIError, ErrorCode, create_error_response, not_found_error
from utils.logging_config import request_id_var
from utils.error_reporting import report_exception

apply_bcrypt_patch()

# Get settings for logging configuration
settings = get_settings()

# Configure logging — always respect LOG_FORMAT from env, never override it based on DEBUG
setup_logging(
    log_level=settings.log_level,
    log_format=settings.log_format,
    log_dir=settings.log_dir,
    enable_file_logging=settings.log_file_enabled,
    enable_console_logging=True,
    max_bytes=settings.log_max_bytes,
    backup_count=settings.log_backup_count,
    redact_sensitive=settings.log_redact_sensitive,
    app_name="applypilot",
    service_name="applypilot",
    service_version=settings.app_version,
    environment="production" if settings.is_production else "development",
)

logger = logging.getLogger(__name__)

# Global variables
templates: Optional[Jinja2Templates] = None

# =============================================================================
# ASSET MANIFEST (Vite/esbuild content-hashed output)
# =============================================================================

_asset_manifest: Optional[dict] = None
_MANIFEST_PATH = Path("ui/static/dist/manifest.json")


def _load_asset_manifest() -> dict:
    """Load the build manifest. Cached in production; re-read on every request in development."""
    global _asset_manifest
    from config import get_settings as _get_settings
    _settings = _get_settings()
    if _asset_manifest is not None and _settings.is_production:
        return _asset_manifest
    if _MANIFEST_PATH.exists():
        try:
            _asset_manifest = json.loads(_MANIFEST_PATH.read_text())
        except (json.JSONDecodeError, OSError) as manifest_err:
            logger.error("Failed to parse asset manifest at %s: %s", _MANIFEST_PATH, manifest_err)
            _asset_manifest = {}
    else:
        _asset_manifest = {}
    return _asset_manifest


def asset_url(path: str) -> str:
    """Jinja2 global: resolve a static asset to its hashed dist URL.

    In production (after `npm run build`), returns the content-hashed path so
    browsers cache permanently.  Falls back to /static/<path> in development
    when no build has been run.

    Usage in templates: {{ asset_url('js/app.js') }}
    """
    manifest = _load_asset_manifest()
    hashed = manifest.get(path)
    if hashed:
        return f"/static/dist/{hashed}"
    return f"/static/{path}"


def get_analytics_context() -> dict:
    """Get analytics configuration for templates."""
    return {
        "posthog_api_key": settings.posthog_api_key or "",
        "posthog_host": settings.posthog_host,
    }


async def _cleanup_orphaned_sessions() -> None:
    """
    Reset workflow sessions stuck in an active state from a previous server instance.
    Sessions in INITIALIZED or IN_PROGRESS state that are older than 2 hours are
    assumed to be orphaned (no background task is still running for them) and are
    marked as FAILED so users receive clear feedback.
    """
    from datetime import timedelta
    from sqlalchemy import update
    from utils.database import get_session
    from models.database import WorkflowSession

    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    orphaned_statuses = ["initialized", "in_progress"]

    async with get_session() as db:
        result = await db.execute(
            update(WorkflowSession)
            .where(
                WorkflowSession.workflow_status.in_(orphaned_statuses),
                WorkflowSession.processing_start_time < cutoff,
            )
            .values(
                workflow_status="failed",
                error_messages=["Session interrupted by server restart. Please re-submit your job."],
            )
            .returning(WorkflowSession.session_id)
        )
        rows = result.fetchall()
        await db.commit()
        if rows:
            logger.warning(f"Startup: reset {len(rows)} orphaned workflow session(s) to 'failed'")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown tasks."""

    log_startup_info(
        app_name=settings.app_name,
        version=settings.app_version,
        environment="development" if settings.debug else "production",
        debug=settings.debug,
        host=settings.host,
        port=settings.port,
        gemini_model=settings.gemini_model,
        use_vertex_ai=getattr(settings, "use_vertex_ai", False),
        vertex_project=getattr(settings, "vertex_ai_project", None),
        vertex_location=getattr(settings, "vertex_ai_location", "us-central1"),
        database_url=settings.database_url,
        redis_url=settings.redis_url,
        log_level=settings.log_level,
    )
    logger.info("Starting ApplyPilot...")

    # Startup tasks
    try:
        # Validate critical secrets before accepting traffic
        if settings.is_production and not settings.encryption_key:
            logger.critical(
                "ENCRYPTION_KEY is not set in production. Stored BYOK API keys "
                "cannot be decrypted. Set ENCRYPTION_KEY before rotating JWT_SECRET."
            )
            raise RuntimeError(
                "ENCRYPTION_KEY must be set in production — see .env.example"
            )

        if settings.is_production and settings.debug:
            logger.critical("DEBUG=true is set in a production environment. This enables insecure code paths.")
            raise RuntimeError("DEBUG must be false in production — set DEBUG=false in your environment")

        redis_url = getattr(settings, "redis_url", "") or ""
        if settings.is_production and not redis_url:
            raise RuntimeError(
                "REDIS_URL is not set in production. "
                "Redis is required for caching, rate limiting, and JWT revocation. "
                "Set REDIS_URL to a valid rediss:// connection string."
            )
        if settings.is_production and redis_url and not redis_url.startswith("rediss://"):
            logger.critical(
                "REDIS_URL does not use TLS (rediss://) in production. "
                "Redis traffic is unencrypted. Update REDIS_URL to use rediss://."
            )
            raise RuntimeError("REDIS_URL must use rediss:// (TLS) in production")

        # Initialise distributed tracing (no-op if OTel packages not installed)
        from utils.tracing import setup_tracing
        setup_tracing(
            service_name=settings.app_name.lower().replace(" ", "-"),
            service_version=settings.app_version,
            environment="production" if settings.is_production else "development",
        )

        # Create necessary directories with error handling
        for dir_name in ["logs", "uploads", "generated"]:
            try:
                Path(dir_name).mkdir(exist_ok=True)
            except PermissionError:
                logger.error(f"Permission denied creating directory: {dir_name}")
                raise
            except OSError as e:
                logger.error(f"Failed to create directory {dir_name}: {e}", exc_info=True)
                raise

        # Initialize PostgreSQL database connection
        await connect_to_database()
        logger.info("PostgreSQL database connection initialized successfully")

        # Initialize Redis connection
        try:
            from utils.redis_client import connect_to_redis
            await connect_to_redis()
            logger.info("Redis connection initialized successfully")
        except Exception as e:
            logger.warning(f"Redis not available - caching disabled: {e}")

        # Initialize workflow
        await get_initialized_workflow()
        logger.info("Workflow initialized successfully")

        # Initialize templates
        global templates
        templates = Jinja2Templates(directory="ui")
        templates.env.globals["asset_url"] = asset_url
        templates.env.globals["posthog_enabled"] = settings.posthog_enabled
        manifest = _load_asset_manifest()  # Warm the cache at startup
        logger.info("Loaded asset manifest with %d entries", len(manifest))

        # Reset orphaned workflow sessions that were left in a running state
        # (e.g., after a crash or forced restart). Background task sessions
        # that never completed will be marked as failed so users get clear feedback.
        try:
            await _cleanup_orphaned_sessions()
        except Exception as e:
            logger.warning(f"Orphaned session cleanup failed (non-fatal): {e}")

        logger.info("Application startup complete")

    except Exception as e:
        logger.error(f"Startup failed: {e}", exc_info=True)
        raise

    yield

    # Shutdown tasks
    logger.info("Shutting down ApplyPilot...")
    try:
        # Close database connections
        await close_database_connection()

        # Close Redis connections
        await close_redis_connection()

        # Close Gemini connections
        await close_gemini_client()

        logger.info("Application shutdown complete")

    except Exception as e:
        logger.error(f"Shutdown error: {e}", exc_info=True)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    # Custom JSON encoder for handling UUID and datetime
    class CustomJSONResponse(JSONResponse):
        def render(self, content: Any) -> bytes:
            return json.dumps(
                serialize_object_for_json(content),
                ensure_ascii=False,
                allow_nan=False,
                indent=None,
                separators=(",", ":"),
            ).encode("utf-8")

    # Create the FastAPI app
    app = FastAPI(
        title=settings.app_name,
        description=settings.app_description,
        version=settings.app_version,
        docs_url="/api/docs" if settings.debug else None,
        redoc_url="/api/redoc" if settings.debug else None,
        lifespan=lifespan,
        default_response_class=CustomJSONResponse,
    )

    # Configure middleware
    configure_middleware(app)

    # Include API routers
    include_routers(app)

    # Add custom routes
    add_custom_routes(app)

    # Add exception handlers
    add_exception_handlers(app)

    return app


def configure_middleware(app: FastAPI):
    """Configure middleware for the application."""

    # Request logging middleware (should be first to capture all requests)
    app.add_middleware(RequestLoggingMiddleware)

    # Slow request warning middleware
    app.add_middleware(
        SlowRequestMiddleware,
        threshold_ms=settings.slow_request_threshold_ms,
    )
    
    # Security headers middleware
    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        """Add security headers to all responses."""
        import secrets as _secrets

        # Generate a per-request nonce BEFORE calling the route handler so
        # templates can embed it in inline <script> tags via request.state.csp_nonce.
        nonce = _secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce

        response = await call_next(request)

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # XSS protection (legacy, but still useful for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict browser features
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        # HSTS - only in production (Cloud Run provides HTTPS)
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Content Security Policy — nonce-based (no 'unsafe-inline' for scripts or styles).
        # All inline <script> and <style> blocks across all templates carry
        # nonce="{{ request.state.csp_nonce | default('') }}", generated above before
        # call_next() so the template can embed it.
        csp_directives = [
            "default-src 'self'",
            f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net "
            "https://us-assets.i.posthog.com https://eu-assets.i.posthog.com",
            f"style-src 'self' 'nonce-{nonce}' https://fonts.googleapis.com https://cdn.jsdelivr.net",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data: https:",
            "connect-src 'self' wss: https://us.i.posthog.com https://eu.i.posthog.com",
            "frame-src 'none'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
        if settings.is_production:
            csp_directives.append("upgrade-insecure-requests")
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        return response
    
    # X-API-Version header on all /api/v1/ responses
    @app.middleware("http")
    async def api_version_header_middleware(request: Request, call_next):
        """Stamp every /api/v1/ response with the current API version."""
        response = await call_next(request)
        if str(request.url.path).startswith("/api/v1/"):
            response.headers["X-API-Version"] = "1"
        return response

    # Deprecation headers for legacy /api/ routes (non-v1)
    @app.middleware("http")
    async def api_legacy_deprecation_middleware(request: Request, call_next):
        """Warn callers hitting legacy /api/ routes to migrate to /api/v1/."""
        response = await call_next(request)
        path = str(request.url.path)
        if (
            path.startswith("/api/")
            and not path.startswith("/api/v1/")
            and not path.startswith("/api/health")
            and not path.startswith("/api/ws/")
        ):
            v1_path = "/api/v1" + path[4:]
            response.headers["Deprecation"] = "true"
            response.headers["Sunset"] = "Sat, 01 Aug 2026 00:00:00 GMT"
            response.headers["Link"] = f'<{v1_path}>; rel="successor-version"'
        return response

    # Global request body size limit (10 MB for JSON, uploads have per-endpoint limits)
    MAX_REQUEST_BODY_SIZE = 10 * 1024 * 1024  # 10 MB

    @app.middleware("http")
    async def request_size_limit_middleware(request: Request, call_next):
        """Reject requests whose Content-Length header exceeds the global limit."""
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                content_length_int = int(content_length)
            except (ValueError, TypeError):
                return create_error_response(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message="Invalid Content-Length header.",
                    status_code=400,
                )
            if content_length_int > MAX_REQUEST_BODY_SIZE:
                return create_error_response(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message=f"Request body too large. Maximum allowed size is {MAX_REQUEST_BODY_SIZE // (1024 * 1024)} MB.",
                    status_code=413,
                )
        return await call_next(request)

    # API rate limiting middleware
    @app.middleware("http")
    async def api_rate_limit_middleware(request: Request, call_next):
        """Apply rate limiting to API endpoints."""
        from utils.cache import check_rate_limit_with_headers
        
        path = str(request.url.path)
        
        # Only rate limit API endpoints (not static files, health checks, etc.)
        if not path.startswith("/api/"):
            return await call_next(request)
        
        # Skip rate limiting for certain endpoints
        skip_paths = ["/api/health", "/api/ws/", "/api/v1/auth/login", "/api/v1/auth/register"]
        if any(path.startswith(skip) for skip in skip_paths):
            return await call_next(request)
        
        # Get client IP: use the TCP-level peer address (set by Cloud Run/uvicorn)
        # which is not spoofable.  X-Forwarded-For's first entry is client-controlled
        # and must NOT be used for security decisions.
        client_ip = request.client.host if request.client else "unknown"

        # Try to get user ID from Authorization header for more accurate limiting
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            # Use a SHA-256 hash of the token as identifier (more specific than IP)
            import hashlib
            token_hash = hashlib.sha256(auth_header.encode()).hexdigest()[:16]
            identifier = f"api:{token_hash}"
        else:
            identifier = f"api:{client_ip}"
        
        # Rate limit: 100 requests per minute per user/IP
        result = await check_rate_limit_with_headers(
            identifier=identifier,
            limit=100,
            window_seconds=60,
        )
        
        if not result.allowed:
            return create_error_response(
                error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
                message="Too many requests. Please slow down.",
                status_code=429,
                headers={
                    "Retry-After": str(result.reset_seconds),
                    "X-RateLimit-Limit": str(result.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(result.reset_seconds),
                },
            )
        
        # Process request and add rate limit headers to response
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(result.reset_seconds)
        
        return response
    
    # Maintenance mode middleware
    @app.middleware("http")
    async def maintenance_mode_middleware(request: Request, call_next):
        """Check for maintenance mode and return maintenance page if enabled."""
        from utils.maintenance import is_maintenance_mode, should_bypass_maintenance, get_maintenance_info
        
        path = str(request.url.path)
        
        # Allow certain paths to bypass maintenance mode
        if should_bypass_maintenance(path):
            return await call_next(request)
        
        # Check if maintenance mode is enabled
        if await is_maintenance_mode():
            # For API requests, return JSON
            accept = request.headers.get("accept", "")
            if "application/json" in accept or path.startswith("/api/"):
                maintenance_info = await get_maintenance_info()
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "maintenance",
                        "message": maintenance_info.get("message", "Service under maintenance"),
                        "estimated_end": maintenance_info.get("estimated_end"),
                    },
                    headers={"Retry-After": "300"},  # 5 minutes
                )
            
            # For browser requests, serve maintenance page
            if templates is not None:
                maintenance_info = await get_maintenance_info()
                return templates.TemplateResponse(
                    "maintenance.html",
                    {
                        "request": request,
                        "app_name": settings.app_name,
                        "message": maintenance_info.get("message"),
                        "estimated_end": maintenance_info.get("estimated_end"),
                    },
                    status_code=503,
                )
        
        return await call_next(request)

    # CORS middleware
    origins = (
        settings.cors_origins
        if isinstance(settings.cors_origins, list)
        else [settings.cors_origins]
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=settings.cors_credentials,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
    )

    # Trusted Host middleware
    try:
        allowed_hosts = settings.allowed_hosts
        if allowed_hosts:
            # Ensure we have at least one valid host
            if not isinstance(allowed_hosts, list):
                allowed_hosts = [
                    h.strip() for h in str(allowed_hosts).split(",") if h.strip()
                ]

            # Always include localhost and 127.0.0.1 for development
            if "localhost" not in allowed_hosts:
                allowed_hosts.append("localhost")
            if "127.0.0.1" not in allowed_hosts:
                allowed_hosts.append("127.0.0.1")

            # Allow 0.0.0.0 in non-production so browsing directly to
            # http://0.0.0.0:8000 works without a "Invalid host header" error.
            if not settings.is_production and "0.0.0.0" not in allowed_hosts:
                allowed_hosts.append("0.0.0.0")

            logger.info(f"Configuring Trusted Hosts with: {allowed_hosts}")
            app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    except Exception as e:
        logger.error(f"Error configuring TrustedHostMiddleware: {e}", exc_info=True)
        if settings.is_production:
            fallback_hosts = ["localhost", "127.0.0.1"]
            logger.warning(f"Using fallback hosts: {fallback_hosts}")
            app.add_middleware(TrustedHostMiddleware, allowed_hosts=fallback_hosts)


def include_routers(app: FastAPI):
    """Include API routers with versioning."""

    # API v1 routes (current version)
    API_V1_PREFIX = "/api/v1"
    
    app.include_router(auth_router, prefix=f"{API_V1_PREFIX}/auth", tags=["Authentication"])
    app.include_router(profile_router, prefix=f"{API_V1_PREFIX}/profile", tags=["User Profile"])
    app.include_router(
        applications_router, prefix=f"{API_V1_PREFIX}/applications", tags=["Job Applications"]
    )
    app.include_router(workflow_router, prefix=f"{API_V1_PREFIX}/workflow", tags=["Workflow"])
    app.include_router(
        interview_prep_router, prefix=f"{API_V1_PREFIX}/interview-prep", tags=["Interview Prep"]
    )
    app.include_router(
        cv_optimizer_router, prefix=f"{API_V1_PREFIX}/cv-optimizer", tags=["CV Optimizer"]
    )
    app.include_router(
        tools_router, prefix=f"{API_V1_PREFIX}/tools", tags=["Career Tools"]
    )
    app.include_router(
        extension_autofill_router,
        prefix=f"{API_V1_PREFIX}/extension",
        tags=["Extension"],
    )
    app.include_router(websocket_router, prefix=f"{API_V1_PREFIX}", tags=["WebSocket"])
    app.include_router(admin_router, prefix=f"{API_V1_PREFIX}", tags=["Admin"])

    # Legacy routes (for backward compatibility - redirect to v1)
    # These ensure existing clients continue to work
    app.include_router(auth_router, prefix="/api/auth", tags=["Authentication (Legacy)"], include_in_schema=False)
    app.include_router(profile_router, prefix="/api/profile", tags=["User Profile (Legacy)"], include_in_schema=False)
    app.include_router(
        applications_router, prefix="/api/applications", tags=["Job Applications (Legacy)"], include_in_schema=False
    )
    app.include_router(workflow_router, prefix="/api/workflow", tags=["Workflow (Legacy)"], include_in_schema=False)
    app.include_router(
        interview_prep_router, prefix="/api/interview-prep", tags=["Interview Prep (Legacy)"], include_in_schema=False
    )
    app.include_router(
        tools_router, prefix="/api/tools", tags=["Career Tools (Legacy)"], include_in_schema=False
    )
    app.include_router(
        extension_autofill_router,
        prefix="/api/extension",
        tags=["Extension (Legacy)"],
        include_in_schema=False,
    )
    app.include_router(websocket_router, prefix="/api", tags=["WebSocket (Legacy)"], include_in_schema=False)
    
    # Cache stats endpoint for monitoring — requires admin authentication
    from fastapi import Depends
    from utils.auth import require_admin

    @app.get("/api/v1/cache/stats", tags=["Monitoring"])
    @app.get("/api/cache/stats", tags=["Monitoring"], include_in_schema=False)
    async def cache_stats(current_user: Dict[str, Any] = Depends(require_admin)):
        """Get Redis cache statistics for monitoring. Requires admin role."""
        try:
            from utils.cache import get_cache_stats
            return await get_cache_stats()
        except Exception as e:
            logger.warning(f"Failed to get cache stats: {e}")
            return {"status": "unavailable", "error": "Cache unavailable"}


def add_custom_routes(app: FastAPI):
    """Add custom routes for the application."""

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint for Cloud Run and application monitoring.

        Always returns 200 OK (Cloud Run requirement), even when services are degraded.
        The actual health status is in the response body.
        """
        try:
            services_status: Dict[str, str] = {}
            overall_status: str = "healthy"

            # Check database service - critical for application
            try:
                db_healthy = await check_database_health()
                services_status["database"] = "healthy" if db_healthy else "degraded"
                if not db_healthy:
                    overall_status = "degraded"
                    logger.warning(
                        "Database health check failed but continuing operation"
                    )
            except Exception as e:
                services_status["database"] = "degraded"
                overall_status = "degraded"
                logger.error(f"Database health check error: {e}", exc_info=True)

            # Check Gemini service - non-critical; skip in BYOK-only mode
            server_has_gemini_key = bool(getattr(settings, "gemini_api_key", None)) or getattr(settings, "use_vertex_ai", False)
            if server_has_gemini_key:
                try:
                    gemini_healthy: bool = await check_gemini_health()
                    services_status["gemini"] = "healthy" if gemini_healthy else "degraded"
                except Exception as e:
                    services_status["gemini"] = "degraded"
                    logger.error(f"Gemini health check error: {e}", exc_info=True)
            else:
                services_status["gemini"] = "byok_only"

            # Check Redis service - non-critical
            try:
                redis_healthy = await check_redis_health()
                services_status["redis"] = "healthy" if redis_healthy else "degraded"
            except Exception as e:
                services_status["redis"] = "degraded"
                logger.error(f"Redis health check error: {e}", exc_info=True)

            # Check maintenance mode
            maintenance = False
            try:
                from utils.maintenance import is_maintenance_mode
                maintenance = await is_maintenance_mode()
            except Exception as e:
                logger.error(f"Maintenance mode check error: {e}", exc_info=True)

            health_status = {
                "status": overall_status,
                "maintenance": maintenance,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "services": services_status,
                "version": settings.app_version,
            }

            return JSONResponse(content=health_status, status_code=200)

        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            # Always return 200 for Cloud Run; indicate failure in the body without exposing str(e)
            return JSONResponse(
                content={
                    "status": "degraded",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "message": "Health check encountered an error but service may still be operational",
                },
                status_code=200,
            )

    # Root endpoint - serve main application
    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        """Serve the main application page."""
        if templates is None:
            return HTMLResponse(
                content="<h1>ApplyPilot</h1><p>Service initializing...</p>",
                status_code=503,
            )

        try:
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "app_name": settings.app_name,
                    "app_version": settings.app_version,
                    **get_analytics_context(),
                },
            )
        except Exception as e:
            logger.error(f"Error serving root page: {e}", exc_info=True)
            return HTMLResponse(
                content="<h1>ApplyPilot</h1><p>Service temporarily unavailable</p>",
                status_code=503,
            )

    # Dashboard endpoint
    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request):
        """Serve the dashboard page."""
        if templates is None:
            return HTMLResponse(
                content="<h1>Dashboard</h1><p>Service initializing...</p>",
                status_code=503,
            )

        try:
            return templates.TemplateResponse(
                "dashboard/index.html",
                {"request": request, "app_name": settings.app_name, **get_analytics_context()},
            )
        except Exception as e:
            logger.error(f"Error serving dashboard: {e}", exc_info=True)

    # New Application endpoint
    @app.get("/dashboard/new-application", response_class=HTMLResponse)
    async def new_application(request: Request):
        """Serve the new application page."""
        if templates is None:
            return HTMLResponse(
                content="<h1>New Application</h1><p>Service initializing...</p>",
                status_code=503,
            )

        try:
            return templates.TemplateResponse(
                "dashboard/new-application.html",
                {"request": request, "app_name": settings.app_name},
            )
        except Exception as e:
            logger.error(f"Error serving new application page: {e}", exc_info=True)
            return HTMLResponse(
                content="<h1>New Application</h1><p>Service temporarily unavailable</p>",
                status_code=503,
            )

    # Authentication pages
    @app.get("/auth/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        """Serve the login page."""
        if templates is None:
            return HTMLResponse(
                content="<h1>Login</h1><p>Service initializing...</p>", status_code=503
            )

        try:
            return templates.TemplateResponse(
                "auth/login.html",
                {
                    "request": request,
                    "app_name": settings.app_name,
                },
            )
        except Exception as e:
            logger.error(f"Error serving login page: {e}", exc_info=True)
            return HTMLResponse(
                content="<h1>Login</h1><p>Service temporarily unavailable</p>",
                status_code=503,
            )

    @app.get("/auth/register", response_class=HTMLResponse)
    async def register_page(request: Request):
        """Serve the registration page."""
        if templates is None:
            return HTMLResponse(
                content="<h1>Register</h1><p>Service initializing...</p>",
                status_code=503,
            )

        try:
            return templates.TemplateResponse(
                "auth/register.html",
                {
                    "request": request,
                    "app_name": settings.app_name,
                    **get_analytics_context(),
                },
            )
        except Exception as e:
            logger.error(f"Error serving register page: {e}", exc_info=True)
            return HTMLResponse(
                content="<h1>Register</h1><p>Service temporarily unavailable</p>",
                status_code=503,
            )

    @app.get("/auth/reset-password", response_class=HTMLResponse)
    async def reset_password_page(request: Request):
        """Serve the password reset page."""
        if templates is None:
            return HTMLResponse(
                content="<h1>Reset Password</h1><p>Service initializing...</p>",
                status_code=503,
            )

        try:
            return templates.TemplateResponse(
                "auth/reset-password.html",
                {
                    "request": request,
                    "app_name": settings.app_name,
                },
            )
        except Exception as e:
            logger.error(f"Error serving reset password page: {e}", exc_info=True)
            return HTMLResponse(
                content="<h1>Reset Password</h1><p>Service temporarily unavailable</p>",
                status_code=503,
            )

    @app.get("/auth/forgot-password", response_class=HTMLResponse)
    async def forgot_password_page(request: Request):
        """Serve the forgot password page (redirects to reset-password)."""
        if templates is None:
            return HTMLResponse(
                content="<h1>Forgot Password</h1><p>Service initializing...</p>",
                status_code=503,
            )

        try:
            return templates.TemplateResponse(
                "auth/reset-password.html",
                {
                    "request": request,
                    "app_name": settings.app_name,
                },
            )
        except Exception as e:
            logger.error(f"Error serving forgot password page: {e}", exc_info=True)
            return HTMLResponse(
                content="<h1>Forgot Password</h1><p>Service temporarily unavailable</p>",
                status_code=503,
            )

    @app.get("/auth/verify-email", response_class=HTMLResponse)
    async def verify_email_page(request: Request):
        """Serve the email verification page."""
        if templates is None:
            return HTMLResponse(
                content="<h1>Verify Email</h1><p>Service initializing...</p>",
                status_code=503,
            )

        try:
            return templates.TemplateResponse(
                "auth/verify-email.html",
                {
                    "request": request,
                    "app_name": settings.app_name,
                },
            )
        except Exception as e:
            logger.error(f"Error serving verify email page: {e}", exc_info=True)
            return HTMLResponse(
                content="<h1>Verify Email</h1><p>Service temporarily unavailable</p>",
                status_code=503,
            )

    # Career Tools page
    @app.get("/dashboard/tools", response_class=HTMLResponse)
    async def tools_page(request: Request):
        """Serve the career tools page."""
        if templates is None:
            return HTMLResponse(
                content="<h1>Career Tools</h1><p>Service initializing...</p>",
                status_code=503,
            )

        try:
            return templates.TemplateResponse(
                "dashboard/tools.html",
                {
                    "request": request,
                    "app_name": settings.app_name,
                },
            )
        except Exception as e:
            logger.error(f"Error serving tools page: {e}", exc_info=True)
            return HTMLResponse(
                content="<h1>Career Tools</h1><p>Service temporarily unavailable</p>",
                status_code=503,
            )

    # Interview Prep page
    @app.get("/dashboard/interview-prep/{session_id}", response_class=HTMLResponse)
    async def interview_prep_page(request: Request, session_id: str):
        """Serve the interview preparation page."""
        if templates is None:
            return HTMLResponse(
                content="<h1>Interview Prep</h1><p>Service initializing...</p>",
                status_code=503,
            )

        try:
            return templates.TemplateResponse(
                "dashboard/interview-prep.html",
                {
                    "request": request,
                    "app_name": settings.app_name,
                    "session_id": session_id,
                },
            )
        except Exception as e:
            logger.error(f"Error serving interview prep page: {e}", exc_info=True)
            return HTMLResponse(
                content="<h1>Interview Prep</h1><p>Service temporarily unavailable</p>",
                status_code=503,
            )

    # Profile setup pages
    @app.get("/profile/setup", response_class=HTMLResponse)
    async def profile_setup_page(request: Request):
        """Serve the profile setup page."""
        if templates is None:
            return HTMLResponse(
                content="<h1>Profile Setup</h1><p>Service initializing...</p>",
                status_code=503,
            )

        try:
            return templates.TemplateResponse(
                "profile/setup.html",
                {"request": request, "app_name": settings.app_name, **get_analytics_context()},
            )
        except Exception as e:
            logger.error(f"Error serving profile setup page: {e}", exc_info=True)
            return HTMLResponse(
                content="<h1>Profile Setup</h1><p>Service temporarily unavailable</p>",
                status_code=503,
            )

    # Help page
    @app.get("/help", response_class=HTMLResponse)
    async def help_page(request: Request):
        """Serve the help and FAQ page."""
        if templates is None:
            return HTMLResponse(
                content="<h1>Help</h1><p>Service initializing...</p>",
                status_code=503,
            )

        try:
            return templates.TemplateResponse(
                "help.html",
                {"request": request, "app_name": settings.app_name, **get_analytics_context()},
            )
        except Exception as e:
            logger.error(f"Error serving help page: {e}", exc_info=True)
            return HTMLResponse(
                content="<h1>Help</h1><p>Service temporarily unavailable</p>",
                status_code=503,
            )

    # Maintenance page
    @app.get("/maintenance", response_class=HTMLResponse)
    async def maintenance_page(request: Request):
        """Serve the maintenance page."""
        from utils.maintenance import get_maintenance_info
        
        if templates is None:
            return HTMLResponse(
                content="<h1>Maintenance</h1><p>Service under maintenance...</p>",
                status_code=503,
            )

        try:
            maintenance_info = await get_maintenance_info()
            return templates.TemplateResponse(
                "maintenance.html",
                {
                    "request": request,
                    "app_name": settings.app_name,
                    "message": maintenance_info.get("message"),
                    "estimated_end": maintenance_info.get("estimated_end"),
                },
                status_code=503 if maintenance_info.get("enabled") else 200,
            )
        except Exception as e:
            logger.error(f"Error serving maintenance page: {e}", exc_info=True)
            return HTMLResponse(
                content="<h1>Maintenance</h1><p>Service under maintenance</p>",
                status_code=503,
            )

    # Legal pages
    @app.get("/privacy", response_class=HTMLResponse)
    async def privacy_policy_page(request: Request):
        """Serve the privacy policy page."""
        if templates is None:
            return HTMLResponse(
                content="<h1>Privacy Policy</h1><p>Service initializing...</p>",
                status_code=503,
            )

        try:
            return templates.TemplateResponse(
                "legal/privacy.html",
                {"request": request, "app_name": settings.app_name},
            )
        except Exception as e:
            logger.error(f"Error serving privacy policy page: {e}", exc_info=True)
            return HTMLResponse(
                content="<h1>Privacy Policy</h1><p>Service temporarily unavailable</p>",
                status_code=503,
            )

    @app.get("/terms", response_class=HTMLResponse)
    async def terms_of_service_page(request: Request):
        """Serve the terms of service page."""
        if templates is None:
            return HTMLResponse(
                content="<h1>Terms of Service</h1><p>Service initializing...</p>",
                status_code=503,
            )

        try:
            return templates.TemplateResponse(
                "legal/terms.html",
                {"request": request, "app_name": settings.app_name},
            )
        except Exception as e:
            logger.error(f"Error serving terms of service page: {e}", exc_info=True)
            return HTMLResponse(
                content="<h1>Terms of Service</h1><p>Service temporarily unavailable</p>",
                status_code=503,
            )

    # Settings page
    @app.get("/dashboard/settings", response_class=HTMLResponse)
    async def settings_page(request: Request):
        """Serve the settings page."""
        if templates is None:
            return HTMLResponse(
                content="<h1>Settings</h1><p>Service initializing...</p>",
                status_code=503,
            )

        try:
            return templates.TemplateResponse(
                "dashboard/settings.html",
                {"request": request, "app_name": settings.app_name},
            )
        except Exception as e:
            logger.error(f"Error serving settings page: {e}", exc_info=True)
            return HTMLResponse(
                content="<h1>Settings</h1><p>Service temporarily unavailable</p>",
                status_code=503,
            )

    # Application detail page
    @app.get("/dashboard/application/{application_id}", response_class=HTMLResponse)
    async def application_detail_page(request: Request, application_id: str):
        """Serve the application detail page."""
        if templates is None:
            return HTMLResponse(
                content="<h1>Application</h1><p>Service initializing...</p>",
                status_code=503,
            )

        try:
            return templates.TemplateResponse(
                "dashboard/application.html",
                {
                    "request": request,
                    "app_name": settings.app_name,
                    "application_id": application_id,
                },
            )
        except Exception as e:
            logger.error(f"Error serving application detail page: {e}", exc_info=True)
            return HTMLResponse(
                content="<h1>Application</h1><p>Service temporarily unavailable</p>",
                status_code=503,
            )

    # /.well-known/security.txt — standard responsible disclosure policy
    @app.get("/.well-known/security.txt", include_in_schema=False)
    async def security_txt(request: Request):
        """Serve security.txt per RFC 9116 for responsible disclosure."""
        from datetime import timezone
        import datetime

        expires = (
            datetime.datetime.now(timezone.utc) + datetime.timedelta(days=365)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        domain = settings.base_url.replace("https://", "").replace("http://", "").split("/")[0]
        contact_email = settings.security_contact_email or f"security@{domain}"

        content = (
            f"Contact: mailto:{contact_email}\n"
            f"Expires: {expires}\n"
            f"Canonical: {settings.base_url}/.well-known/security.txt\n"
            "Preferred-Languages: en\n"
            "Policy: Responsible disclosure — please report vulnerabilities privately before public disclosure.\n"
        )
        return Response(content=content, media_type="text/plain")

    # Static files — absolute path avoids breakage if working directory changes
    _static_dir = Path(__file__).parent / "ui" / "static"
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

    # API documentation redirect
    @app.get("/docs")
    async def docs_redirect():
        """Redirect to API documentation."""
        if settings.debug:
            return JSONResponse({"message": "API documentation available at /api/docs"})
        else:
            raise not_found_error("Documentation")


def _is_html_request(request: Request) -> bool:
    """Check if the request expects HTML response."""
    # Check Accept header
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return True
    # Check if it's not an API request
    path = str(request.url.path)
    if path.startswith("/api/"):
        return False
    # Check for common browser patterns
    if "application/json" in accept:
        return False
    return True


def add_exception_handlers(app: FastAPI):
    """Add custom exception handlers with standardized error responses."""

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError):
        """Handle custom API errors with standardized format."""
        logger.warning(f"API Error {exc.error_code.value}: {exc.message} - {request.url}")
        return exc.to_response()

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        """Handle validation errors with standardized format."""
        # Sanitize the exception details to ensure they are JSON serializable
        errors = exc.errors()
        details = []
        for error in errors:
            field = ".".join(str(loc) for loc in error.get("loc", []))
            details.append({
                "field": field,
                "message": error.get("msg", "Validation error"),
                "code": error.get("type", "validation_error"),
            })

        logger.error(
            f"Validation error for {request.method} {request.url}: {details}"
        )
        
        return create_error_response(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Request validation failed",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle HTTP exceptions with standardized format or custom HTML pages."""
        logger.warning(f"HTTP {exc.status_code}: {exc.detail} - {request.url}")
        if exc.status_code >= 500:
            await report_exception(exc, request=request)

        # Serve custom HTML error pages for browser requests
        if _is_html_request(request) and templates is not None:
            if exc.status_code == 404:
                try:
                    return templates.TemplateResponse(
                        "errors/404.html",
                        {"request": request, "app_name": settings.app_name},
                        status_code=404,
                    )
                except Exception as tpl_err:
                    logger.debug("Failed to render 404 template, falling back to JSON", exc_info=True)
            elif exc.status_code >= 500:
                try:
                    error_id = request_id_var.get() or f"ERR-{datetime.now().timestamp()}"
                    return templates.TemplateResponse(
                        "errors/500.html",
                        {
                            "request": request,
                            "app_name": settings.app_name,
                            "error_id": error_id,
                        },
                        status_code=exc.status_code,
                    )
                except Exception as tpl_err:
                    logger.debug("Failed to render 500 template, falling back to JSON", exc_info=True)

        # Map HTTP status codes to error codes
        error_code_map = {
            400: ErrorCode.VALIDATION_ERROR,
            401: ErrorCode.AUTH_UNAUTHORIZED,
            403: ErrorCode.AUTH_FORBIDDEN,
            404: ErrorCode.RESOURCE_NOT_FOUND,
            409: ErrorCode.RESOURCE_CONFLICT,
            423: ErrorCode.AUTH_ACCOUNT_LOCKED,
            429: ErrorCode.RATE_LIMIT_EXCEEDED,
            500: ErrorCode.INTERNAL_ERROR,
        }
        error_code = error_code_map.get(exc.status_code, ErrorCode.UNKNOWN_ERROR)

        return create_error_response(
            error_code=error_code,
            message=str(exc.detail),
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle general exceptions with standardized format or custom HTML pages."""
        logger.error(f"Unhandled exception: {str(exc)} - {request.url}", exc_info=True)
        await report_exception(exc, request=request)

        # Serve custom HTML error page for browser requests
        if _is_html_request(request) and templates is not None:
            try:
                error_id = request_id_var.get() or f"ERR-{datetime.now().timestamp()}"
                return templates.TemplateResponse(
                    "errors/500.html",
                    {
                        "request": request,
                        "app_name": settings.app_name,
                        "error_id": error_id,
                    },
                    status_code=500,
                )
            except Exception:
                logger.debug("Failed to render 500 template in general handler, falling back to JSON", exc_info=True)

        message = "An unexpected error occurred"
        if not settings.is_production:
            message = str(exc)

        return create_error_response(
            error_code=ErrorCode.INTERNAL_ERROR,
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# Create the application instance
app = create_app()


# Development server entry point
if __name__ == "__main__":
    # Get configuration
    host = settings.host
    port = settings.port
    reload = settings.reload and settings.debug
    workers = 1 if settings.debug else settings.workers

    # Run the server.
    # - access_log=False  → our RequestLoggingMiddleware already logs every request;
    #                        uvicorn's access log would produce an exact duplicate line.
    # - log_config=None   → prevents uvicorn from resetting the root logger config
    #                        that setup_logging() already configured above.
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers,
        log_level=settings.log_level.lower(),
        access_log=False,
        log_config=None,
    )
