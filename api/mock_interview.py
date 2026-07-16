"""
API endpoints for conversational mock interview practice.
HR / Pro / Manager styles; duration-based sessions (10/15/20 minutes).
"""

from __future__ import annotations

import html
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from agents.mock_interview import HISTORY_CAP, VALID_STYLES, MockInterviewAgent
from api.websocket import (
    broadcast_mock_interview_complete,
    broadcast_mock_interview_error,
    broadcast_mock_interview_speak_delta,
    broadcast_mock_interview_started,
    broadcast_mock_interview_thinking,
    broadcast_mock_interview_turn_scored,
    broadcast_mock_interview_utterance,
)
from models.database import WorkflowSession
from utils.auth import get_current_user
from utils.cache import (
    check_rate_limit,
    clear_mock_interview_thinking,
    is_mock_interview_thinking,
    set_mock_interview_thinking,
)
from utils.database import get_database
from utils.error_reporting import report_exception
from utils.error_responses import (
    APIError,
    ErrorCode,
    internal_error,
    not_found_error,
    rate_limit_error,
    validation_error,
)
from utils.llm_client import user_facing_message_from_llm_exception
from utils.llm_context import require_user_llm_context
from utils.llm_preferences import load_preferred_model
from utils.logging_config import sanitize_log_value
from utils.security import sanitize_llm_output, sanitize_text

logger = logging.getLogger(__name__)
router = APIRouter()

RATE_LIMIT_START = 10
RATE_LIMIT_TURN = 40
RATE_LIMIT_FINISH = 10
RATE_LIMIT_WINDOW = 3600
ALLOWED_DURATIONS = frozenset({10, 15, 20})
DEFAULT_DURATION = 15
MAX_TRANSCRIPT_CHARS = 4000
MIN_TRANSCRIPT_CHARS = 5


# =============================================================================
# PYDANTIC MODELS
# =============================================================================


def _validate_style(v: str) -> str:
    style = (v or "").lower().strip()
    if style not in VALID_STYLES:
        raise ValueError("style must be one of: hr, pro, manager")
    return style


def _validate_duration(v: int) -> int:
    if v not in ALLOWED_DURATIONS:
        raise ValueError("duration_minutes must be 10, 15, or 20")
    return v


def _validate_transcript(v: str) -> str:
    text = sanitize_text(v or "").strip()
    if len(text) < MIN_TRANSCRIPT_CHARS:
        raise ValueError(f"transcript must be at least {MIN_TRANSCRIPT_CHARS} characters")
    if len(text) > MAX_TRANSCRIPT_CHARS:
        raise ValueError(f"transcript must be at most {MAX_TRANSCRIPT_CHARS} characters")
    return text


class MockInterviewStartRequest(BaseModel):
    """Start a mock interview run."""

    style: str = Field(..., description="hr | pro | manager")
    duration_minutes: int = Field(DEFAULT_DURATION, description="10, 15, or 20")
    star_coach: bool = Field(
        True,
        description="Ignored — STAR coaching is always on for Practice Interview",
    )

    validate_style = field_validator("style")(_validate_style)
    validate_duration = field_validator("duration_minutes")(_validate_duration)


class MockInterviewTurnRequest(BaseModel):
    """Submit a candidate answer transcript."""

    transcript: str = Field(..., max_length=MAX_TRANSCRIPT_CHARS)
    source: Literal["typed", "stt"] = Field("typed")

    validate_transcript = field_validator("transcript")(_validate_transcript)


class MockInterviewResponse(BaseModel):
    """Active run + history summary."""

    session_id: str
    active: Optional[Dict[str, Any]] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)
    seconds_remaining: Optional[int] = None
    is_thinking: bool = False


class MockInterviewStatusResponse(BaseModel):
    """Polling status."""

    session_id: str
    status: Optional[str] = None
    is_thinking: bool = False
    seconds_remaining: Optional[int] = None
    ends_at: Optional[str] = None
    run_id: Optional[str] = None


class MockInterviewActionResponse(BaseModel):
    """Start / turn / finish action response."""

    session_id: str
    run_id: str
    status: str
    speak: Optional[str] = None
    act: Optional[str] = None
    seconds_remaining: Optional[int] = None
    ends_at: Optional[str] = None
    scores: Optional[Dict[str, Any]] = None
    tip: Optional[str] = None
    plan: Optional[List[Dict[str, Any]]] = None
    covered_plan_ids: Optional[List[str]] = None
    star_coach: bool = True
    debrief: Optional[Dict[str, Any]] = None
    message: str = ""


# =============================================================================
# HELPERS
# =============================================================================


def _get_user_uuid(current_user: Dict[str, Any]) -> uuid.UUID:
    user_id = current_user.get("id") or current_user.get("_id")
    if isinstance(user_id, str):
        return uuid.UUID(user_id)
    return user_id


def _seconds_remaining(ends_at_iso: Optional[str]) -> int:
    if not ends_at_iso:
        return 0
    try:
        ends = datetime.fromisoformat(ends_at_iso.replace("Z", "+00:00"))
        if ends.tzinfo is None:
            ends = ends.replace(tzinfo=timezone.utc)
        return max(0, int((ends - datetime.now(timezone.utc)).total_seconds()))
    except (TypeError, ValueError):
        return 0


def _empty_store() -> Dict[str, Any]:
    return {"version": 1, "active": None, "history": []}


def _plain_mock_strings(obj: Any) -> Any:
    """Undo HTML escaping from sanitize_llm_output for plain-text dialogue UI.

    Mock interview turns/tips are shown via textContent / escapeHtml, so storing
    ``&#x27;`` makes apostrophes appear literally. Keep script stripping from
    sanitize_llm_output, then unescape so users see normal punctuation.
    """
    if isinstance(obj, dict):
        return {k: _plain_mock_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_plain_mock_strings(item) for item in obj]
    if isinstance(obj, str):
        return html.unescape(obj)
    return obj


def _get_store(ws: WorkflowSession) -> Dict[str, Any]:
    data = ws.mock_interview
    if not isinstance(data, dict):
        return _empty_store()
    out = _plain_mock_strings(dict(data))
    if not isinstance(out, dict):
        return _empty_store()
    if "history" not in out or not isinstance(out.get("history"), list):
        out["history"] = []
    return out


async def _load_owned_session(
    db: AsyncSession, session_id: str, user_id: uuid.UUID
) -> WorkflowSession:
    result = await db.execute(
        select(WorkflowSession).where(
            and_(
                WorkflowSession.session_id == session_id,
                WorkflowSession.user_id == user_id,
            )
        )
    )
    ws = result.scalar_one_or_none()
    if not ws:
        raise not_found_error("Workflow session")
    return ws


def _archive_active(store: Dict[str, Any]) -> None:
    active = store.get("active")
    if isinstance(active, dict) and active.get("status") in ("complete", "aborted", "failed"):
        history = list(store.get("history") or [])
        history.insert(0, active)
        store["history"] = history[:HISTORY_CAP]
        store["active"] = None


async def _save_store(db: AsyncSession, ws: WorkflowSession, store: Dict[str, Any]) -> None:
    # Strip risky markup, then unescape so dialogue keeps normal apostrophes.
    ws.mock_interview = _plain_mock_strings(sanitize_llm_output(store))
    flag_modified(ws, "mock_interview")
    await db.commit()
    await db.refresh(ws)


async def _run_debrief(
    agent: MockInterviewAgent,
    active: Dict[str, Any],
    job_analysis: Optional[Dict[str, Any]],
    *,
    user_api_key: Optional[str],
    model: Optional[str],
    llm_provider: Optional[str],
) -> Dict[str, Any]:
    return await agent.debrief(
        style=active.get("style") or "hr",
        turns=list(active.get("turns") or []),
        job_analysis=job_analysis,
        user_api_key=user_api_key,
        model=model,
        llm_provider=llm_provider,
    )


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get("/{session_id}", response_model=MockInterviewResponse)
async def get_mock_interview(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> MockInterviewResponse:
    """Return active mock interview run and recent history."""
    user_id = _get_user_uuid(current_user)
    ws = await _load_owned_session(db, session_id, user_id)
    store = _get_store(ws)
    active = store.get("active")
    ends_at = active.get("ends_at") if isinstance(active, dict) else None
    thinking = await is_mock_interview_thinking(session_id)
    return MockInterviewResponse(
        session_id=session_id,
        active=active if isinstance(active, dict) else None,
        history=list(store.get("history") or []),
        seconds_remaining=_seconds_remaining(ends_at) if ends_at else None,
        is_thinking=thinking,
    )


@router.get("/{session_id}/status", response_model=MockInterviewStatusResponse)
async def get_mock_interview_status(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> MockInterviewStatusResponse:
    """Polling status for an active mock interview."""
    user_id = _get_user_uuid(current_user)
    ws = await _load_owned_session(db, session_id, user_id)
    store = _get_store(ws)
    active = store.get("active") if isinstance(store.get("active"), dict) else None
    ends_at = active.get("ends_at") if active else None
    return MockInterviewStatusResponse(
        session_id=session_id,
        status=active.get("status") if active else None,
        is_thinking=await is_mock_interview_thinking(session_id),
        seconds_remaining=_seconds_remaining(ends_at) if ends_at else None,
        ends_at=ends_at,
        run_id=active.get("run_id") if active else None,
    )


@router.post("/{session_id}/start", response_model=MockInterviewActionResponse)
async def start_mock_interview(
    session_id: str,
    body: MockInterviewStartRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> MockInterviewActionResponse:
    """Start a timed mock interview (HR / Pro / Manager)."""
    user_id = _get_user_uuid(current_user)
    allowed, _remaining = await check_rate_limit(
        identifier=f"{user_id}:mock_interview_start",
        limit=RATE_LIMIT_START,
        window_seconds=RATE_LIMIT_WINDOW,
    )
    if not allowed:
        raise rate_limit_error(retry_after=RATE_LIMIT_WINDOW)

    ws = await _load_owned_session(db, session_id, user_id)
    if not ws.job_analysis:
        raise validation_error("Job analysis is required before starting a practice interview")

    store = _get_store(ws)
    active = store.get("active")
    if isinstance(active, dict) and active.get("status") in (
        "briefing",
        "asking",
        "listening",
        "thinking",
    ):
        raise APIError(
            ErrorCode.RESOURCE_CONFLICT,
            "A practice interview is already in progress for this application",
            status_code=409,
        )

    _u, llm_ctx, _p = await require_user_llm_context(db, user_id)
    user_api_key = llm_ctx.user_api_key
    llm_provider = llm_ctx.provider
    preferred_model = await load_preferred_model(
        db, user_id, user_api_key, has_credentials=True
    )

    claimed = await set_mock_interview_thinking(session_id)
    if not claimed:
        raise APIError(
            ErrorCode.RESOURCE_CONFLICT,
            "Practice interview is busy — try again in a moment",
            status_code=409,
        )

    ws_user_id = str(user_id)
    run_id = str(uuid.uuid4())
    try:
        await broadcast_mock_interview_started(ws_user_id, session_id)
        await broadcast_mock_interview_thinking(ws_user_id, session_id)

        async def _on_speak_delta(delta: str) -> None:
            if delta:
                await broadcast_mock_interview_speak_delta(
                    ws_user_id, session_id, delta=delta, run_id=run_id
                )

        agent = MockInterviewAgent()
        opened = await agent.open_session(
            style=body.style,
            duration_minutes=body.duration_minutes,
            job_analysis=ws.job_analysis or {},
            company_research=ws.company_research or {},
            profile_matching=ws.profile_matching or {},
            user_profile=ws.user_data or {},
            interview_prep=ws.interview_prep or {},
            star_coach=True,
            user_api_key=user_api_key,
            model=preferred_model,
            llm_provider=llm_provider,
            on_speak_delta=_on_speak_delta,
        )
        if opened.get("error") or str(opened.get("act") or "") == "wrap_up":
            msg = "Could not start the practice interview. Please try again."
            await broadcast_mock_interview_error(ws_user_id, session_id, msg)
            raise internal_error(msg)

        now = datetime.now(timezone.utc)
        ends = now + timedelta(minutes=body.duration_minutes)
        speak = str(opened.get("speak") or "")
        plan = opened.get("plan") or []
        new_active: Dict[str, Any] = {
            "run_id": run_id,
            "status": "asking",
            "style": body.style,
            "duration_minutes": body.duration_minutes,
            "star_coach": True,
            "language": "en",
            "started_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "ends_at": ends.isoformat(),
            "plan": plan,
            "covered_plan_ids": [],
            "last_tip": None,
            "turns": [
                {
                    "idx": 0,
                    "role": "interviewer",
                    "text": speak,
                    "source": "tts",
                    "at": now.isoformat(),
                }
            ],
            "running_notes": opened.get("running_notes") or [],
            "debrief": None,
            "error": None,
        }
        if isinstance(store.get("active"), dict):
            _archive_active(store)
        store["active"] = new_active
        await _save_store(db, ws, store)

        await broadcast_mock_interview_utterance(
            ws_user_id, session_id, speak=speak, turn_idx=0, run_id=run_id
        )

        return MockInterviewActionResponse(
            session_id=session_id,
            run_id=run_id,
            status="asking",
            speak=speak,
            act=str(opened.get("act") or "next_question"),
            seconds_remaining=_seconds_remaining(ends.isoformat()),
            ends_at=ends.isoformat(),
            plan=plan if isinstance(plan, list) else [],
            covered_plan_ids=[],
            star_coach=True,
            message="Practice interview started",
        )
    except APIError:
        raise
    except Exception as e:
        logger.error(
            "Mock interview start failed for %s: %s",
            sanitize_log_value(session_id),
            sanitize_log_value(str(e)),
            exc_info=True,
        )
        await report_exception(e, user_id=ws_user_id)
        msg = user_facing_message_from_llm_exception(e)
        await broadcast_mock_interview_error(ws_user_id, session_id, msg)
        raise internal_error(msg)
    finally:
        await clear_mock_interview_thinking(session_id)


@router.post("/{session_id}/turn", response_model=MockInterviewActionResponse)
async def submit_mock_interview_turn(
    session_id: str,
    body: MockInterviewTurnRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> MockInterviewActionResponse:
    """Submit a candidate transcript and get the next interviewer act."""
    user_id = _get_user_uuid(current_user)
    allowed, _remaining = await check_rate_limit(
        identifier=f"{user_id}:mock_interview_turn",
        limit=RATE_LIMIT_TURN,
        window_seconds=RATE_LIMIT_WINDOW,
    )
    if not allowed:
        raise rate_limit_error(retry_after=RATE_LIMIT_WINDOW)

    ws = await _load_owned_session(db, session_id, user_id)
    store = _get_store(ws)
    active = store.get("active")
    if not isinstance(active, dict) or active.get("status") not in (
        "asking",
        "listening",
        "briefing",
        "thinking",
    ):
        raise validation_error("No active practice interview to answer")

    if await is_mock_interview_thinking(session_id):
        raise APIError(
            ErrorCode.RESOURCE_CONFLICT,
            "Still processing your previous answer",
            status_code=409,
        )

    _u, llm_ctx, _p = await require_user_llm_context(db, user_id)
    user_api_key = llm_ctx.user_api_key
    llm_provider = llm_ctx.provider
    preferred_model = await load_preferred_model(
        db, user_id, user_api_key, has_credentials=True
    )

    claimed = await set_mock_interview_thinking(session_id)
    if not claimed:
        raise APIError(
            ErrorCode.RESOURCE_CONFLICT,
            "Still processing your previous answer",
            status_code=409,
        )

    ws_user_id = str(user_id)
    run_id = str(active.get("run_id") or "")
    # Work on a shallow copy so a failed LLM call does not leave JSONB dirty as "thinking"
    working = dict(active)
    try:
        await broadcast_mock_interview_thinking(ws_user_id, session_id)
        now = datetime.now(timezone.utc)
        turns = list(working.get("turns") or [])
        turns.append(
            {
                "idx": len(turns),
                "role": "candidate",
                "text": body.transcript,
                "source": body.source,
                "at": now.isoformat(),
            }
        )
        working["turns"] = turns
        working["status"] = "thinking"
        working["updated_at"] = now.isoformat()

        seconds_left = _seconds_remaining(working.get("ends_at"))
        agent = MockInterviewAgent()

        async def _on_speak_delta(delta: str) -> None:
            if delta:
                await broadcast_mock_interview_speak_delta(
                    ws_user_id, session_id, delta=delta, run_id=run_id
                )

        nxt = await agent.next_turn(
            style=working.get("style") or "hr",
            seconds_remaining=seconds_left,
            transcript=body.transcript,
            turns=turns,
            plan=list(working.get("plan") or []),
            running_notes=list(working.get("running_notes") or []),
            covered_plan_ids=list(working.get("covered_plan_ids") or []),
            star_coach=True,
            job_analysis=ws.job_analysis or {},
            user_api_key=user_api_key,
            model=preferred_model,
            llm_provider=llm_provider,
            on_speak_delta=_on_speak_delta,
        )

        if nxt.get("error"):
            msg = "Could not process that answer. Please try again."
            await broadcast_mock_interview_error(ws_user_id, session_id, msg)
            raise internal_error(msg)

        scores = nxt.get("scores") if isinstance(nxt.get("scores"), dict) else None
        tip = str(nxt.get("tip") or "").strip() or None
        covered = nxt.get("covered_plan_ids") if isinstance(nxt.get("covered_plan_ids"), list) else list(
            working.get("covered_plan_ids") or []
        )
        working["covered_plan_ids"] = covered
        working["last_tip"] = tip
        if scores and turns:
            turns[-1]["scores"] = scores
            if tip:
                turns[-1]["tip"] = tip
            await broadcast_mock_interview_turn_scored(
                ws_user_id,
                session_id,
                turn_idx=turns[-1]["idx"],
                scores=scores,
                run_id=run_id,
                tip=tip,
            )

        speak = str(nxt.get("speak") or "")
        act = str(nxt.get("act") or "next_question")
        working["running_notes"] = nxt.get("running_notes") or working.get("running_notes") or []

        debrief: Optional[Dict[str, Any]] = None
        if act == "wrap_up" or seconds_left <= 0:
            turns.append(
                {
                    "idx": len(turns),
                    "role": "interviewer",
                    "text": speak,
                    "source": "tts",
                    "at": datetime.now(timezone.utc).isoformat(),
                }
            )
            working["turns"] = turns
            debrief = await _run_debrief(
                agent,
                working,
                ws.job_analysis or {},
                user_api_key=user_api_key,
                model=preferred_model,
                llm_provider=llm_provider,
            )
            working["debrief"] = debrief
            working["status"] = "complete"
            working["updated_at"] = datetime.now(timezone.utc).isoformat()
            store["active"] = working
            _archive_active(store)
            await _save_store(db, ws, store)
            await broadcast_mock_interview_utterance(
                ws_user_id, session_id, speak=speak, turn_idx=turns[-1]["idx"], run_id=run_id
            )
            await broadcast_mock_interview_complete(
                ws_user_id, session_id, debrief=debrief or {}, run_id=run_id
            )
            return MockInterviewActionResponse(
                session_id=session_id,
                run_id=run_id,
                status="complete",
                speak=speak,
                act="wrap_up",
                seconds_remaining=0,
                ends_at=working.get("ends_at"),
                scores=scores,
                tip=tip,
                plan=list(working.get("plan") or []),
                covered_plan_ids=covered,
                star_coach=True,
                debrief=debrief,
                message="Practice interview complete",
            )

        turns.append(
            {
                "idx": len(turns),
                "role": "interviewer",
                "text": speak,
                "source": "tts",
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        working["turns"] = turns
        working["status"] = "asking"
        working["updated_at"] = datetime.now(timezone.utc).isoformat()
        store["active"] = working
        await _save_store(db, ws, store)
        await broadcast_mock_interview_utterance(
            ws_user_id, session_id, speak=speak, turn_idx=turns[-1]["idx"], run_id=run_id
        )

        return MockInterviewActionResponse(
            session_id=session_id,
            run_id=run_id,
            status="asking",
            speak=speak,
            act=act,
            seconds_remaining=_seconds_remaining(working.get("ends_at")),
            ends_at=working.get("ends_at"),
            scores=scores,
            tip=tip,
            plan=list(working.get("plan") or []),
            covered_plan_ids=covered,
            star_coach=True,
            message="Next question ready",
        )
    except APIError:
        raise
    except Exception as e:
        logger.error(
            "Mock interview turn failed for %s: %s",
            sanitize_log_value(session_id),
            sanitize_log_value(str(e)),
            exc_info=True,
        )
        await report_exception(e, user_id=ws_user_id)
        msg = user_facing_message_from_llm_exception(e)
        await broadcast_mock_interview_error(ws_user_id, session_id, msg)
        raise internal_error(msg)
    finally:
        await clear_mock_interview_thinking(session_id)


@router.post("/{session_id}/finish", response_model=MockInterviewActionResponse)
async def finish_mock_interview(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> MockInterviewActionResponse:
    """End early and generate a debrief."""
    user_id = _get_user_uuid(current_user)
    allowed, _remaining = await check_rate_limit(
        identifier=f"{user_id}:mock_interview_finish",
        limit=RATE_LIMIT_FINISH,
        window_seconds=RATE_LIMIT_WINDOW,
    )
    if not allowed:
        raise rate_limit_error(retry_after=RATE_LIMIT_WINDOW)

    ws = await _load_owned_session(db, session_id, user_id)
    store = _get_store(ws)
    active = store.get("active")
    if not isinstance(active, dict) or active.get("status") in (None, "complete", "aborted"):
        raise validation_error("No active practice interview to finish")

    if await is_mock_interview_thinking(session_id):
        raise APIError(
            ErrorCode.RESOURCE_CONFLICT,
            "Practice interview is busy — try again in a moment",
            status_code=409,
        )

    _u, llm_ctx, _p = await require_user_llm_context(db, user_id)
    user_api_key = llm_ctx.user_api_key
    llm_provider = llm_ctx.provider
    preferred_model = await load_preferred_model(
        db, user_id, user_api_key, has_credentials=True
    )

    claimed = await set_mock_interview_thinking(session_id)
    if not claimed:
        raise APIError(
            ErrorCode.RESOURCE_CONFLICT,
            "Practice interview is busy — try again in a moment",
            status_code=409,
        )

    ws_user_id = str(user_id)
    run_id = str(active.get("run_id") or "")
    working = dict(active)
    try:
        await broadcast_mock_interview_thinking(ws_user_id, session_id)
        agent = MockInterviewAgent()
        speak = "Thanks for practicing — here's your feedback."
        turns = list(working.get("turns") or [])
        turns.append(
            {
                "idx": len(turns),
                "role": "interviewer",
                "text": speak,
                "source": "tts",
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        working["turns"] = turns
        debrief = await _run_debrief(
            agent,
            working,
            ws.job_analysis or {},
            user_api_key=user_api_key,
            model=preferred_model,
            llm_provider=llm_provider,
        )
        working["debrief"] = debrief
        working["status"] = "complete"
        working["updated_at"] = datetime.now(timezone.utc).isoformat()
        store["active"] = working
        _archive_active(store)
        await _save_store(db, ws, store)
        await broadcast_mock_interview_complete(
            ws_user_id, session_id, debrief=debrief, run_id=run_id
        )
        return MockInterviewActionResponse(
            session_id=session_id,
            run_id=run_id,
            status="complete",
            speak=speak,
            act="wrap_up",
            seconds_remaining=0,
            ends_at=working.get("ends_at"),
            plan=list(working.get("plan") or []),
            covered_plan_ids=list(working.get("covered_plan_ids") or []),
            star_coach=True,
            debrief=debrief,
            message="Practice interview finished",
        )
    except APIError:
        raise
    except Exception as e:
        logger.error(
            "Mock interview finish failed for %s: %s",
            sanitize_log_value(session_id),
            sanitize_log_value(str(e)),
            exc_info=True,
        )
        await report_exception(e, user_id=ws_user_id)
        msg = user_facing_message_from_llm_exception(e)
        await broadcast_mock_interview_error(ws_user_id, session_id, msg)
        raise internal_error(msg)
    finally:
        await clear_mock_interview_thinking(session_id)


@router.post("/{session_id}/abort", response_model=MockInterviewActionResponse)
async def abort_mock_interview(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> MockInterviewActionResponse:
    """Abort the active run without a debrief."""
    user_id = _get_user_uuid(current_user)
    ws = await _load_owned_session(db, session_id, user_id)
    store = _get_store(ws)
    active = store.get("active")
    if not isinstance(active, dict) or active.get("status") in (None, "complete", "aborted"):
        raise validation_error("No active practice interview to abort")

    if await is_mock_interview_thinking(session_id):
        raise APIError(
            ErrorCode.RESOURCE_CONFLICT,
            "Practice interview is busy — wait for the current answer to finish, then abort",
            status_code=409,
        )

    run_id = str(active.get("run_id") or "")
    working = dict(active)
    working["status"] = "aborted"
    working["updated_at"] = datetime.now(timezone.utc).isoformat()
    store["active"] = working
    _archive_active(store)
    await _save_store(db, ws, store)
    return MockInterviewActionResponse(
        session_id=session_id,
        run_id=run_id,
        status="aborted",
        message="Practice interview aborted",
    )
