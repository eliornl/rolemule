"""Tests for interview prep polling."""

from __future__ import annotations

import pytest

from applypilot_client.polling import InterviewPollTimeout, wait_for_interview_prep


def test_wait_until_prep_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}
    statuses = [
        {"session_id": "s1", "has_interview_prep": False, "is_generating": True},
        {"session_id": "s1", "has_interview_prep": True, "is_generating": False},
    ]

    def get_status() -> dict:
        idx = min(calls["n"], len(statuses) - 1)
        calls["n"] += 1
        return statuses[idx]

    monkeypatch.setattr("applypilot_client.polling.time.sleep", lambda _s: None)
    result = wait_for_interview_prep(get_status, interval_seconds=0.01, timeout_seconds=5)
    assert result["has_interview_prep"] is True


def test_wait_generation_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("applypilot_client.polling.time.sleep", lambda _s: None)
    with pytest.raises(InterviewPollTimeout) as exc:
        wait_for_interview_prep(
            lambda: {"session_id": "s2", "has_interview_prep": False, "is_generating": False},
            interval_seconds=0.01,
            timeout_seconds=5,
        )
    assert exc.value.generation_failed is True
