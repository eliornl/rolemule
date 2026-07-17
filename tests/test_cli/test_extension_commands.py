"""Tests for rolemule extension commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from rolemule_client.errors import ApiClientError, ExitCode

SAMPLE_BODY = {
    "page_url": "https://careers.example.com/apply",
    "fields": [
        {
            "field_uid": "0",
            "tag": "input",
            "input_type": "text",
            "label_text": "First name",
        }
    ],
}

AUTOFILL_RESPONSE = {
    "assignments": [{"field_uid": "0", "value": "Jane", "label_text": "First name"}],
    "skipped": [{"field_uid": "1", "reason": "File upload handled separately"}],
    "warnings": ["Review every value before applying."],
}


def test_extension_autofill_map(invoke, write_credentials, tmp_path: Path) -> None:
    write_credentials()
    req = tmp_path / "fields.json"
    req.write_text(json.dumps(SAMPLE_BODY), encoding="utf-8")
    mock_client = MagicMock()
    mock_client.extension.autofill_map.return_value = AUTOFILL_RESPONSE

    with patch("cli.commands.extension.require_client", return_value=mock_client):
        result = invoke("extension", "autofill", "map", "--file", str(req))
    assert result.exit_code == 0
    assert "Assignments" in result.output
    assert "Jane" in result.output
    mock_client.extension.autofill_map.assert_called_once_with(SAMPLE_BODY)


def test_extension_autofill_map_url_override(invoke, write_credentials, tmp_path: Path) -> None:
    write_credentials()
    req = tmp_path / "fields.json"
    req.write_text(json.dumps({**SAMPLE_BODY, "page_url": "https://old.example.com/apply"}), encoding="utf-8")
    mock_client = MagicMock()
    mock_client.extension.autofill_map.return_value = AUTOFILL_RESPONSE

    with patch("cli.commands.extension.require_client", return_value=mock_client):
        result = invoke(
            "extension",
            "autofill",
            "map",
            "--file",
            str(req),
            "--url",
            "https://careers.example.com/apply",
        )
    assert result.exit_code == 0
    sent = mock_client.extension.autofill_map.call_args[0][0]
    assert sent["page_url"] == "https://careers.example.com/apply"


def test_extension_autofill_map_json(invoke, write_credentials, tmp_path: Path) -> None:
    write_credentials()
    req = tmp_path / "fields.json"
    req.write_text(json.dumps(SAMPLE_BODY), encoding="utf-8")
    mock_client = MagicMock()
    mock_client.extension.autofill_map.return_value = AUTOFILL_RESPONSE

    with patch("cli.commands.extension.require_client", return_value=mock_client):
        result = invoke("--format", "json", "extension", "autofill", "map", "--file", str(req))
    assert result.exit_code == 0
    assert json.loads(result.stdout)["assignments"][0]["value"] == "Jane"


def test_extension_autofill_missing_fields(invoke, write_credentials, tmp_path: Path) -> None:
    write_credentials()
    req = tmp_path / "bad.json"
    req.write_text(json.dumps({"page_url": "https://careers.example.com/apply"}), encoding="utf-8")
    result = invoke("extension", "autofill", "map", "--file", str(req))
    assert result.exit_code != 0


def test_extension_autofill_rate_limit(invoke, write_credentials, tmp_path: Path) -> None:
    write_credentials()
    req = tmp_path / "fields.json"
    req.write_text(json.dumps(SAMPLE_BODY), encoding="utf-8")
    mock_client = MagicMock()
    mock_client.extension.autofill_map.side_effect = ApiClientError(
        message="Rate limit exceeded",
        status_code=429,
        error_code="RATE_4001",
        exit_code=ExitCode.RATE_LIMITED,
    )

    with patch("cli.commands.extension.require_client", return_value=mock_client):
        result = invoke("extension", "autofill", "map", "--file", str(req))
    assert result.exit_code == int(ExitCode.RATE_LIMITED)
