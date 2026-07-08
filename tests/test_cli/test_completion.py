"""Tests for shell completion script generation."""

from __future__ import annotations

import pytest


@pytest.fixture
def typer_explicit_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    """Typer accepts shell names as values when auto-detection is disabled."""
    monkeypatch.setenv("_TYPER_COMPLETE_TEST_DISABLE_SHELL_DETECTION", "1")


def test_show_completion_bash(invoke, typer_explicit_shell) -> None:
    result = invoke("--show-completion", "bash")
    assert result.exit_code == 0
    assert "applypilot" in result.output
    assert "_APPLYPILOT_COMPLETE" in result.output


def test_show_completion_zsh(invoke, typer_explicit_shell) -> None:
    result = invoke("--show-completion", "zsh")
    assert result.exit_code == 0
    assert "applypilot" in result.output
    assert "compdef" in result.output


def test_completion_flags_in_help(invoke) -> None:
    result = invoke("--help")
    assert result.exit_code == 0
    assert "--install-completion" in result.output
    assert "--show-completion" in result.output
