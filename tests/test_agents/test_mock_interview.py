"""Unit tests for MockInterviewAgent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.mock_interview import (
    STYLE_PACKS,
    MockInterviewAgent,
    _extract_prep_questions,
    _safe_score,
)


@pytest.fixture
def agent() -> MockInterviewAgent:
    return MockInterviewAgent()


@pytest.mark.asyncio
async def test_open_session_returns_speak(agent: MockInterviewAgent) -> None:
    mock_client = MagicMock()
    mock_client.generate = AsyncMock(
        return_value={
            "response": '{"speak":"Tell me about yourself.","act":"next_question","plan":[{"id":"q1","category":"behavioral","goal":"intro"}],"running_notes":[]}',
            "done": True,
        }
    )
    with patch("agents.mock_interview.get_gemini_client", AsyncMock(return_value=mock_client)):
        result = await agent.open_session(
            style="hr",
            duration_minutes=15,
            job_analysis={"job_title": "Engineer", "company_name": "Acme"},
            user_api_key="test-key",
            llm_provider="gemini",
        )
    assert "Tell me about yourself" in result["speak"]
    assert result["act"] == "next_question"
    assert isinstance(result["plan"], list)


@pytest.mark.asyncio
@pytest.mark.parametrize("style", ["hr", "pro", "manager"])
async def test_open_session_uses_style_pack(agent: MockInterviewAgent, style: str) -> None:
    mock_client = MagicMock()
    mock_client.generate = AsyncMock(
        return_value={
            "response": '{"speak":"Q?","act":"next_question","plan":[],"running_notes":[]}',
            "done": True,
        }
    )
    with patch("agents.mock_interview.get_gemini_client", AsyncMock(return_value=mock_client)):
        await agent.open_session(
            style=style,
            duration_minutes=10,
            job_analysis={"job_title": "PM"},
            user_api_key="k",
            llm_provider="openai",
        )
    call_kwargs = mock_client.generate.await_args.kwargs
    prompt_text = call_kwargs.get("prompt", "")
    assert style in prompt_text
    assert STYLE_PACKS[style][:40] in prompt_text


@pytest.mark.asyncio
async def test_next_turn_forces_wrap_up_when_time_low(agent: MockInterviewAgent) -> None:
    mock_client = MagicMock()
    mock_client.generate = AsyncMock(
        return_value={
            "response": '{"speak":"Thanks.","act":"next_question","scores":{"content":7,"structure":7,"clarity":7},"running_notes":[]}',
            "done": True,
        }
    )
    with patch("agents.mock_interview.get_gemini_client", AsyncMock(return_value=mock_client)):
        result = await agent.next_turn(
            style="pro",
            seconds_remaining=20,
            transcript="I led a project that shipped on time.",
            turns=[],
            plan=[],
            running_notes=[],
            job_analysis={"job_title": "Engineer"},
            user_api_key="k",
        )
    assert result["act"] == "wrap_up"


@pytest.mark.asyncio
async def test_next_turn_time_up_without_llm(agent: MockInterviewAgent) -> None:
    result = await agent.next_turn(
        style="manager",
        seconds_remaining=0,
        transcript="Answer",
        turns=[],
        plan=[],
        running_notes=[],
    )
    assert result["act"] == "wrap_up"
    assert "time" in result["speak"].lower() or "Thanks" in result["speak"]


@pytest.mark.asyncio
async def test_next_turn_follow_up(agent: MockInterviewAgent) -> None:
    mock_client = MagicMock()
    mock_client.generate = AsyncMock(
        return_value={
            "response": '{"speak":"Can you quantify that?","act":"follow_up","scores":{"content":8,"structure":7,"clarity":8},"tip":"","covered_plan_ids":[],"running_notes":["needs metrics"]}',
            "done": True,
        }
    )
    with patch("agents.mock_interview.get_gemini_client", AsyncMock(return_value=mock_client)):
        result = await agent.next_turn(
            style="manager",
            seconds_remaining=600,
            transcript="I improved the process.",
            turns=[],
            plan=[{"id": "q1", "category": "behavioral", "goal": "impact"}],
            running_notes=[],
            user_api_key="k",
        )
    assert result["act"] == "follow_up"
    assert result["scores"]["content"] == 8
    assert "quantify" in result["speak"].lower()


@pytest.mark.asyncio
async def test_next_turn_weak_score_gets_tip(agent: MockInterviewAgent) -> None:
    mock_client = MagicMock()
    mock_client.generate = AsyncMock(
        return_value={
            "response": '{"speak":"Tell me more.","act":"follow_up","scores":{"content":4,"structure":4,"clarity":5},"tip":"Add a metric.","covered_plan_ids":["q1"],"running_notes":[]}',
            "done": True,
        }
    )
    with patch("agents.mock_interview.get_gemini_client", AsyncMock(return_value=mock_client)):
        result = await agent.next_turn(
            style="hr",
            seconds_remaining=500,
            transcript="I did some stuff at work.",
            turns=[],
            plan=[{"id": "q1", "category": "behavioral", "goal": "example"}],
            running_notes=[],
            user_api_key="k",
        )
    assert "metric" in result["tip"].lower()
    assert result["covered_plan_ids"] == ["q1"]


@pytest.mark.asyncio
async def test_next_turn_two_minute_coaching_in_prompt(agent: MockInterviewAgent) -> None:
    mock_client = MagicMock()
    mock_client.generate = AsyncMock(
        return_value={
            "response": '{"speak":"Last full question — give one brief example.","act":"next_question","scores":{"content":7,"structure":7,"clarity":7},"tip":"","covered_plan_ids":[],"running_notes":[]}',
            "done": True,
        }
    )
    with patch("agents.mock_interview.get_gemini_client", AsyncMock(return_value=mock_client)):
        await agent.next_turn(
            style="pro",
            seconds_remaining=90,
            transcript="I shipped a feature with my team last quarter.",
            turns=[],
            plan=[],
            running_notes=[],
            user_api_key="k",
        )
    prompt = mock_client.generate.await_args.kwargs.get("prompt", "")
    assert "last full question" in prompt.lower() or "Last full question" in prompt or "61 and 120" in prompt or "last full" in prompt.lower()


@pytest.mark.asyncio
async def test_next_turn_tolerates_junk_scores(agent: MockInterviewAgent) -> None:
    mock_client = MagicMock()
    mock_client.generate = AsyncMock(
        return_value={
            "response": '{"speak":"Next?","act":"next_question","scores":{"content":"high","structure":99,"clarity":null},"running_notes":[]}',
            "done": True,
        }
    )
    with patch("agents.mock_interview.get_gemini_client", AsyncMock(return_value=mock_client)):
        result = await agent.next_turn(
            style="hr",
            seconds_remaining=400,
            transcript="I communicate well with stakeholders.",
            turns=[],
            plan=[],
            running_notes=[],
            user_api_key="k",
        )
    assert result["scores"]["content"] == 5
    assert result["scores"]["structure"] == 10
    assert result["scores"]["clarity"] == 5


@pytest.mark.asyncio
async def test_debrief_schema(agent: MockInterviewAgent) -> None:
    mock_client = MagicMock()
    mock_client.generate = AsyncMock(
        return_value={
            "response": (
                '{"overall_score":8,"scores":{"content":8,"structure":7,"clarity":8,"role_fit":7,"style_focus":8},'
                '"strengths":["a","b","c"],"improvements":["d","e","f"],'
                '"weakest_answer_rewrite":"Better STAR answer","summary":"Solid practice."}'
            ),
            "done": True,
        }
    )
    with patch("agents.mock_interview.get_gemini_client", AsyncMock(return_value=mock_client)):
        result = await agent.debrief(
            style="hr",
            turns=[{"role": "candidate", "text": "I handled conflict well."}],
            job_analysis={"job_title": "Analyst"},
            user_api_key="k",
        )
    assert result["overall_score"] == 8
    assert len(result["strengths"]) == 3
    assert "Better STAR" in result["weakest_answer_rewrite"]


@pytest.mark.asyncio
async def test_open_session_parse_error_fallback(agent: MockInterviewAgent) -> None:
    mock_client = MagicMock()
    mock_client.generate = AsyncMock(return_value={"response": "not-json", "done": True})
    with patch("agents.mock_interview.get_gemini_client", AsyncMock(return_value=mock_client)):
        result = await agent.open_session(
            style="hr",
            duration_minutes=15,
            job_analysis={"job_title": "Engineer"},
            user_api_key="k",
        )
    assert result["act"] == "wrap_up"
    assert result["speak"]
    assert result.get("error") == "parse_error"


@pytest.mark.asyncio
async def test_open_session_streams_speak_deltas(agent: MockInterviewAgent) -> None:
    raw = (
        '{"speak":"Tell me about yourself.","act":"next_question",'
        '"plan":[{"id":"q1","category":"behavioral","goal":"intro"}],"running_notes":[]}'
    )

    async def _stream(**_kwargs):
        for i in range(0, len(raw), 12):
            yield raw[i : i + 12]

    mock_client = MagicMock()
    mock_client.generate_stream = _stream
    mock_client.generate = AsyncMock()
    deltas: list[str] = []

    async def on_delta(d: str) -> None:
        deltas.append(d)

    with patch("agents.mock_interview.get_gemini_client", AsyncMock(return_value=mock_client)):
        result = await agent.open_session(
            style="hr",
            duration_minutes=15,
            job_analysis={"job_title": "Engineer"},
            user_api_key="k",
            llm_provider="gemini",
            on_speak_delta=on_delta,
        )
    assert "Tell me about yourself" in result["speak"]
    assert "".join(deltas) == "Tell me about yourself."
    mock_client.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_next_turn_parse_error_returns_error_not_wrap(agent: MockInterviewAgent) -> None:
    mock_client = MagicMock()
    mock_client.generate = AsyncMock(return_value={"response": "not-json", "done": True})
    with patch("agents.mock_interview.get_gemini_client", AsyncMock(return_value=mock_client)):
        result = await agent.next_turn(
            style="hr",
            seconds_remaining=500,
            transcript="I led a project.",
            turns=[],
            plan=[],
            running_notes=[],
            user_api_key="k",
        )
    assert result.get("error") == "parse_error"
    assert result["act"] != "wrap_up"


@pytest.mark.asyncio
async def test_next_turn_stream_fallback_on_failure(agent: MockInterviewAgent) -> None:
    async def _bad_stream(**_kwargs):
        raise RuntimeError("stream boom")
        yield  # pragma: no cover

    mock_client = MagicMock()
    mock_client.generate_stream = _bad_stream
    mock_client.generate = AsyncMock(
        return_value={
            "response": (
                '{"speak":"Can you elaborate?","act":"follow_up",'
                '"scores":{"content":6,"structure":6,"clarity":6},"running_notes":[]}'
            ),
            "done": True,
        }
    )
    with patch("agents.mock_interview.get_gemini_client", AsyncMock(return_value=mock_client)):
        result = await agent.next_turn(
            style="hr",
            seconds_remaining=500,
            transcript="I led a team project.",
            turns=[],
            plan=[],
            running_notes=[],
            user_api_key="k",
            on_speak_delta=AsyncMock(),
        )
    assert "elaborate" in result["speak"].lower()
    mock_client.generate.assert_awaited()


def test_extract_prep_questions_hr_prefers_behavioral() -> None:
    prep = {
        "predicted_questions": {
            "behavioral": [{"question": "Tell me about a conflict"}],
            "technical": [{"question": "Explain TCP"}],
            "company_specific": [{"question": "Why us?"}],
        }
    }
    text = _extract_prep_questions(prep, "hr")
    assert "Tell me about a conflict" in text
    assert "Why us?" in text
    assert "Explain TCP" not in text


def test_extract_prep_questions_pro_prefers_technical() -> None:
    prep = {
        "predicted_questions": {
            "behavioral": [{"question": "Conflict"}],
            "technical": [{"question": "Design a cache"}],
            "role_specific": [{"question": "How do you ship?"}],
        }
    }
    text = _extract_prep_questions(prep, "pro")
    assert "Design a cache" in text
    assert "How do you ship?" in text
    assert "Conflict" not in text


def test_extract_prep_questions_manager_prefers_role_and_behavioral() -> None:
    prep = {
        "predicted_questions": {
            "behavioral": [{"question": "Ownership story"}],
            "technical": [{"question": "Big-O"}],
            "role_specific": [{"question": "How do you prioritize?"}],
        }
    }
    text = _extract_prep_questions(prep, "manager")
    assert "Ownership story" in text
    assert "How do you prioritize?" in text
    assert "Big-O" not in text


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, 5),
        ("", 5),
        ("seven", 5),
        (0, 1),
        (15, 10),
        (7.9, 7),
        ("8", 8),
    ],
)
def test_safe_score(raw, expected) -> None:
    assert _safe_score(raw) == expected
