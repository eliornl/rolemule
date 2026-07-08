"""Tests for CV optimization polling."""

from __future__ import annotations

import pytest

from applypilot_client.polling import CvPollTimeout, wait_for_cv_optimization


def test_wait_until_result_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}
    statuses = [
        {"session_id": "s1", "has_result": False, "is_running": True, "best_score": 7.0},
        {"session_id": "s1", "has_result": True, "is_running": False, "best_score": 8.2},
    ]

    def get_status() -> dict:
        idx = min(calls["n"], len(statuses) - 1)
        calls["n"] += 1
        return statuses[idx]

    monkeypatch.setattr("applypilot_client.polling.time.sleep", lambda _s: None)
    result = wait_for_cv_optimization(get_status, interval_seconds=0.01, timeout_seconds=5)
    assert result["has_result"] is True
    assert result["best_score"] == 8.2


def test_wait_failed_without_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("applypilot_client.polling.time.sleep", lambda _s: None)
    with pytest.raises(CvPollTimeout) as exc:
        wait_for_cv_optimization(
            lambda: {"session_id": "s2", "has_result": False, "is_running": False},
            interval_seconds=0.01,
            timeout_seconds=5,
        )
    assert exc.value.failed is True
