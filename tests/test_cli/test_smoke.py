"""Smoke tests — every command group loads and shows --help without errors."""

from __future__ import annotations

import pytest

# Top-level Typer groups registered in cli/main.py
TOP_LEVEL_GROUPS = [
    "doctor",
    "auth",
    "profile",
    "workflow",
    "apps",
    "interview",
    "cv",
    "tools",
    "extension",
    "admin",
]

# Nested groups worth verifying (import / registration errors surface here)
NESTED_GROUPS = [
    ["auth", "token"],
    ["profile", "set"],
    ["profile", "resume"],
    ["profile", "api-key"],
    ["profile", "workflow-preferences"],
    ["workflow", "regenerate"],
    ["tools", "schema"],
    ["extension", "autofill"],
    ["admin", "maintenance"],
]


@pytest.mark.parametrize("group", TOP_LEVEL_GROUPS)
def test_top_level_group_help(invoke, group: str) -> None:
    result = invoke(group, "--help")
    assert result.exit_code == 0, result.output
    assert "Usage:" in result.output


@pytest.mark.parametrize("parts", NESTED_GROUPS)
def test_nested_group_help(invoke, parts: list[str]) -> None:
    result = invoke(*parts, "--help")
    assert result.exit_code == 0, result.output
    assert "Usage:" in result.output


def test_root_help(invoke) -> None:
    result = invoke("--help")
    assert result.exit_code == 0
    assert "applypilot" in result.output.lower()
    assert "workflow" in result.output


def test_version_command(invoke) -> None:
    result = invoke("version")
    assert result.exit_code == 0
    assert result.output.strip()
