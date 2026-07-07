"""Tests for utils/tracing.py."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

import utils.tracing as tracing_mod


@pytest.fixture(autouse=True)
def reset_tracing_state():
    tracing_mod._tracer = None
    yield
    tracing_mod._tracer = None


def _enable_otel_on_module(monkeypatch):
    """Inject OTEL symbols that only exist when the package is installed."""
    fake_tracer = MagicMock()
    fake_trace = MagicMock()
    fake_trace.get_tracer.return_value = fake_tracer
    fake_trace.get_current_span.return_value = MagicMock()
    monkeypatch.setattr(tracing_mod, "_OTEL_AVAILABLE", True, raising=False)
    monkeypatch.setattr(tracing_mod, "Resource", MagicMock(create=MagicMock(return_value=MagicMock())), raising=False)
    monkeypatch.setattr(tracing_mod, "TracerProvider", MagicMock(return_value=MagicMock()), raising=False)
    monkeypatch.setattr(tracing_mod, "BatchSpanProcessor", MagicMock(), raising=False)
    monkeypatch.setattr(tracing_mod, "otel_trace", fake_trace, raising=False)
    monkeypatch.setattr(tracing_mod, "StatusCode", MagicMock(ERROR="ERROR"), raising=False)
    return fake_tracer


@pytest.mark.asyncio
async def test_trace_span_noop_when_otel_unavailable() -> None:
    with patch.object(tracing_mod, "_OTEL_AVAILABLE", False):
        async with tracing_mod.trace_span("test.span", {"k": "v"}) as span:
            assert span is None


def test_get_current_span_noop_when_unavailable() -> None:
    with patch.object(tracing_mod, "_OTEL_AVAILABLE", False):
        assert tracing_mod.get_current_span() is None


def test_setup_tracing_noop_when_otel_unavailable() -> None:
    with patch.object(tracing_mod, "_OTEL_AVAILABLE", False):
        tracing_mod.setup_tracing(service_name="applypilot", environment="production")
        assert tracing_mod._tracer is None


def test_setup_tracing_development_no_exporter(monkeypatch) -> None:
    fake_tracer = _enable_otel_on_module(monkeypatch)
    fake_fa = MagicMock()
    fake_sa = MagicMock()
    with patch.dict(
        "sys.modules",
        {
            "opentelemetry.instrumentation.fastapi": MagicMock(FastAPIInstrumentor=fake_fa),
            "opentelemetry.instrumentation.sqlalchemy": MagicMock(SQLAlchemyInstrumentor=fake_sa),
        },
    ):
        tracing_mod.setup_tracing(environment="development")
        assert tracing_mod._tracer is fake_tracer
        fake_fa.return_value.instrument.assert_called_once()
        fake_sa.return_value.instrument.assert_called_once()


def test_setup_tracing_production_adds_exporter(monkeypatch) -> None:
    _enable_otel_on_module(monkeypatch)
    mock_exporter = MagicMock()
    mock_provider = MagicMock()
    monkeypatch.setattr(tracing_mod, "TracerProvider", MagicMock(return_value=mock_provider), raising=False)
    with patch.object(tracing_mod, "_build_cloud_trace_exporter", return_value=mock_exporter), \
         patch.dict(
             "sys.modules",
             {
                 "opentelemetry.instrumentation.fastapi": MagicMock(FastAPIInstrumentor=MagicMock()),
                 "opentelemetry.instrumentation.sqlalchemy": MagicMock(SQLAlchemyInstrumentor=MagicMock()),
             },
         ):
        tracing_mod.setup_tracing(environment="production")
        mock_provider.add_span_processor.assert_called_once()


def test_setup_tracing_handles_fastapi_instrumentor_missing(monkeypatch) -> None:
    _enable_otel_on_module(monkeypatch)
    with patch.dict("sys.modules", {"opentelemetry.instrumentation.fastapi": None}):
        tracing_mod.setup_tracing(environment="development")


def test_setup_tracing_handles_exception(monkeypatch) -> None:
    _enable_otel_on_module(monkeypatch)
    monkeypatch.setattr(tracing_mod, "Resource", MagicMock(side_effect=RuntimeError("fail")), raising=False)
    tracing_mod.setup_tracing(environment="production")
    assert tracing_mod._tracer is None


def test_build_cloud_trace_exporter_gcp_path() -> None:
    mock_exporter = MagicMock()
    fake_mod = MagicMock(CloudTraceSpanExporter=MagicMock(return_value=mock_exporter))
    with patch.dict("sys.modules", {"opentelemetry.exporter.gcp.trace": fake_mod}):
        result = tracing_mod._build_cloud_trace_exporter()
        assert result is mock_exporter


def test_build_cloud_trace_exporter_console_fallback() -> None:
    mock_console_cls = MagicMock(return_value="console-exporter")
    fake_export_mod = MagicMock(ConsoleSpanExporter=mock_console_cls)
    with patch.dict(
        "sys.modules",
        {
            "opentelemetry.exporter.gcp.trace": None,
            "opentelemetry.sdk.trace.export": fake_export_mod,
        },
    ):
        result = tracing_mod._build_cloud_trace_exporter()
        assert result == "console-exporter"


@pytest.mark.asyncio
async def test_trace_span_records_exception(monkeypatch) -> None:
    mock_span = MagicMock()
    mock_tracer = MagicMock()

    @contextmanager
    def _span_cm(*args, **kwargs):
        yield mock_span

    mock_tracer.start_as_current_span.side_effect = _span_cm
    _enable_otel_on_module(monkeypatch)
    monkeypatch.setattr(tracing_mod, "_tracer", mock_tracer, raising=False)

    with pytest.raises(ValueError):
        async with tracing_mod.trace_span("agent.test", {"x": 1}):
            raise ValueError("boom")
    mock_span.set_status.assert_called_once()
    mock_span.record_exception.assert_called_once()


@pytest.mark.asyncio
async def test_trace_span_yields_active_span(monkeypatch) -> None:
    mock_span = MagicMock()
    mock_tracer = MagicMock()

    @contextmanager
    def _span_cm(*args, **kwargs):
        yield mock_span

    mock_tracer.start_as_current_span.side_effect = _span_cm
    _enable_otel_on_module(monkeypatch)
    monkeypatch.setattr(tracing_mod, "_tracer", mock_tracer, raising=False)

    async with tracing_mod.trace_span("agent.ok", {"a": "b"}) as span:
        assert span is mock_span
    mock_span.set_attribute.assert_called_with("a", "b")


def test_get_current_span_with_otel(monkeypatch) -> None:
    mock_span = MagicMock()
    _enable_otel_on_module(monkeypatch)
    tracing_mod.otel_trace.get_current_span.return_value = mock_span
    assert tracing_mod.get_current_span() is mock_span


def test_import_error_sets_otel_unavailable(monkeypatch) -> None:
    import builtins
    import importlib
    import sys

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "opentelemetry" or name.startswith("opentelemetry."):
            raise ImportError("blocked for test")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    sys.modules.pop("utils.tracing", None)
    reloaded = importlib.import_module("utils.tracing")
    assert reloaded._OTEL_AVAILABLE is False
    sys.modules.pop("utils.tracing", None)
    importlib.import_module("utils.tracing")
