"""
Direct-handler coverage for remaining api/interview_prep.py gaps.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import select

from api.interview_prep import (
    _check_api_key_available,
    _generate_interview_prep_background,
    _get_user_api_key,
    delete_interview_prep,
    generate_interview_prep,
    get_interview_prep,
    get_interview_prep_status,
)
from models.database import User, WorkflowSession
from tests.test_api.conftest import _NullSessionLocal
from utils.error_responses import APIError


def _user_dict(uid: uuid.UUID, email: str) -> dict:
    return {
        "id": str(uid),
        "_id": str(uid),
        "email": email,
        "full_name": "Prep User",
        "auth_method": "local",
        "profile_completed": True,
    }


async def _seed_session(
    uid: uuid.UUID,
    *,
    interview_prep: dict | None = None,
    job_analysis: dict | None = None,
) -> str:
    sid = str(uuid.uuid4())
    async with _NullSessionLocal() as db:
        db.add(
            WorkflowSession(
                id=uuid.uuid4(),
                session_id=sid,
                user_id=uid,
                workflow_status="completed",
                job_analysis=job_analysis or {"job_title": "Engineer", "company_name": "Co"},
                interview_prep=interview_prep,
            )
        )
        await db.commit()
    return sid


@pytest.fixture
async def prep_user():
    uid = uuid.uuid4()
    email = f"prep_{uid.hex[:10]}@example.com"
    async with _NullSessionLocal() as db:
        db.add(
            User(
                id=uid,
                email=email,
                password_hash="$2b$12$placeholder",
                auth_method="local",
                full_name="Prep User",
            )
        )
        from models.database import UserWorkflowPreferences

        db.add(
            UserWorkflowPreferences(
                id=uuid.uuid4(),
                user_id=uid,
                preferred_provider="ollama",
            )
        )
        await db.commit()
    yield uid, email
    async with _NullSessionLocal() as db:
        from sqlalchemy import delete

        await db.execute(delete(WorkflowSession).where(WorkflowSession.user_id == uid))
        await db.execute(delete(User).where(User.id == uid))
        await db.commit()


class TestInterviewPrepDirectHandlers:
    @pytest.mark.asyncio
    async def test_get_user_api_key_decrypts_from_db(self, prep_user) -> None:
        from utils.llm.availability import UserLLMContext

        uid, _ = prep_user
        ctx = UserLLMContext(
            provider="gemini",
            user_api_key="byok-key",
            preferred_model=None,
            ready=True,
        )
        async with _NullSessionLocal() as db:
            with patch(
                "utils.llm_context.require_user_llm_context",
                AsyncMock(return_value=(MagicMock(), ctx, None)),
            ):
                key = await _get_user_api_key(db, uid)
        assert key == "byok-key"

    @pytest.mark.asyncio
    async def test_check_api_key_available_user_key(self, prep_user) -> None:
        from utils.llm.availability import UserLLMContext

        uid, _ = prep_user
        ctx = UserLLMContext(
            provider="gemini",
            user_api_key="user-key",
            preferred_model=None,
            ready=True,
        )
        async with _NullSessionLocal() as db:
            with patch(
                "utils.llm_context.require_user_llm_context",
                AsyncMock(return_value=(MagicMock(), ctx, None)),
            ):
                assert await _check_api_key_available(db, uid) is True

    @pytest.mark.asyncio
    async def test_get_interview_prep_db_hit_caches(self, prep_user) -> None:
        uid, email = prep_user
        prep = {
            "predicted_questions": {"behavioral": ["Q1"]},
            "generated_at": "2026-01-01T00:00:00+00:00",
        }
        sid = await _seed_session(uid, interview_prep=prep)
        async with _NullSessionLocal() as db:
            with (
                patch("api.interview_prep.get_cached_interview_prep", AsyncMock(return_value=None)),
                patch("api.interview_prep.cache_interview_prep", AsyncMock()) as cache_mock,
            ):
                resp = await get_interview_prep(
                    session_id=sid,
                    current_user=_user_dict(uid, email),
                    db=db,
                )
        assert resp.has_interview_prep is True
        assert resp.interview_prep["predicted_questions"]
        cache_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_interview_prep_db_no_prep(self, prep_user) -> None:
        uid, email = prep_user
        sid = await _seed_session(uid, interview_prep=None)
        async with _NullSessionLocal() as db:
            with patch("api.interview_prep.get_cached_interview_prep", AsyncMock(return_value=None)):
                resp = await get_interview_prep(
                    session_id=sid,
                    current_user=_user_dict(uid, email),
                    db=db,
                )
        assert resp.has_interview_prep is False
        assert resp.interview_prep is None

    @pytest.mark.asyncio
    async def test_get_status_session_without_prep(self, prep_user) -> None:
        uid, email = prep_user
        sid = await _seed_session(uid, interview_prep=None)
        async with _NullSessionLocal() as db:
            with patch("api.interview_prep.is_interview_prep_generating", AsyncMock(return_value=False)):
                resp = await get_interview_prep_status(
                    session_id=sid,
                    current_user=_user_dict(uid, email),
                    db=db,
                )
        assert resp.has_interview_prep is False
        assert resp.is_generating is False
        assert resp.generated_at is None

    @pytest.mark.asyncio
    async def test_generate_starts_background_direct(self, prep_user) -> None:
        uid, email = prep_user
        sid = await _seed_session(uid)
        bg = BackgroundTasks()
        async with _NullSessionLocal() as db:
            with (
                patch("api.interview_prep.check_rate_limit", AsyncMock(return_value=(True, 4))),
                patch("api.interview_prep._check_api_key_available", AsyncMock(return_value=True)),
                patch("api.interview_prep._get_user_api_key", AsyncMock(return_value="key")),
                patch("api.interview_prep.set_interview_prep_generating", AsyncMock(return_value=True)),
                patch("api.interview_prep._generate_interview_prep_background", AsyncMock()),
            ):
                resp = await generate_interview_prep(
                    session_id=sid,
                    background_tasks=bg,
                    regenerate=False,
                    current_user=_user_dict(uid, email),
                    db=db,
                )
        assert resp.status == "generating"
        assert len(bg.tasks) == 1

    @pytest.mark.asyncio
    async def test_delete_clears_db_and_cache_direct(self, prep_user) -> None:
        uid, email = prep_user
        sid = await _seed_session(uid, interview_prep={"predicted_questions": {}})
        async with _NullSessionLocal() as db:
            with (
                patch("api.interview_prep.is_interview_prep_generating", AsyncMock(return_value=False)),
                patch("api.interview_prep.invalidate_interview_prep", AsyncMock()) as inv,
            ):
                await delete_interview_prep(
                    session_id=sid,
                    current_user=_user_dict(uid, email),
                    db=db,
                )
        inv.assert_awaited_once_with(sid)
        async with _NullSessionLocal() as db:
            row = await db.execute(
                select(WorkflowSession).where(WorkflowSession.session_id == sid)
            )
            assert row.scalar_one().interview_prep is None

    @pytest.mark.asyncio
    async def test_get_interview_prep_not_found_direct(self, prep_user) -> None:
        uid, email = prep_user
        async with _NullSessionLocal() as db:
            with patch("api.interview_prep.get_cached_interview_prep", AsyncMock(return_value=None)):
                with pytest.raises(APIError) as exc:
                    await get_interview_prep(
                        session_id=str(uuid.uuid4()),
                        current_user=_user_dict(uid, email),
                        db=db,
                    )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_status_not_found_direct(self, prep_user) -> None:
        uid, email = prep_user
        async with _NullSessionLocal() as db:
            with pytest.raises(APIError) as exc:
                await get_interview_prep_status(
                    session_id=str(uuid.uuid4()),
                    current_user=_user_dict(uid, email),
                    db=db,
                )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_not_found_direct(self, prep_user) -> None:
        uid, email = prep_user
        async with _NullSessionLocal() as db:
            with pytest.raises(APIError) as exc:
                await delete_interview_prep(
                    session_id=str(uuid.uuid4()),
                    current_user=_user_dict(uid, email),
                    db=db,
                )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_status_internal_error(self, prep_user) -> None:
        uid, email = prep_user
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("db fail"))
        with pytest.raises(APIError) as exc:
            await get_interview_prep_status(
                session_id=str(uuid.uuid4()),
                current_user=_user_dict(uid, email),
                db=mock_db,
            )
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_generate_internal_error(self, prep_user) -> None:
        uid, email = prep_user
        sid = await _seed_session(uid)
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("db fail"))
        with patch("api.interview_prep.check_rate_limit", AsyncMock(return_value=(True, 4))):
            with pytest.raises(APIError) as exc:
                await generate_interview_prep(
                    session_id=sid,
                    background_tasks=BackgroundTasks(),
                    regenerate=False,
                    current_user=_user_dict(uid, email),
                    db=mock_db,
                )
        assert exc.value.status_code == 500


class TestInterviewPrepBackgroundErrors:
    @pytest.mark.asyncio
    async def test_background_persists_error_state(self, prep_user) -> None:
        uid, _ = prep_user
        sid = await _seed_session(uid)

        mock_agent = MagicMock()
        mock_agent.generate = AsyncMock(side_effect=RuntimeError("LLM failed"))

        @asynccontextmanager
        async def _null_get_session():
            async with _NullSessionLocal() as db:
                yield db

        with (
            patch("api.interview_prep.get_session", _null_get_session),
            patch("api.interview_prep.InterviewPrepAgent", return_value=mock_agent),
            patch("api.interview_prep.broadcast_interview_prep_started", AsyncMock()),
            patch("api.interview_prep.broadcast_interview_prep_error", AsyncMock()) as err_broadcast,
            patch("api.interview_prep.report_exception", AsyncMock()) as report,
            patch("api.interview_prep.clear_interview_prep_generating", AsyncMock()),
        ):
            await _generate_interview_prep_background(sid, user_id=str(uid))

        report.assert_awaited_once()
        err_broadcast.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_background_broadcast_error_failure_logged(self, prep_user) -> None:
        uid, _ = prep_user
        sid = await _seed_session(uid)

        mock_agent = MagicMock()
        mock_agent.generate = AsyncMock(side_effect=RuntimeError("LLM failed"))

        @asynccontextmanager
        async def _null_get_session():
            async with _NullSessionLocal() as db:
                yield db

        with (
            patch("api.interview_prep.get_session", _null_get_session),
            patch("api.interview_prep.InterviewPrepAgent", return_value=mock_agent),
            patch("api.interview_prep.broadcast_interview_prep_started", AsyncMock()),
            patch(
                "api.interview_prep.broadcast_interview_prep_error",
                AsyncMock(side_effect=RuntimeError("ws closed")),
            ),
            patch("api.interview_prep.report_exception", AsyncMock()),
            patch("api.interview_prep.clear_interview_prep_generating", AsyncMock()),
        ):
            await _generate_interview_prep_background(sid, user_id=str(uid))
