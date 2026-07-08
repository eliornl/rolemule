"""Tests for cli.workflow_watch human formatting."""

from __future__ import annotations

from cli.workflow_watch import format_watch_event


def test_format_agent_update() -> None:
    line = format_watch_event(
        {
            "type": "agent_update",
            "data": {"agent": "job_analyzer", "status": "running", "message": "Parsing posting"},
        }
    )
    assert line == "[agent] job_analyzer: running — Parsing posting"


def test_format_workflow_complete() -> None:
    line = format_watch_event(
        {"type": "workflow_complete", "session_id": "sess-1", "data": {}}
    )
    assert "sess-1" in line
    assert "[done]" in line


def test_format_gate_decision() -> None:
    line = format_watch_event(
        {
            "type": "gate_decision",
            "session_id": "sess-9",
            "data": {"match_score": 0.42, "requires_confirmation": True},
        }
    )
    assert "42%" in line
    assert "workflow continue sess-9" in line


def test_format_workflow_error() -> None:
    line = format_watch_event(
        {
            "type": "workflow_error",
            "data": {"error": "Quota exceeded", "failed_agent": "cover_letter_writer"},
        }
    )
    assert "cover_letter_writer" in line
    assert "Quota exceeded" in line


def test_format_pong_returns_none() -> None:
    assert format_watch_event({"type": "pong", "data": {}}) is None
