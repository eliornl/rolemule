"""Unit tests for cli/output.py error and emit helpers."""

from __future__ import annotations

import json

import pytest
import typer

from applypilot_client.errors import ApiClientError, ExitCode
from cli.context import CliContext
from cli.output import (
    emit,
    emit_duplicate_application,
    emit_error,
    emit_workflow_error,
    persist_auth_response,
    require_client,
)


def _ctx(fmt: str = "human", token: str | None = "jwt") -> CliContext:
    from cli.config import Credentials

    creds = Credentials(access_token=token, email="u@example.com", saved_at="2026-01-01T00:00:00Z") if token else None
    return CliContext(base_url="http://localhost:8000", output_format=fmt, credentials=creds)


def test_emit_json_mode(capsys) -> None:
    emit(_ctx("json"), {"ok": True})
    out = capsys.readouterr().out
    assert json.loads(out)["ok"] is True


def test_emit_human_mode(capsys) -> None:
    emit(_ctx("human"), {"ok": True}, human="Hello")
    assert capsys.readouterr().out.strip() == "Hello"


def test_require_client_without_token_exits_2(capsys) -> None:
    with pytest.raises(typer.Exit) as exc:
        require_client(_ctx(token=None))
    assert exc.value.exit_code == int(ExitCode.AUTH_OR_PROFILE)


def test_emit_error_json_shape(capsys) -> None:
    exc = ApiClientError("Forbidden", status_code=403, error_code="AUTH_1003", exit_code=ExitCode.AUTH_OR_PROFILE)
    with pytest.raises(typer.Exit) as raised:
        emit_error(_ctx("json"), exc)
    assert raised.value.exit_code == int(ExitCode.AUTH_OR_PROFILE)
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert payload["error_code"] == "AUTH_1003"


def test_emit_error_human(capsys) -> None:
    exc = ApiClientError("Bad request", status_code=400, error_code="VAL_2001")
    with pytest.raises(typer.Exit):
        emit_error(_ctx("human"), exc)
    assert "Bad request" in capsys.readouterr().err


def test_emit_workflow_error_res_3002_json(capsys) -> None:
    exc = ApiClientError(
        message="Duplicate",
        status_code=409,
        error_code="RES_3002",
        details=[{"field": "application_id", "message": "app-1", "code": "DUPLICATE_APPLICATION"}],
    )
    with pytest.raises(typer.Exit) as raised:
        emit_workflow_error(_ctx("json"), exc)
    assert raised.value.exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["warning"] is True
    assert payload["application_id"] == "app-1"


def test_emit_workflow_error_res_3002_human(capsys) -> None:
    exc = ApiClientError(message="Duplicate", status_code=409, error_code="RES_3002")
    with pytest.raises(typer.Exit) as raised:
        emit_workflow_error(_ctx("human"), exc)
    assert raised.value.exit_code == 0
    assert "Warning" in capsys.readouterr().err


def test_emit_workflow_error_cfg_6001_json(capsys) -> None:
    exc = ApiClientError(message="No key", status_code=422, error_code="CFG_6001")
    with pytest.raises(typer.Exit) as raised:
        emit_workflow_error(_ctx("json"), exc)
    assert raised.value.exit_code != 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["error_code"] == "CFG_6001"
    assert "hint" in payload


def test_emit_workflow_error_cfg_6001_human(capsys) -> None:
    exc = ApiClientError(message="No key", status_code=422, error_code="CFG_6001")
    with pytest.raises(typer.Exit):
        emit_workflow_error(_ctx("human"), exc)
    err = capsys.readouterr().err
    assert "api-key set" in err.lower()


def test_emit_workflow_error_falls_through_to_emit_error(capsys) -> None:
    exc = ApiClientError(message="Not found", status_code=404, error_code="RES_3001", exit_code=ExitCode.ERROR)
    with pytest.raises(typer.Exit) as raised:
        emit_workflow_error(_ctx("human"), exc)
    assert raised.value.exit_code == int(ExitCode.ERROR)


def test_emit_duplicate_application_human_ids(capsys) -> None:
    exc = ApiClientError(
        message="Dup",
        status_code=409,
        error_code="RES_3002",
        details=[
            {"field": "session_id", "message": "sess-9", "code": "DUPLICATE_APPLICATION"},
        ],
    )
    with pytest.raises(typer.Exit):
        emit_duplicate_application(_ctx("human"), exc)
    out = capsys.readouterr().out
    assert "sess-9" in out


def test_persist_auth_response_skips_without_token(applypilot_home) -> None:
    persist_auth_response({"message": "no token"})
    assert not (applypilot_home / "credentials.json").exists()


def test_persist_auth_response_saves_token(applypilot_home) -> None:
    persist_auth_response({"access_token": "abc.def.ghi", "user": {"email": "a@b.com"}})
    data = json.loads((applypilot_home / "credentials.json").read_text())
    assert data["access_token"] == "abc.def.ghi"
    assert data["email"] == "a@b.com"
