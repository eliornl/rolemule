"""Tests for config subcommands."""

from __future__ import annotations

import json

from cli.config import load_config


def test_config_show_human(invoke, applypilot_home) -> None:
    result = invoke("config")
    assert result.exit_code == 0
    assert "base_url:" in result.stdout


def test_config_show_json(invoke, applypilot_home) -> None:
    result = invoke("--format", "json", "config")
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "base_url" in payload
    assert payload["default_format"] == "human"


def test_config_set_base_url(invoke, applypilot_home) -> None:
    result = invoke("config", "set", "--base-url", "https://apply.example.com")
    assert result.exit_code == 0
    assert load_config().base_url == "https://apply.example.com"


def test_config_set_requires_option(invoke, applypilot_home) -> None:
    result = invoke("config", "set")
    assert result.exit_code == 1
    assert "at least one option" in result.output.lower()
