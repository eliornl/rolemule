"""Tests for applypilot_client.polling."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from applypilot_client.polling import WorkflowPollTimeout, wait_for_terminal_status


def test_wait_until_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}
    statuses = [
        {"session_id": "s1", "status": "initialized", "progress_percentage": 0},
        {"session_id": "s1", "status": "in_progress", "progress_percentage": 40},
        {"session_id": "s1", "status": "completed", "progress_percentage": 100},
    ]

    def get_status() -> dict:
        idx = min(calls["n"], len(statuses) - 1)
        calls["n"] += 1
        return statuses[idx]

    monkeypatch.setattr("applypilot_client.polling.time.sleep", lambda _s: None)
    result = wait_for_terminal_status(get_status, interval_seconds=0.01, timeout_seconds=5)
    assert result["status"] == "completed"


def test_wait_stops_on_awaiting_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("applypilot_client.polling.time.sleep", lambda _s: None)
    result = wait_for_terminal_status(
        lambda: {"session_id": "s2", "status": "awaiting_confirmation"},
        interval_seconds=0.01,
        timeout_seconds=5,
    )
    assert result["status"] == "awaiting_confirmation"


def test_wait_stops_on_analysis_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("applypilot_client.polling.time.sleep", lambda _s: None)
    result = wait_for_terminal_status(
        lambda: {"session_id": "s3", "status": "analysis_complete"},
        interval_seconds=0.01,
        timeout_seconds=5,
    )
    assert result["status"] == "analysis_complete"


def test_wait_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("applypilot_client.polling.time.sleep", lambda _s: None)
    monkeypatch.setattr(
        "applypilot_client.polling.time.monotonic",
        MagicMock(side_effect=[0.0, 0.0, 1000.0]),
    )
    with pytest.raises(WorkflowPollTimeout):
        wait_for_terminal_status(
            lambda: {"session_id": "s4", "status": "in_progress"},
            interval_seconds=0.01,
            timeout_seconds=1.0,
        )


def test_on_progress_called(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr("applypilot_client.polling.time.sleep", lambda _s: None)

    wait_for_terminal_status(
        lambda: {"session_id": "s5", "status": "failed"},
        interval_seconds=0.01,
        timeout_seconds=5,
        on_progress=lambda st: seen.append(st["status"]),
    )
    assert seen == ["failed"]
