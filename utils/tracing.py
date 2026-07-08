"""
Distributed tracing via OpenTelemetry.

Instruments FastAPI requests, SQLAlchemy queries, and LLM agent calls.
In production, exports spans to Google Cloud Trace.
In development, prints spans to stdout.

If the opentelemetry packages are not installed the entire module degrades
gracefully — all public helpers become no-ops, nothing in the call-path raises.

Setup (called once at startup):
    from utils.tracing import setup_tracing
    setup_tracing(service_name="applypilot", environment="production")

Adding a custom span around an agent call:
    from utils.tracing import trace_span

    async with trace_span("agent.job_analyzer", {"job_url": url}) as span:
        if span:
            span.set_attribute("model", settings.gemini_model)
        result = await analyze(...)
"""

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional
from utils.logging_config import sanitize_log_value

logger = logging.getLogger(__name__)

# =============================================================================
# OPTIONAL IMPORT GUARD
# =============================================================================

try:
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.trace import StatusCode

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _OTEL_AVAILABLE = False
    logger.info(
        "OpenTelemetry packages not installed — tracing disabled. "
        "To enable: pip install opentelemetry-sdk "
        "opentelemetry-instrumentation-fastapi "
        "opentelemetry-instrumentation-sqlalchemy "
        "opentelemetry-exporter-gcp-trace"
    )

# =============================================================================
# MODULE STATE
# =============================================================================

_tracer: Optional[Any] = None  # opentelemetry.trace.Tracer | None


# =============================================================================
# SETUP
# =============================================================================


def setup_tracing(
    service_name: str = "applypilot",
    service_version: str = "1.0.0",
    environment: str = "production",
) -> None:
    """
    Initialise OpenTelemetry tracing.

    Must be called once during application startup, **before** the FastAPI app
    starts handling requests.  Auto-instruments FastAPI and SQLAlchemy so every
    HTTP request and database query automatically gets a span.

    In production, exports to Google Cloud Trace (requires
    `opentelemetry-exporter-gcp-trace` and GCP credentials).
    Falls back to the console exporter when the GCP package is missing.

    In development (environment != "production"), no exporter is attached —
    spans are created for `trace_span` instrumentation but are not printed,
    keeping the terminal output clean.

    Args:
        service_name: Service name tag attached to every span.
        service_version: Deployed version tag.
        environment: "production" | "development" | "staging".
    """
    global _tracer

    if not _OTEL_AVAILABLE:
        return

    try:
        resource = Resource.create(
            {
                "service.name": service_name,
                "service.version": service_version,
                "deployment.environment": environment,
            }
        )

        provider = TracerProvider(resource=resource)

        # In production, export spans to Cloud Trace.
        # In development, skip the console exporter entirely — raw JSON spans
        # flooding stdout add noise without benefit; the structured log lines
        # already give full observability during local development.
        if environment == "production":
            exporter = _build_cloud_trace_exporter()
            provider.add_span_processor(BatchSpanProcessor(exporter))
        otel_trace.set_tracer_provider(provider)

        # Auto-instrument FastAPI — all incoming requests get spans
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor().instrument()
        except ImportError:
            logger.warning(
                "opentelemetry-instrumentation-fastapi not installed — "
                "HTTP request spans will not be created automatically"
            )

        # Auto-instrument SQLAlchemy — all DB queries get spans
        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

            SQLAlchemyInstrumentor().instrument()
        except ImportError:
            logger.warning(
                "opentelemetry-instrumentation-sqlalchemy not installed — "
                "database query spans will not be created automatically"
            )

        _tracer = otel_trace.get_tracer(service_name, service_version)
        logger.info('OpenTelemetry tracing active — service=%s version=%s env=%s', sanitize_log_value(service_name), sanitize_log_value(service_version), sanitize_log_value(environment))

    except Exception as exc:
        # Never crash the application due to tracing setup failures.
        logger.error('OpenTelemetry setup failed — tracing disabled: %s', sanitize_log_value(exc), exc_info=True)


def _build_cloud_trace_exporter():
    """Return Cloud Trace exporter, falling back to console if unavailable."""
    try:
        from opentelemetry.exporter.gcp.trace import CloudTraceSpanExporter

        logger.info("OpenTelemetry: using Google Cloud Trace exporter")
        return CloudTraceSpanExporter()
    except ImportError:
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        logger.warning(
            "opentelemetry-exporter-gcp-trace not installed — "
            "falling back to console span exporter in production. "
            "Install it to export spans to Cloud Trace."
        )
        return ConsoleSpanExporter()


# =============================================================================
# SPAN CONTEXT MANAGER
# =============================================================================


@asynccontextmanager
async def trace_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[Optional[Any], None]:
    """
    Async context manager that creates a named child span.

    Degrades gracefully to a no-op if tracing is not configured.

    Args:
        name: Span name in dot notation, e.g. "agent.job_analyzer".
        attributes: Optional key/value attributes to attach immediately.

    Yields:
        The opentelemetry Span, or None if tracing is disabled.

    Example::

        async with trace_span("agent.cover_letter", {"model": model}) as span:
            if span:
                span.set_attribute("user_id", str(user_id))
            result = await cover_letter_agent.generate(...)
    """
    if not _OTEL_AVAILABLE or _tracer is None:
        yield None
        return

    with _tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, str(value))
        try:
            yield span
        except Exception as exc:
            span.set_status(StatusCode.ERROR, str(exc))
            span.record_exception(exc)
            raise


def get_current_span() -> Optional[Any]:
    """Return the currently active span, or None if tracing is off."""
    if not _OTEL_AVAILABLE:
        return None
    return otel_trace.get_current_span()
