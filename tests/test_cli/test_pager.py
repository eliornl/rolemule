"""Tests for cli.pager."""

from __future__ import annotations

from unittest.mock import patch

from cli.pager import maybe_page


def test_maybe_page_no_pager_writes_stdout(capsys) -> None:
    maybe_page("line one\nline two", no_pager=True)
    assert "line one" in capsys.readouterr().out


def test_maybe_page_short_output_skips_pager(capsys) -> None:
    with patch("cli.pager.subprocess.run") as run_mock:
        maybe_page("short", no_pager=False)
    run_mock.assert_not_called()
    assert "short" in capsys.readouterr().out


def test_maybe_page_long_output_invokes_pager(capsys) -> None:
    text = "\n".join(f"line {i}" for i in range(200))
    with patch("cli.pager.os.get_terminal_size", return_value=type("S", (), {"lines": 24})()):
        with patch("cli.pager.shutil.which", return_value="/usr/bin/less"):
            with patch("cli.pager.subprocess.run") as run_mock:
                maybe_page(text, no_pager=False)
    run_mock.assert_called_once()
