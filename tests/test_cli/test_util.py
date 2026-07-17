"""Unit tests for cli/util.py helpers."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest
import typer

from rolemule_client.errors import ExitCode
from cli.util import filename_from_headers, payload_from_file, require_confirm


def test_payload_from_file_object(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    path.write_text(json.dumps({"a": 1}), encoding="utf-8")
    assert payload_from_file(str(path)) == {"a": 1}


def test_payload_from_file_stdin() -> None:
    old = sys.stdin
    sys.stdin = io.StringIO('{"stdin": true}')
    try:
        data = payload_from_file("-")
    finally:
        sys.stdin = old
    assert data == {"stdin": True}


def test_payload_from_file_array_wrapper(tmp_path: Path) -> None:
    path = tmp_path / "arr.json"
    path.write_text(json.dumps([{"company": "Acme"}]), encoding="utf-8")
    data = payload_from_file(str(path), wrapper_key="work_experience")
    assert data == {"work_experience": [{"company": "Acme"}]}


def test_payload_from_file_rejects_non_object(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('"string"', encoding="utf-8")
    with pytest.raises(typer.BadParameter):
        payload_from_file(str(path))


def test_require_confirm_blocks_without_flag() -> None:
    with pytest.raises(typer.Exit) as exc:
        require_confirm(False, "delete everything")
    assert exc.value.exit_code == int(ExitCode.ERROR)


def test_require_confirm_passes_with_flag() -> None:
    require_confirm(True, "delete everything")


def test_filename_from_headers_parses() -> None:
    assert filename_from_headers({"content-disposition": 'attachment; filename="cv.odt"'}, "fallback.odt") == "cv.odt"


def test_filename_from_headers_fallback() -> None:
    assert filename_from_headers({}, "default.pdf") == "default.pdf"
