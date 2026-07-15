"""Unit tests for utils.tracing (OpenTelemetry optional)."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from utils import tracing


def _install_fake_otel(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    """Inject minimal opentelemetry modules so tracing setup can run without deps."""
    fake_span = MagicMock(name="span")
    fake_tracer = MagicMock(name="tracer")
    fake_tracer.start_as_current_span.return_value.__enter__.return_value = fake_span
    fake_tracer.start_as_current_span.return_value.__exit__.return_value = None

    otel_trace = ModuleType("opentelemetry.trace")
    otel_trace.set_tracer_provider = MagicMock()
    otel_trace.get_tracer = MagicMock(return_value=fake_tracer)
    otel_trace.get_current_span = MagicMock(return_value=fake_span)
    StatusCode = SimpleNamespace(ERROR="ERROR")
    otel_trace.StatusCode = StatusCode

    otel_root = ModuleType("opentelemetry")
    otel_root.trace = otel_trace

    resources = ModuleType("opentelemetry.sdk.resources")
    resources.Resource = MagicMock()
    resources.Resource.create = MagicMock(return_value=MagicMock(name="resource"))

    sdk_trace = ModuleType("opentelemetry.sdk.trace")
    sdk_trace.TracerProvider = MagicMock(return_value=MagicMock(name="provider"))

    sdk_export = ModuleType("opentelemetry.sdk.trace.export")
    sdk_export.BatchSpanProcessor = MagicMock(return_value=MagicMock(name="bsp"))
    sdk_export.ConsoleSpanExporter = MagicMock(return_value=MagicMock(name="console"))

    fastapi_instr = ModuleType("opentelemetry.instrumentation.fastapi")
    fastapi_instr.FastAPIInstrumentor = MagicMock(return_value=MagicMock(name="fastapi_instr"))

    sa_instr = ModuleType("opentelemetry.instrumentation.sqlalchemy")
    sa_instr.SQLAlchemyInstrumentor = MagicMock(return_value=MagicMock(name="sa_instr"))

    gcp_export = ModuleType("opentelemetry.exporter.gcp.trace")
    gcp_export.CloudTraceSpanExporter = MagicMock(return_value=MagicMock(name="gcp"))

    modules = {
        "opentelemetry": otel_root,
        "opentelemetry.trace": otel_trace,
        "opentelemetry.sdk": ModuleType("opentelemetry.sdk"),
        "opentelemetry.sdk.resources": resources,
        "opentelemetry.sdk.trace": sdk_trace,
        "opentelemetry.sdk.trace.export": sdk_export,
        "opentelemetry.instrumentation": ModuleType("opentelemetry.instrumentation"),
        "opentelemetry.instrumentation.fastapi": fastapi_instr,
        "opentelemetry.instrumentation.sqlalchemy": sa_instr,
        "opentelemetry.exporter": ModuleType("opentelemetry.exporter"),
        "opentelemetry.exporter.gcp": ModuleType("opentelemetry.exporter.gcp"),
        "opentelemetry.exporter.gcp.trace": gcp_export,
    }
    for name, mod in modules.items():
        monkeypatch.setitem(sys.modules, name, mod)

    # Bind names the real import would have set on the tracing module.
    monkeypatch.setattr(tracing, "otel_trace", otel_trace, raising=False)
    monkeypatch.setattr(tracing, "Resource", resources.Resource, raising=False)
    monkeypatch.setattr(tracing, "TracerProvider", sdk_trace.TracerProvider, raising=False)
    monkeypatch.setattr(tracing, "BatchSpanProcessor", sdk_export.BatchSpanProcessor, raising=False)
    monkeypatch.setattr(tracing, "StatusCode", StatusCode, raising=False)
    monkeypatch.setattr(tracing, "_OTEL_AVAILABLE", True)

    return {
        "otel_trace": otel_trace,
        "Resource": resources.Resource,
        "TracerProvider": sdk_trace.TracerProvider,
        "BatchSpanProcessor": sdk_export.BatchSpanProcessor,
        "FastAPIInstrumentor": fastapi_instr.FastAPIInstrumentor,
        "SQLAlchemyInstrumentor": sa_instr.SQLAlchemyInstrumentor,
        "CloudTraceSpanExporter": gcp_export.CloudTraceSpanExporter,
        "ConsoleSpanExporter": sdk_export.ConsoleSpanExporter,
        "tracer": fake_tracer,
        "span": fake_span,
    }


@pytest.mark.asyncio
async def test_trace_span_noop_when_tracer_unset() -> None:
    with patch.object(tracing, "_OTEL_AVAILABLE", True), patch.object(tracing, "_tracer", None):
        async with tracing.trace_span("test.span", {"k": "v"}) as span:
            assert span is None


@pytest.mark.asyncio
async def test_trace_span_noop_when_otel_unavailable() -> None:
    with patch.object(tracing, "_OTEL_AVAILABLE", False), patch.object(tracing, "_tracer", MagicMock()):
        async with tracing.trace_span("test.span") as span:
            assert span is None


def test_get_current_span_when_otel_unavailable() -> None:
    with patch.object(tracing, "_OTEL_AVAILABLE", False):
        assert tracing.get_current_span() is None


def test_setup_tracing_noop_when_otel_unavailable() -> None:
    with patch.object(tracing, "_OTEL_AVAILABLE", False):
        tracing.setup_tracing()


def test_setup_tracing_development(monkeypatch: pytest.MonkeyPatch) -> None:
    fakes = _install_fake_otel(monkeypatch)
    monkeypatch.setattr(tracing, "_tracer", None)
    tracing.setup_tracing(service_name="applypilot", environment="development")
    fakes["Resource"].create.assert_called_once()
    fakes["TracerProvider"].assert_called_once()
    fakes["BatchSpanProcessor"].assert_not_called()
    fakes["otel_trace"].set_tracer_provider.assert_called_once()
    fakes["FastAPIInstrumentor"].assert_called_once()
    fakes["SQLAlchemyInstrumentor"].assert_called_once()
    assert tracing._tracer is fakes["tracer"]


def test_setup_tracing_production_uses_cloud_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    fakes = _install_fake_otel(monkeypatch)
    monkeypatch.setattr(tracing, "_tracer", None)
    tracing.setup_tracing(environment="production")
    fakes["CloudTraceSpanExporter"].assert_called_once()
    fakes["BatchSpanProcessor"].assert_called_once()


def test_build_cloud_trace_exporter_falls_back_to_console(monkeypatch: pytest.MonkeyPatch) -> None:
    fakes = _install_fake_otel(monkeypatch)
    # Force GCP import failure → console exporter fallback.
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.exporter.gcp.trace",
        ModuleType("opentelemetry.exporter.gcp.trace"),
    )

    real_import = __import__

    def _fail_gcp(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "opentelemetry.exporter.gcp.trace" or (
            name == "opentelemetry.exporter.gcp" and fromlist and "trace" in fromlist
        ):
            raise ImportError(name)
        if name.startswith("opentelemetry.exporter.gcp.trace"):
            raise ImportError(name)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", _fail_gcp)
    exporter = tracing._build_cloud_trace_exporter()
    fakes["ConsoleSpanExporter"].assert_called_once()
    assert exporter is fakes["ConsoleSpanExporter"].return_value


def test_setup_tracing_handles_instrumentor_import_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    fakes = _install_fake_otel(monkeypatch)
    monkeypatch.setattr(tracing, "_tracer", None)

    # Remove instrumentor modules so `from opentelemetry.instrumentation...` raises.
    monkeypatch.delitem(sys.modules, "opentelemetry.instrumentation.fastapi", raising=False)
    monkeypatch.delitem(sys.modules, "opentelemetry.instrumentation.sqlalchemy", raising=False)

    real_import = __import__

    def _fail_instrumentors(name, globals=None, locals=None, fromlist=(), level=0):
        if "instrumentation.fastapi" in name or "instrumentation.sqlalchemy" in name:
            raise ImportError(name)
        if fromlist and (
            (name == "opentelemetry.instrumentation" and "fastapi" in fromlist)
            or (name == "opentelemetry.instrumentation" and "sqlalchemy" in fromlist)
        ):
            raise ImportError(name)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", _fail_instrumentors)
    tracing.setup_tracing(environment="development")
    assert tracing._tracer is fakes["tracer"]


def test_setup_tracing_swallows_unexpected_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_otel(monkeypatch)
    monkeypatch.setattr(tracing, "_tracer", None)
    broken = MagicMock()
    broken.create.side_effect = RuntimeError("boom")
    monkeypatch.setattr(tracing, "Resource", broken)
    tracing.setup_tracing(environment="development")
    assert tracing._tracer is None


@pytest.mark.asyncio
async def test_trace_span_sets_attributes_and_yields(monkeypatch: pytest.MonkeyPatch) -> None:
    fakes = _install_fake_otel(monkeypatch)
    monkeypatch.setattr(tracing, "_tracer", fakes["tracer"])
    async with tracing.trace_span("agent.job", {"model": "x"}) as span:
        assert span is fakes["span"]
    fakes["span"].set_attribute.assert_called_with("model", "x")


@pytest.mark.asyncio
async def test_trace_span_records_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    fakes = _install_fake_otel(monkeypatch)
    monkeypatch.setattr(tracing, "_tracer", fakes["tracer"])
    raised = False
    try:
        async with tracing.trace_span("agent.job"):
            raise ValueError("fail")
    except ValueError:
        raised = True
    assert raised is True
    fakes["span"].set_status.assert_called_once()
    fakes["span"].record_exception.assert_called_once()


def test_get_current_span_when_otel_available(monkeypatch: pytest.MonkeyPatch) -> None:
    fakes = _install_fake_otel(monkeypatch)
    assert tracing.get_current_span() is fakes["span"]
