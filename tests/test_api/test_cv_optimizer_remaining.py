"""
Direct-handler coverage for remaining api/cv_optimizer.py gaps.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import select

from api.cv_optimizer import (
    CvOptimizationStartRequest,
    _generate_cv_html_from_markdown,
    _markdown_cv_to_odt,
    download_optimized_cv_odt,
    get_cv_optimization,
    get_cv_optimization_status,
    start_cv_optimization,
)
from models.database import User, WorkflowSession, WorkflowStatusEnum
from tests.test_api.conftest import _NullSessionLocal
from utils.error_responses import APIError


def _user_dict(uid: uuid.UUID, email: str) -> dict:
    return {"id": str(uid), "_id": str(uid), "email": email, "full_name": "CVO User"}


async def _seed_user_and_session(
    *,
    workflow_status=WorkflowStatusEnum.COMPLETED.value,
    cv_optimization=None,
    job_analysis=None,
    user_data=None,
    resume_recommendations=None,
    cover_letter=None,
) -> tuple[uuid.UUID, str, str]:
    uid = uuid.uuid4()
    email = f"cvo_{uid.hex[:10]}@example.com"
    session_id = str(uuid.uuid4())
    async with _NullSessionLocal() as db:
        db.add(
            User(
                id=uid,
                email=email,
                password_hash="$2b$12$placeholder",
                auth_method="local",
                full_name="CVO User",
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
        db.add(
            WorkflowSession(
                id=uuid.uuid4(),
                session_id=session_id,
                user_id=uid,
                workflow_status=workflow_status,
                job_analysis=job_analysis or {"job_title": "Engineer", "company_name": "Co"},
                user_data=user_data or {"full_name": "Jane", "skills": ["Python"]},
                resume_recommendations=resume_recommendations,
                cover_letter=cover_letter,
                cv_optimization=cv_optimization,
            )
        )
        await db.commit()
    return uid, email, session_id


async def _cleanup(uid: uuid.UUID) -> None:
    from sqlalchemy import delete

    async with _NullSessionLocal() as db:
        await db.execute(delete(WorkflowSession).where(WorkflowSession.user_id == uid))
        await db.execute(delete(User).where(User.id == uid))
        await db.commit()


class TestCvOptimizerDirectHandlers:
    @pytest.fixture
    async def session_bundle(self):
        uid, email, sid = await _seed_user_and_session()
        yield uid, email, sid
        await _cleanup(uid)

    @pytest.mark.asyncio
    async def test_get_result_cache_hit_direct(self, session_bundle) -> None:
        uid, email, sid = session_bundle
        cached = {"optimized_cv": "# Jane", "best_score": 8.0}
        async with _NullSessionLocal() as db:
            with patch("api.cv_optimizer.get_cached_cv_optimization", AsyncMock(return_value=cached)):
                resp = await get_cv_optimization(
                    session_id=sid,
                    current_user=_user_dict(uid, email),
                    db=db,
                )
        assert resp.has_result is True
        assert resp.result["optimized_cv"] == "# Jane"

    @pytest.mark.asyncio
    async def test_get_status_direct(self, session_bundle) -> None:
        uid, email, sid = session_bundle
        async with _NullSessionLocal() as db:
            await db.execute(
                select(WorkflowSession).where(WorkflowSession.session_id == sid)
            )
            ws = (await db.execute(
                select(WorkflowSession).where(WorkflowSession.session_id == sid)
            )).scalar_one()
            ws.cv_optimization = {"best_score": 7.5, "completed_at": "2026-01-01T00:00:00+00:00"}
            await db.commit()
            with patch("api.cv_optimizer.is_cv_optimization_running", AsyncMock(return_value=False)):
                resp = await get_cv_optimization_status(
                    session_id=sid,
                    current_user=_user_dict(uid, email),
                    db=db,
                )
        assert resp.best_score == 7.5
        assert resp.has_result is True

    @pytest.mark.asyncio
    async def test_start_awaiting_confirmation_returns_409(self) -> None:
        uid, email, sid = await _seed_user_and_session(
            workflow_status=WorkflowStatusEnum.AWAITING_CONFIRMATION.value,
        )
        try:
            async with _NullSessionLocal() as db:
                with (
                    patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 9))),
                    patch("api.cv_optimizer._get_user_api_key", AsyncMock(return_value="key")),
                ):
                    with pytest.raises(APIError) as exc:
                        await start_cv_optimization(
                            session_id=sid,
                            background_tasks=BackgroundTasks(),
                            request=CvOptimizationStartRequest(),
                            current_user=_user_dict(uid, email),
                            db=db,
                        )
            assert exc.value.status_code == 409
            assert "confirmation" in exc.value.message.lower()
        finally:
            await _cleanup(uid)

    @pytest.mark.asyncio
    async def test_start_failed_workflow_returns_409(self) -> None:
        uid, email, sid = await _seed_user_and_session(
            workflow_status=WorkflowStatusEnum.FAILED.value,
        )
        try:
            async with _NullSessionLocal() as db:
                with (
                    patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 9))),
                    patch("api.cv_optimizer._get_user_api_key", AsyncMock(return_value="key")),
                ):
                    with pytest.raises(APIError) as exc:
                        await start_cv_optimization(
                            session_id=sid,
                            background_tasks=BackgroundTasks(),
                            request=CvOptimizationStartRequest(),
                            current_user=_user_dict(uid, email),
                            db=db,
                        )
            assert exc.value.status_code == 409
            assert "failed" in exc.value.message.lower()
        finally:
            await _cleanup(uid)

    @pytest.mark.asyncio
    async def test_download_docx_real_fallback(self, session_bundle) -> None:
        uid, email, sid = session_bundle
        async with _NullSessionLocal() as db:
            ws = (await db.execute(
                select(WorkflowSession).where(WorkflowSession.session_id == sid)
            )).scalar_one()
            ws.cv_optimization = {"optimized_cv": "# Jane Doe\n\n## Experience\n- Built APIs"}
            await db.commit()
            with (
                patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 9))),
                patch("api.cv_optimizer._get_user_api_key", AsyncMock(return_value=None)),
                patch("api.cv_optimizer.get_cached_cv_optimization", AsyncMock(return_value=None)),
                patch("api.cv_optimizer._resolve_soffice_path", return_value=None),
            ):
                resp = await download_optimized_cv_odt(
                    session_id=sid,
                    current_user=_user_dict(uid, email),
                    db=db,
                )
        assert resp.status_code == 200
        body = b""
        async for chunk in resp.body_iterator:
            body += chunk
        assert body.startswith(b"PK")

    @pytest.mark.asyncio
    async def test_generate_cv_html_no_html_raises(self) -> None:
        mock_client = MagicMock()
        mock_client.generate = AsyncMock(return_value={"response": "plain text only", "done": True})
        with patch("utils.llm_client.get_gemini_client", AsyncMock(return_value=mock_client)):
            with pytest.raises(ValueError, match="valid HTML"):
                await _generate_cv_html_from_markdown("# Jane", "key")

    @pytest.mark.asyncio
    async def test_markdown_cv_to_odt_html_fallback(self) -> None:
        with (
            patch("api.cv_optimizer._resolve_soffice_path", return_value=None),
            patch(
                "api.cv_optimizer._generate_cv_html_from_markdown",
                AsyncMock(return_value="<!DOCTYPE html><html><body>CV</body></html>"),
            ),
            patch("api.cv_optimizer.html_cv_to_odt_bytes", return_value=b"odt-bytes"),
        ):
            result = await _markdown_cv_to_odt("# CV", None)
        assert result == b"odt-bytes"

    @pytest.mark.asyncio
    async def test_start_internal_error(self, session_bundle) -> None:
        uid, email, sid = session_bundle
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("db fail"))
        with (
            patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 9))),
            patch("api.cv_optimizer._get_user_api_key", AsyncMock(return_value="key")),
        ):
            with pytest.raises(APIError) as exc:
                await start_cv_optimization(
                    session_id=sid,
                    background_tasks=BackgroundTasks(),
                    request=CvOptimizationStartRequest(),
                    current_user=_user_dict(uid, email),
                    db=mock_db,
                )
        assert exc.value.status_code == 500
