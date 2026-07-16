"""
Integration tests for Mock Interview API.

Endpoints:
  GET  /api/v1/mock-interview/{session_id}
  GET  /api/v1/mock-interview/{session_id}/status
  POST /api/v1/mock-interview/{session_id}/start
  POST /api/v1/mock-interview/{session_id}/turn
  POST /api/v1/mock-interview/{session_id}/finish
  POST /api/v1/mock-interview/{session_id}/abort
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BASE = "/api/v1/mock-interview"
SESSION_ID = str(uuid.uuid4())


def _mock_ws() -> MagicMock:
    ws = MagicMock()
    ws.session_id = SESSION_ID
    ws.user_id = uuid.uuid4()
    ws.job_analysis = {"job_title": "Engineer", "company_name": "Acme"}
    ws.company_research = {}
    ws.profile_matching = {}
    ws.user_data = {"professional_title": "Engineer"}
    ws.interview_prep = None
    ws.mock_interview = None
    return ws


@pytest.mark.asyncio
async def test_get_no_auth(api_client):
    resp = await api_client.get(f"{BASE}/{SESSION_ID}")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_not_found(authed_client):
    from utils.error_responses import not_found_error

    with patch(
        "api.mock_interview._load_owned_session",
        AsyncMock(side_effect=not_found_error("Workflow session")),
    ):
        resp = await authed_client.get(f"{BASE}/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_start_validation_invalid_style(authed_client):
    resp = await authed_client.post(
        f"{BASE}/{SESSION_ID}/start",
        json={"style": "intern", "duration_minutes": 15},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_start_validation_invalid_duration(authed_client):
    resp = await authed_client.post(
        f"{BASE}/{SESSION_ID}/start",
        json={"style": "hr", "duration_minutes": 12},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_start_happy_path(authed_client):
    ws = _mock_ws()
    opened = {
        "speak": "Tell me about yourself.",
        "act": "next_question",
        "plan": [],
        "running_notes": [],
    }
    llm_ctx = MagicMock(user_api_key="key", provider="gemini", ready=True)

    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(True, 9))), \
         patch("api.mock_interview.require_user_llm_context", AsyncMock(return_value=(None, llm_ctx, None))), \
         patch("api.mock_interview.load_preferred_model", AsyncMock(return_value=None)), \
         patch("api.mock_interview.set_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.clear_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.broadcast_mock_interview_started", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_thinking", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_utterance", AsyncMock()), \
         patch("api.mock_interview._save_store", AsyncMock()), \
         patch(
             "api.mock_interview.MockInterviewAgent.open_session",
             AsyncMock(return_value=opened),
         ):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/start",
            json={"style": "hr", "duration_minutes": 15},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "asking"
    assert "Tell me about yourself" in data["speak"]
    assert data["ends_at"]


@pytest.mark.asyncio
async def test_start_broadcasts_speak_delta(authed_client):
    ws = _mock_ws()
    opened = {
        "speak": "Hello there.",
        "act": "next_question",
        "plan": [],
        "running_notes": [],
    }
    llm_ctx = MagicMock(user_api_key="key", provider="gemini", ready=True)
    delta_broadcast = AsyncMock()

    async def _open_session(**kwargs):
        cb = kwargs.get("on_speak_delta")
        assert cb is not None
        await cb("Hello ")
        await cb("there.")
        return opened

    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(True, 9))), \
         patch("api.mock_interview.require_user_llm_context", AsyncMock(return_value=(None, llm_ctx, None))), \
         patch("api.mock_interview.load_preferred_model", AsyncMock(return_value=None)), \
         patch("api.mock_interview.set_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.clear_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.broadcast_mock_interview_started", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_thinking", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_speak_delta", delta_broadcast), \
         patch("api.mock_interview.broadcast_mock_interview_utterance", AsyncMock()), \
         patch("api.mock_interview._save_store", AsyncMock()), \
         patch(
             "api.mock_interview.MockInterviewAgent.open_session",
             AsyncMock(side_effect=_open_session),
         ):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/start",
            json={"style": "hr", "duration_minutes": 15},
        )

    assert resp.status_code == 200
    assert delta_broadcast.await_count == 2
    assert delta_broadcast.await_args_list[0].kwargs["delta"] == "Hello "
    assert delta_broadcast.await_args_list[1].kwargs["delta"] == "there."


@pytest.mark.asyncio
async def test_start_cfg_6001(authed_client):
    from utils.error_responses import no_api_key_error

    ws = _mock_ws()
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(True, 9))), \
         patch(
             "api.mock_interview.require_user_llm_context",
             AsyncMock(side_effect=no_api_key_error()),
         ):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/start",
            json={"style": "pro", "duration_minutes": 10},
        )
    assert resp.status_code == 422
    assert resp.json().get("error_code") == "CFG_6001"


@pytest.mark.asyncio
async def test_start_conflict_when_active(authed_client):
    ws = _mock_ws()
    ws.mock_interview = {
        "version": 1,
        "active": {
            "run_id": "x",
            "status": "asking",
            "style": "hr",
            "ends_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            "turns": [],
        },
        "history": [],
    }
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(True, 9))):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/start",
            json={"style": "manager", "duration_minutes": 20},
        )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_turn_wrap_up_on_time_expiry(authed_client):
    ws = _mock_ws()
    ends = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    ws.mock_interview = {
        "version": 1,
        "active": {
            "run_id": "run-1",
            "status": "asking",
            "style": "hr",
            "ends_at": ends,
            "plan": [],
            "turns": [{"idx": 0, "role": "interviewer", "text": "Q?", "source": "tts"}],
            "running_notes": [],
        },
        "history": [],
    }
    llm_ctx = MagicMock(user_api_key="key", provider="gemini", ready=True)
    nxt = {
        "speak": "Thanks for practicing.",
        "act": "wrap_up",
        "scores": {"content": 7, "structure": 7, "clarity": 7},
        "running_notes": [],
    }
    debrief = {
        "overall_score": 7,
        "scores": {"content": 7, "structure": 7, "clarity": 7, "role_fit": 7, "style_focus": 7},
        "strengths": ["a"],
        "improvements": ["b"],
        "weakest_answer_rewrite": "x",
        "summary": "ok",
    }

    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(True, 39))), \
         patch("api.mock_interview.require_user_llm_context", AsyncMock(return_value=(None, llm_ctx, None))), \
         patch("api.mock_interview.load_preferred_model", AsyncMock(return_value=None)), \
         patch("api.mock_interview.set_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.clear_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.broadcast_mock_interview_thinking", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_utterance", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_turn_scored", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_complete", AsyncMock()), \
         patch("api.mock_interview._save_store", AsyncMock()), \
         patch("api.mock_interview.MockInterviewAgent.next_turn", AsyncMock(return_value=nxt)), \
         patch("api.mock_interview.MockInterviewAgent.debrief", AsyncMock(return_value=debrief)):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/turn",
            json={"transcript": "I delivered a project that cut costs by 20%.", "source": "typed"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "complete"
    assert data["debrief"]["overall_score"] == 7


@pytest.mark.asyncio
async def test_abort(authed_client):
    ws = _mock_ws()
    ws.mock_interview = {
        "version": 1,
        "active": {
            "run_id": "run-2",
            "status": "asking",
            "style": "pro",
            "ends_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            "turns": [],
        },
        "history": [],
    }
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.is_mock_interview_thinking", AsyncMock(return_value=False)), \
         patch("api.mock_interview._save_store", AsyncMock()) as save:
        resp = await authed_client.post(f"{BASE}/{SESSION_ID}/abort")
    assert resp.status_code == 200
    assert resp.json()["status"] == "aborted"
    save.assert_awaited()


@pytest.mark.asyncio
async def test_status_fields(authed_client):
    ws = _mock_ws()
    ends = (datetime.now(timezone.utc) + timedelta(minutes=8)).isoformat()
    ws.mock_interview = {
        "version": 1,
        "active": {
            "run_id": "r",
            "status": "asking",
            "style": "hr",
            "ends_at": ends,
            "turns": [],
        },
        "history": [],
    }
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.is_mock_interview_thinking", AsyncMock(return_value=False)):
        resp = await authed_client.get(f"{BASE}/{SESSION_ID}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "asking"
    assert data["run_id"] == "r"
    assert data["is_thinking"] is False
    assert isinstance(data["seconds_remaining"], int)


@pytest.mark.asyncio
async def test_finish_early(authed_client):
    ws = _mock_ws()
    ws.mock_interview = {
        "version": 1,
        "active": {
            "run_id": "run-finish",
            "status": "asking",
            "style": "manager",
            "ends_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            "turns": [{"idx": 0, "role": "interviewer", "text": "Q?", "source": "tts"}],
            "running_notes": [],
        },
        "history": [],
    }
    llm_ctx = MagicMock(user_api_key="key", provider="gemini", ready=True)
    debrief = {
        "overall_score": 6,
        "scores": {"content": 6, "structure": 6, "clarity": 6, "role_fit": 6, "style_focus": 6},
        "strengths": ["clear"],
        "improvements": ["more metrics"],
        "weakest_answer_rewrite": "…",
        "summary": "Decent start",
    }
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(True, 9))), \
         patch("api.mock_interview.require_user_llm_context", AsyncMock(return_value=(None, llm_ctx, None))), \
         patch("api.mock_interview.load_preferred_model", AsyncMock(return_value=None)), \
         patch("api.mock_interview.set_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.clear_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.is_mock_interview_thinking", AsyncMock(return_value=False)), \
         patch("api.mock_interview.broadcast_mock_interview_thinking", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_complete", AsyncMock()), \
         patch("api.mock_interview._save_store", AsyncMock()), \
         patch("api.mock_interview.MockInterviewAgent.debrief", AsyncMock(return_value=debrief)):
        resp = await authed_client.post(f"{BASE}/{SESSION_ID}/finish")
    assert resp.status_code == 200
    assert resp.json()["status"] == "complete"
    assert resp.json()["debrief"]["overall_score"] == 6


@pytest.mark.asyncio
async def test_finish_includes_final_answer_in_debrief_turns(authed_client):
    ws = _mock_ws()
    ws.mock_interview = {
        "version": 1,
        "active": {
            "run_id": "run-finish-draft",
            "status": "asking",
            "style": "hr",
            "ends_at": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(),
            "turns": [
                {
                    "idx": 0,
                    "role": "interviewer",
                    "text": "Tell me about a project.",
                    "source": "tts",
                }
            ],
            "running_notes": [],
        },
        "history": [],
    }
    llm_ctx = MagicMock(user_api_key="key", provider="gemini", ready=True)
    debrief = {
        "overall_score": 5,
        "scores": {
            "content": 5,
            "structure": 4,
            "clarity": 4,
            "role_fit": 6,
            "style_focus": 5,
        },
        "strengths": ["enthusiasm"],
        "improvements": ["structure"],
        "answer_reviews": [],
        "weakest_answer_rewrite": "As founding engineer I owned…",
        "summary": "Solid raw material, tighten structure.",
    }
    debrief_mock = AsyncMock(return_value=debrief)
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(True, 9))), \
         patch("api.mock_interview.require_user_llm_context", AsyncMock(return_value=(None, llm_ctx, None))), \
         patch("api.mock_interview.load_preferred_model", AsyncMock(return_value=None)), \
         patch("api.mock_interview.set_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.clear_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.is_mock_interview_thinking", AsyncMock(return_value=False)), \
         patch("api.mock_interview.broadcast_mock_interview_thinking", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_complete", AsyncMock()), \
         patch("api.mock_interview._save_store", AsyncMock()), \
         patch("api.mock_interview.MockInterviewAgent.debrief", debrief_mock):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/finish",
            json={
                "final_answer": "I built a scalable API from scratch using Python.",
                "source": "typed",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "complete"
    assert debrief_mock.await_count == 1
    turns = debrief_mock.await_args.kwargs["turns"]
    candidate = [t for t in turns if t.get("role") == "candidate"]
    assert len(candidate) == 1
    assert "scalable API" in candidate[0]["text"]


@pytest.mark.asyncio
async def test_start_rate_limited(authed_client):
    ws = _mock_ws()
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(False, 0))):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/start",
            json={"style": "hr", "duration_minutes": 15},
        )
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_start_requires_job_analysis(authed_client):
    ws = _mock_ws()
    ws.job_analysis = None
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(True, 9))):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/start",
            json={"style": "hr", "duration_minutes": 15},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_empty_store(authed_client):
    ws = _mock_ws()
    ws.mock_interview = None
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.is_mock_interview_thinking", AsyncMock(return_value=False)):
        resp = await authed_client.get(f"{BASE}/{SESSION_ID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active"] is None
    assert data["history"] == []
    assert data["is_thinking"] is False


@pytest.mark.asyncio
async def test_turn_no_active(authed_client):
    ws = _mock_ws()
    ws.mock_interview = {"version": 1, "active": None, "history": []}
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(True, 39))):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/turn",
            json={"transcript": "I delivered results with a clear STAR story.", "source": "typed"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_turn_empty_transcript(authed_client):
    resp = await authed_client.post(
        f"{BASE}/{SESSION_ID}/turn",
        json={"transcript": "   ", "source": "typed"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_turn_thinking_lock_conflict(authed_client):
    ws = _mock_ws()
    ws.mock_interview = {
        "version": 1,
        "active": {
            "run_id": "run-busy",
            "status": "thinking",
            "style": "hr",
            "ends_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            "turns": [],
        },
        "history": [],
    }
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(True, 39))), \
         patch("api.mock_interview.is_mock_interview_thinking", AsyncMock(return_value=True)):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/turn",
            json={"transcript": "Still waiting on the previous answer processing.", "source": "typed"},
        )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_turn_continues_asking(authed_client):
    ws = _mock_ws()
    ws.mock_interview = {
        "version": 1,
        "active": {
            "run_id": "run-cont",
            "status": "asking",
            "style": "pro",
            "ends_at": (datetime.now(timezone.utc) + timedelta(minutes=12)).isoformat(),
            "plan": [],
            "turns": [{"idx": 0, "role": "interviewer", "text": "Q?", "source": "tts"}],
            "running_notes": [],
        },
        "history": [],
    }
    llm_ctx = MagicMock(user_api_key="key", provider="gemini", ready=True)
    nxt = {
        "speak": "Can you go deeper on the architecture?",
        "act": "follow_up",
        "scores": {"content": 8, "structure": 7, "clarity": 8},
        "running_notes": ["probe depth"],
    }
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(True, 39))), \
         patch("api.mock_interview.require_user_llm_context", AsyncMock(return_value=(None, llm_ctx, None))), \
         patch("api.mock_interview.load_preferred_model", AsyncMock(return_value=None)), \
         patch("api.mock_interview.set_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.clear_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.broadcast_mock_interview_thinking", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_utterance", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_turn_scored", AsyncMock()), \
         patch("api.mock_interview._save_store", AsyncMock()), \
         patch("api.mock_interview.MockInterviewAgent.next_turn", AsyncMock(return_value=nxt)):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/turn",
            json={"transcript": "I designed a cache with TTL and sharding.", "source": "stt"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "asking"
    assert data["act"] == "follow_up"
    assert "architecture" in data["speak"].lower()
    assert data["debrief"] is None


@pytest.mark.asyncio
async def test_abort_no_active(authed_client):
    ws = _mock_ws()
    ws.mock_interview = {"version": 1, "active": None, "history": []}
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)):
        resp = await authed_client.post(f"{BASE}/{SESSION_ID}/abort")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_finish_no_active(authed_client):
    ws = _mock_ws()
    ws.mock_interview = {"version": 1, "active": None, "history": []}
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)):
        resp = await authed_client.post(f"{BASE}/{SESSION_ID}/finish")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_start_busy_lock_conflict(authed_client):
    ws = _mock_ws()
    llm_ctx = MagicMock(user_api_key="key", provider="gemini", ready=True)
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(True, 9))), \
         patch("api.mock_interview.require_user_llm_context", AsyncMock(return_value=(None, llm_ctx, None))), \
         patch("api.mock_interview.load_preferred_model", AsyncMock(return_value=None)), \
         patch("api.mock_interview.set_mock_interview_thinking", AsyncMock(return_value=False)):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/start",
            json={"style": "hr", "duration_minutes": 15},
        )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_abort_while_thinking_conflict(authed_client):
    ws = _mock_ws()
    ws.mock_interview = {
        "version": 1,
        "active": {
            "run_id": "run-busy-abort",
            "status": "asking",
            "style": "hr",
            "ends_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            "turns": [],
        },
        "history": [],
    }
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.is_mock_interview_thinking", AsyncMock(return_value=True)):
        resp = await authed_client.post(f"{BASE}/{SESSION_ID}/abort")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_start_rejects_open_wrap_up(authed_client):
    ws = _mock_ws()
    llm_ctx = MagicMock(user_api_key="key", provider="gemini", ready=True)
    opened = {
        "speak": "Thanks for that answer. Let's wrap up this practice for now.",
        "act": "wrap_up",
        "error": "parse_error",
        "plan": [],
        "running_notes": [],
    }
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(True, 9))), \
         patch("api.mock_interview.require_user_llm_context", AsyncMock(return_value=(None, llm_ctx, None))), \
         patch("api.mock_interview.load_preferred_model", AsyncMock(return_value=None)), \
         patch("api.mock_interview.set_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.clear_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.broadcast_mock_interview_started", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_thinking", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_error", AsyncMock()), \
         patch(
             "api.mock_interview.MockInterviewAgent.open_session",
             AsyncMock(return_value=opened),
         ):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/start",
            json={"style": "hr", "duration_minutes": 15},
        )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_finish_rate_limited(authed_client):
    ws = _mock_ws()
    ws.mock_interview = {
        "version": 1,
        "active": {
            "run_id": "run-rl",
            "status": "asking",
            "style": "hr",
            "ends_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            "turns": [],
        },
        "history": [],
    }
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(False, 0))):
        resp = await authed_client.post(f"{BASE}/{SESSION_ID}/finish")
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_turn_stale_thinking_recovers_when_lock_clear(authed_client):
    ws = _mock_ws()
    ws.mock_interview = {
        "version": 1,
        "active": {
            "run_id": "run-stale",
            "status": "thinking",
            "style": "hr",
            "ends_at": (datetime.now(timezone.utc) + timedelta(minutes=8)).isoformat(),
            "plan": [],
            "turns": [{"idx": 0, "role": "interviewer", "text": "Q?", "source": "tts"}],
            "running_notes": [],
        },
        "history": [],
    }
    llm_ctx = MagicMock(user_api_key="key", provider="gemini", ready=True)
    nxt = {
        "speak": "Tell me more.",
        "act": "follow_up",
        "scores": {"content": 6, "structure": 6, "clarity": 6},
        "running_notes": [],
    }
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(True, 39))), \
         patch("api.mock_interview.is_mock_interview_thinking", AsyncMock(return_value=False)), \
         patch("api.mock_interview.require_user_llm_context", AsyncMock(return_value=(None, llm_ctx, None))), \
         patch("api.mock_interview.load_preferred_model", AsyncMock(return_value=None)), \
         patch("api.mock_interview.set_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.clear_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.broadcast_mock_interview_thinking", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_utterance", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_turn_scored", AsyncMock()), \
         patch("api.mock_interview._save_store", AsyncMock()), \
         patch("api.mock_interview.MockInterviewAgent.next_turn", AsyncMock(return_value=nxt)):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/turn",
            json={"transcript": "Recovering from a stale thinking state.", "source": "typed"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "asking"


@pytest.mark.asyncio
async def test_turn_parse_error_does_not_complete(authed_client):
    ws = _mock_ws()
    active = {
        "run_id": "run-parse",
        "status": "asking",
        "style": "hr",
        "ends_at": (datetime.now(timezone.utc) + timedelta(minutes=8)).isoformat(),
        "plan": [],
        "turns": [{"idx": 0, "role": "interviewer", "text": "Q?", "source": "tts"}],
        "running_notes": [],
    }
    ws.mock_interview = {"version": 1, "active": active, "history": []}
    llm_ctx = MagicMock(user_api_key="key", provider="gemini", ready=True)
    nxt = {
        "error": "parse_error",
        "speak": "Please try again.",
        "act": "next_question",
        "scores": {"content": 5, "structure": 5, "clarity": 5},
        "running_notes": [],
    }
    save = AsyncMock()
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(True, 39))), \
         patch("api.mock_interview.is_mock_interview_thinking", AsyncMock(return_value=False)), \
         patch("api.mock_interview.require_user_llm_context", AsyncMock(return_value=(None, llm_ctx, None))), \
         patch("api.mock_interview.load_preferred_model", AsyncMock(return_value=None)), \
         patch("api.mock_interview.set_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.clear_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.broadcast_mock_interview_thinking", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_error", AsyncMock()), \
         patch("api.mock_interview._save_store", save), \
         patch("api.mock_interview.MockInterviewAgent.next_turn", AsyncMock(return_value=nxt)):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/turn",
            json={"transcript": "An answer that should stay in progress.", "source": "typed"},
        )
    assert resp.status_code == 500
    save.assert_not_awaited()
    assert ws.mock_interview["active"]["status"] == "asking"
    assert ws.mock_interview["active"] is active


@pytest.mark.asyncio
async def test_turn_llm_exception_does_not_save(authed_client):
    ws = _mock_ws()
    active = {
        "run_id": "run-exc",
        "status": "asking",
        "style": "hr",
        "ends_at": (datetime.now(timezone.utc) + timedelta(minutes=8)).isoformat(),
        "plan": [],
        "turns": [{"idx": 0, "role": "interviewer", "text": "Q?", "source": "tts"}],
        "running_notes": [],
    }
    ws.mock_interview = {"version": 1, "active": active, "history": []}
    llm_ctx = MagicMock(user_api_key="key", provider="gemini", ready=True)
    save = AsyncMock()
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(True, 39))), \
         patch("api.mock_interview.is_mock_interview_thinking", AsyncMock(return_value=False)), \
         patch("api.mock_interview.require_user_llm_context", AsyncMock(return_value=(None, llm_ctx, None))), \
         patch("api.mock_interview.load_preferred_model", AsyncMock(return_value=None)), \
         patch("api.mock_interview.set_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.clear_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.broadcast_mock_interview_thinking", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_error", AsyncMock()), \
         patch("api.mock_interview._save_store", save), \
         patch(
             "api.mock_interview.MockInterviewAgent.next_turn",
             AsyncMock(side_effect=RuntimeError("llm down")),
         ), \
         patch("api.mock_interview.report_exception", AsyncMock()):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/turn",
            json={"transcript": "An answer that should not persist thinking.", "source": "typed"},
        )
    assert resp.status_code == 500
    save.assert_not_awaited()
    assert ws.mock_interview["active"]["status"] == "asking"


@pytest.mark.asyncio
async def test_finish_stale_thinking_recovers_when_lock_clear(authed_client):
    ws = _mock_ws()
    ws.mock_interview = {
        "version": 1,
        "active": {
            "run_id": "run-fin-stale",
            "status": "thinking",
            "style": "hr",
            "ends_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            "plan": [],
            "turns": [{"idx": 0, "role": "interviewer", "text": "Q?", "source": "tts"}],
            "running_notes": [],
        },
        "history": [],
    }
    llm_ctx = MagicMock(user_api_key="key", provider="gemini", ready=True)
    debrief = {
        "overall_score": 7,
        "scores": {"content": 7, "structure": 7, "clarity": 7, "role_fit": 7, "style_focus": 7},
        "strengths": ["a"],
        "improvements": ["b"],
        "weakest_answer_rewrite": "x",
        "summary": "ok",
    }
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(True, 9))), \
         patch("api.mock_interview.is_mock_interview_thinking", AsyncMock(return_value=False)), \
         patch("api.mock_interview.require_user_llm_context", AsyncMock(return_value=(None, llm_ctx, None))), \
         patch("api.mock_interview.load_preferred_model", AsyncMock(return_value=None)), \
         patch("api.mock_interview.set_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.clear_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.broadcast_mock_interview_thinking", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_complete", AsyncMock()), \
         patch("api.mock_interview._save_store", AsyncMock()), \
         patch("api.mock_interview.MockInterviewAgent.debrief", AsyncMock(return_value=debrief)):
        resp = await authed_client.post(f"{BASE}/{SESSION_ID}/finish")
    assert resp.status_code == 200
    assert resp.json()["status"] == "complete"


@pytest.mark.asyncio
async def test_turn_rate_limited(authed_client):
    ws = _mock_ws()
    ws.mock_interview = {
        "version": 1,
        "active": {
            "run_id": "r",
            "status": "asking",
            "style": "hr",
            "ends_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            "turns": [],
        },
        "history": [],
    }
    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(False, 0))):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/turn",
            json={"transcript": "Rate limited answer text here.", "source": "typed"},
        )
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_complete_archives_history_and_caps(authed_client):
    from agents.mock_interview import HISTORY_CAP

    ws = _mock_ws()
    old_history = [
        {"run_id": f"old-{i}", "status": "complete", "debrief": {"overall_score": i}}
        for i in range(HISTORY_CAP)
    ]
    ends = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    ws.mock_interview = {
        "version": 1,
        "active": {
            "run_id": "run-new",
            "status": "asking",
            "style": "hr",
            "ends_at": ends,
            "plan": [],
            "turns": [{"idx": 0, "role": "interviewer", "text": "Q?", "source": "tts"}],
            "running_notes": [],
        },
        "history": old_history,
    }
    llm_ctx = MagicMock(user_api_key="key", provider="gemini", ready=True)
    nxt = {
        "speak": "Thanks.",
        "act": "wrap_up",
        "scores": {"content": 7, "structure": 7, "clarity": 7},
        "running_notes": [],
    }
    debrief = {
        "overall_score": 7,
        "scores": {"content": 7, "structure": 7, "clarity": 7, "role_fit": 7, "style_focus": 7},
        "strengths": ["a"],
        "improvements": ["b"],
        "weakest_answer_rewrite": "x",
        "summary": "ok",
    }
    saved: dict = {}

    async def _save(_db, _ws, store):
        saved["store"] = {
            "active": store.get("active"),
            "history": list(store.get("history") or []),
        }

    with patch("api.mock_interview._load_owned_session", AsyncMock(return_value=ws)), \
         patch("api.mock_interview.check_rate_limit", AsyncMock(return_value=(True, 39))), \
         patch("api.mock_interview.is_mock_interview_thinking", AsyncMock(return_value=False)), \
         patch("api.mock_interview.require_user_llm_context", AsyncMock(return_value=(None, llm_ctx, None))), \
         patch("api.mock_interview.load_preferred_model", AsyncMock(return_value=None)), \
         patch("api.mock_interview.set_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.clear_mock_interview_thinking", AsyncMock(return_value=True)), \
         patch("api.mock_interview.broadcast_mock_interview_thinking", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_utterance", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_turn_scored", AsyncMock()), \
         patch("api.mock_interview.broadcast_mock_interview_complete", AsyncMock()), \
         patch("api.mock_interview._save_store", AsyncMock(side_effect=_save)), \
         patch("api.mock_interview.MockInterviewAgent.next_turn", AsyncMock(return_value=nxt)), \
         patch("api.mock_interview.MockInterviewAgent.debrief", AsyncMock(return_value=debrief)):
        resp = await authed_client.post(
            f"{BASE}/{SESSION_ID}/turn",
            json={"transcript": "Final answer that wraps the session up fully.", "source": "typed"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "complete"
    assert saved["store"]["active"] is None
    assert len(saved["store"]["history"]) == HISTORY_CAP
    assert saved["store"]["history"][0]["run_id"] == "run-new"
    assert saved["store"]["history"][0]["status"] == "complete"

