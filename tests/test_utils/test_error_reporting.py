"""Tests for utils/error_reporting.py."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request

import utils.error_reporting as er


@pytest.fixture(autouse=True)
def reset_error_client():
    er._client = None
    er._client_init_attempted = False
    yield
    er._client = None
    er._client_init_attempted = False


def test_get_client_unavailable_when_package_missing() -> None:
    with patch.object(er, "_CLIENT_AVAILABLE", False):
        assert er._get_client() is None


def test_import_error_marks_client_unavailable(monkeypatch) -> None:
    import builtins
    import importlib
    import sys

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "google.cloud" or name.startswith("google.cloud."):
            raise ImportError("blocked for test")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    sys.modules.pop("utils.error_reporting", None)
    reloaded = importlib.import_module("utils.error_reporting")
    assert reloaded._CLIENT_AVAILABLE is False
    sys.modules.pop("utils.error_reporting", None)
    importlib.import_module("utils.error_reporting")


def test_get_client_initializes_once() -> None:
    mock_client = MagicMock()
    with patch.object(er, "_CLIENT_AVAILABLE", True), \
         patch.object(er, "_gcp_error_reporting", MagicMock(Client=MagicMock(return_value=mock_client))):
        assert er._get_client() is mock_client
        assert er._get_client() is mock_client


def test_get_client_init_failure() -> None:
    with patch.object(er, "_CLIENT_AVAILABLE", True), \
         patch.object(er, "_gcp_error_reporting", MagicMock(Client=MagicMock(side_effect=RuntimeError("fail")))):
        assert er._get_client() is None


@pytest.mark.asyncio
async def test_report_exception_skips_non_production() -> None:
    with patch("config.settings.get_settings") as gs:
        gs.return_value = MagicMock(is_production=False)
        await er.report_exception(RuntimeError("x"))
        assert er._client_init_attempted is False


@pytest.mark.asyncio
async def test_report_exception_no_client_in_production() -> None:
    with patch("config.settings.get_settings") as gs, \
         patch.object(er, "_get_client", return_value=None):
        gs.return_value = MagicMock(is_production=True)
        await er.report_exception(RuntimeError("x"))  # no raise


@pytest.mark.asyncio
async def test_report_exception_with_request_and_client() -> None:
    mock_client = MagicMock()
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/test",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    request = Request(scope)

    with patch("config.settings.get_settings") as gs, \
         patch.object(er, "_get_client", return_value=mock_client), \
         patch.object(er, "_CLIENT_AVAILABLE", True), \
         patch.object(er, "_gcp_error_reporting", MagicMock(HTTPContext=MagicMock(return_value="ctx"))):
        gs.return_value = MagicMock(is_production=True)
        await er.report_exception(ValueError("boom"), request=request, user_id="user-1")
        mock_client.report.assert_called_once()


@pytest.mark.asyncio
async def test_report_exception_swallows_report_failure() -> None:
    mock_client = MagicMock()
    mock_client.report.side_effect = RuntimeError("grpc down")
    with patch("config.settings.get_settings") as gs, \
         patch.object(er, "_get_client", return_value=mock_client):
        gs.return_value = MagicMock(is_production=True)
        await er.report_exception(RuntimeError("orig"))  # no raise


@pytest.mark.asyncio
async def test_report_exception_http_context_build_failure() -> None:
    mock_client = MagicMock()
    broken_request = MagicMock()
    broken_request.method = "GET"
    type(broken_request).url = property(lambda self: (_ for _ in ()).throw(RuntimeError("bad url")))

    with patch("config.settings.get_settings") as gs, \
         patch.object(er, "_get_client", return_value=mock_client), \
         patch.object(er, "_CLIENT_AVAILABLE", True), \
         patch.object(er, "_gcp_error_reporting", MagicMock(HTTPContext=MagicMock(side_effect=RuntimeError("ctx fail")))):
        gs.return_value = MagicMock(is_production=True)
        await er.report_exception(RuntimeError("boom"), request=broken_request)
        mock_client.report.assert_called_once()
