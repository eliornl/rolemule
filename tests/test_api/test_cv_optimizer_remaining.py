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
    _export_optimized_cv_file,
    _generate_cv_html_from_markdown,
    _get_user_api_key,
    _markdown_cv_to_odt,
    _markdown_cv_to_odt_via_libreoffice,
    delete_cv_optimization,
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
    @pytest.mark.asyncio
    async def test_get_user_api_key_cfg_returns_none(self, session_bundle) -> None:
        uid, _email, _sid = session_bundle
        mock_db = AsyncMock()
        from utils.error_responses import no_api_key_error

        with patch(
            "utils.llm_context.require_user_llm_context",
            AsyncMock(side_effect=no_api_key_error()),
        ):
            assert await _get_user_api_key(mock_db, uid) is None

    @pytest.mark.asyncio
    async def test_get_user_api_key_generic_exception_returns_none(self, session_bundle) -> None:
        uid, _email, _sid = session_bundle
        mock_db = AsyncMock()
        with patch(
            "utils.llm_context.require_user_llm_context",
            AsyncMock(side_effect=RuntimeError("db fail")),
        ):
            assert await _get_user_api_key(mock_db, uid) is None

    @pytest.mark.asyncio
    async def test_start_success_direct(self, session_bundle) -> None:
        uid, email, sid = session_bundle
        async with _NullSessionLocal() as db:
            with (
                patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 9))),
                patch("api.cv_optimizer.set_cv_optimization_running", AsyncMock(return_value=True)),
                patch("api.cv_optimizer._run_cv_optimization_background", AsyncMock()),
                patch("utils.llm_preferences.load_preferred_model", AsyncMock(return_value=None)),
            ):
                result = await start_cv_optimization(
                    session_id=sid,
                    background_tasks=BackgroundTasks(),
                    request=CvOptimizationStartRequest(max_iterations=3, score_threshold=8.0),
                    current_user=_user_dict(uid, email),
                    db=db,
                )
        assert result.status == "started"
        assert result.session_id == sid

    @pytest.mark.asyncio
    async def test_get_result_from_db_caches(self, session_bundle) -> None:
        uid, email, sid = session_bundle
        cached_payload = {"optimized_cv": "# Jane", "best_score": 8.5}
        async with _NullSessionLocal() as db:
            ws = (await db.execute(
                select(WorkflowSession).where(WorkflowSession.session_id == sid)
            )).scalar_one()
            ws.cv_optimization = cached_payload
            await db.commit()
            with (
                patch("api.cv_optimizer.get_cached_cv_optimization", AsyncMock(return_value=None)),
                patch("api.cv_optimizer.cache_cv_optimization", AsyncMock(return_value=None)) as cache_mock,
            ):
                resp = await get_cv_optimization(
                    session_id=sid,
                    current_user=_user_dict(uid, email),
                    db=db,
                )
        assert resp.has_result is True
        cache_mock.assert_awaited()

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

    @pytest.mark.asyncio
    async def test_start_rate_limited(self, session_bundle) -> None:
        uid, email, sid = session_bundle
        async with _NullSessionLocal() as db:
            with patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(False, 0))):
                with pytest.raises(APIError) as exc:
                    await start_cv_optimization(
                        session_id=sid,
                        background_tasks=BackgroundTasks(),
                        request=CvOptimizationStartRequest(),
                        current_user=_user_dict(uid, email),
                        db=db,
                    )
        assert exc.value.status_code == 429

    @pytest.mark.asyncio
    async def test_start_missing_job_analysis_returns_422(self, session_bundle) -> None:
        uid, email, sid = session_bundle
        async with _NullSessionLocal() as db:
            ws = (await db.execute(
                select(WorkflowSession).where(WorkflowSession.session_id == sid)
            )).scalar_one()
            ws.job_analysis = None
            await db.commit()
            with patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 9))):
                with pytest.raises(APIError) as exc:
                    await start_cv_optimization(
                        session_id=sid,
                        background_tasks=BackgroundTasks(),
                        request=CvOptimizationStartRequest(),
                        current_user=_user_dict(uid, email),
                        db=db,
                    )
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_start_already_running_returns_409(self, session_bundle) -> None:
        uid, email, sid = session_bundle
        async with _NullSessionLocal() as db:
            with (
                patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 9))),
                patch("api.cv_optimizer.set_cv_optimization_running", AsyncMock(return_value=False)),
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

    @pytest.mark.asyncio
    async def test_delete_cv_optimization_direct(self, session_bundle) -> None:
        uid, email, sid = session_bundle
        async with _NullSessionLocal() as db:
            ws = (await db.execute(
                select(WorkflowSession).where(WorkflowSession.session_id == sid)
            )).scalar_one()
            ws.cv_optimization = {"optimized_cv": "# Jane", "best_score": 7.0}
            await db.commit()
            with (
                patch("api.cv_optimizer.is_cv_optimization_running", AsyncMock(return_value=False)),
                patch("api.cv_optimizer.invalidate_cv_optimization", AsyncMock(return_value=None)),
            ):
                await delete_cv_optimization(
                    session_id=sid,
                    current_user=_user_dict(uid, email),
                    db=db,
                )
            ws2 = (await db.execute(
                select(WorkflowSession).where(WorkflowSession.session_id == sid)
            )).scalar_one()
            assert ws2.cv_optimization is None

    @pytest.mark.asyncio
    async def test_delete_while_running_returns_409(self, session_bundle) -> None:
        uid, email, sid = session_bundle
        async with _NullSessionLocal() as db:
            with patch("api.cv_optimizer.is_cv_optimization_running", AsyncMock(return_value=True)):
                with pytest.raises(APIError) as exc:
                    await delete_cv_optimization(
                        session_id=sid,
                        current_user=_user_dict(uid, email),
                        db=db,
                    )
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_download_rate_limited(self, session_bundle) -> None:
        uid, email, sid = session_bundle
        async with _NullSessionLocal() as db:
            with patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(False, 0))):
                with pytest.raises(APIError) as exc:
                    await download_optimized_cv_odt(
                        session_id=sid,
                        current_user=_user_dict(uid, email),
                        db=db,
                    )
        assert exc.value.status_code == 429

    @pytest.mark.asyncio
    async def test_download_no_optimization_result(self, session_bundle) -> None:
        uid, email, sid = session_bundle
        async with _NullSessionLocal() as db:
            with (
                patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 9))),
                patch("api.cv_optimizer.get_cached_cv_optimization", AsyncMock(return_value=None)),
            ):
                with pytest.raises(APIError) as exc:
                    await download_optimized_cv_odt(
                        session_id=sid,
                        current_user=_user_dict(uid, email),
                        db=db,
                    )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_export_libreoffice_failure_falls_back_to_docx(self) -> None:
        with (
            patch("api.cv_optimizer._resolve_soffice_path", return_value="/usr/bin/soffice"),
            patch(
                "api.cv_optimizer._markdown_cv_to_odt_via_libreoffice",
                AsyncMock(side_effect=RuntimeError("lo failed")),
            ),
        ):
            data, media_type, filename = await _export_optimized_cv_file("# Jane\n\n## Skills\nPython", None)
        assert filename == "optimized-cv.docx"
        assert data[:2] == b"PK"
        assert "wordprocessingml" in media_type

    @pytest.mark.asyncio
    async def test_get_status_internal_error(self, session_bundle) -> None:
        uid, email, sid = session_bundle
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("db fail"))
        with pytest.raises(APIError) as exc:
            await get_cv_optimization_status(
                session_id=sid,
                current_user=_user_dict(uid, email),
                db=mock_db,
            )
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_start_in_progress_detail(self) -> None:
        uid, email, sid = await _seed_user_and_session(
            workflow_status=WorkflowStatusEnum.IN_PROGRESS.value,
        )
        try:
            async with _NullSessionLocal() as db:
                with patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 9))):
                    with pytest.raises(APIError) as exc:
                        await start_cv_optimization(
                            session_id=sid,
                            background_tasks=BackgroundTasks(),
                            request=CvOptimizationStartRequest(),
                            current_user=_user_dict(uid, email),
                            db=db,
                        )
            assert "still running" in exc.value.message.lower()
        finally:
            await _cleanup(uid)

    @pytest.mark.asyncio
    async def test_markdown_cv_to_odt_libreoffice_valueerror_fallback(self) -> None:
        with (
            patch("api.cv_optimizer._resolve_soffice_path", return_value="/usr/bin/soffice"),
            patch(
                "api.cv_optimizer._markdown_cv_to_odt_via_libreoffice",
                AsyncMock(side_effect=ValueError("LibreOffice failed")),
            ),
            patch(
                "api.cv_optimizer._generate_cv_html_from_markdown",
                AsyncMock(return_value="<!DOCTYPE html><html><body>CV</body></html>"),
            ),
            patch("api.cv_optimizer.html_cv_to_odt_bytes", return_value=b"odt"),
        ):
            result = await _markdown_cv_to_odt("# CV", None)
        assert result == b"odt"

    @pytest.mark.asyncio
    async def test_delete_not_found(self) -> None:
        uid = uuid.uuid4()
        email = f"ghost_{uid.hex[:8]}@example.com"
        async with _NullSessionLocal() as db:
            with pytest.raises(APIError) as exc:
                await delete_cv_optimization(
                    session_id=str(uuid.uuid4()),
                    current_user=_user_dict(uid, email),
                    db=db,
                )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_download_quota_raises_429(self, session_bundle) -> None:
        uid, email, sid = session_bundle
        from utils.llm.errors import LLMError

        async with _NullSessionLocal() as db:
            ws = (await db.execute(
                select(WorkflowSession).where(WorkflowSession.session_id == sid)
            )).scalar_one()
            ws.cv_optimization = {"optimized_cv": "# Jane\n\n## Skills\nPython"}
            await db.commit()
            with (
                patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 9))),
                patch("api.cv_optimizer._get_user_api_key", AsyncMock(return_value="key")),
                patch("api.cv_optimizer.get_cached_cv_optimization", AsyncMock(return_value=None)),
                patch(
                    "api.cv_optimizer._export_optimized_cv_file",
                    AsyncMock(side_effect=LLMError("RESOURCE_EXHAUSTED", provider="gemini")),
                ),
            ):
                with pytest.raises(APIError) as exc:
                    await download_optimized_cv_odt(
                        session_id=sid,
                        current_user=_user_dict(uid, email),
                        db=db,
                    )
        assert exc.value.status_code == 429

    @pytest.mark.asyncio
    async def test_download_libreoffice_valueerror_503(self, session_bundle) -> None:
        uid, email, sid = session_bundle
        async with _NullSessionLocal() as db:
            ws = (await db.execute(
                select(WorkflowSession).where(WorkflowSession.session_id == sid)
            )).scalar_one()
            ws.cv_optimization = {"optimized_cv": "# Jane\n\n## Skills\nPython"}
            await db.commit()
            with (
                patch("api.cv_optimizer.check_rate_limit", AsyncMock(return_value=(True, 9))),
                patch("api.cv_optimizer._get_user_api_key", AsyncMock(return_value="key")),
                patch("api.cv_optimizer.get_cached_cv_optimization", AsyncMock(return_value=None)),
                patch(
                    "api.cv_optimizer._export_optimized_cv_file",
                    AsyncMock(side_effect=ValueError("LibreOffice conversion failed")),
                ),
            ):
                with pytest.raises(APIError) as exc:
                    await download_optimized_cv_odt(
                        session_id=sid,
                        current_user=_user_dict(uid, email),
                        db=db,
                    )
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_libreoffice_conversion_nonzero_exit(self) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = b"conversion failed"
        with (
            patch(
                "api.cv_optimizer._generate_cv_html_from_markdown",
                AsyncMock(return_value="<!DOCTYPE html><html><body>CV</body></html>"),
            ),
            patch("api.cv_optimizer.asyncio.get_event_loop") as mock_loop,
            patch("api.cv_optimizer.tempfile.mkdtemp", return_value="/tmp/cvo_test"),
            patch("api.cv_optimizer.os.path.join", side_effect=lambda *a: "/".join(a)),
            patch("builtins.open", MagicMock()),
            patch("api.cv_optimizer.os.path.exists", return_value=False),
            patch("api.cv_optimizer.shutil.rmtree"),
        ):
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=mock_proc)
            with pytest.raises(ValueError, match="LibreOffice"):
                await _markdown_cv_to_odt_via_libreoffice("# CV", "key", "/usr/bin/soffice")

    @pytest.mark.asyncio
    async def test_export_quota_reraises(self) -> None:
        from utils.llm.errors import LLMError

        with (
            patch("api.cv_optimizer._resolve_soffice_path", return_value="/usr/bin/soffice"),
            patch(
                "api.cv_optimizer._markdown_cv_to_odt_via_libreoffice",
                AsyncMock(side_effect=LLMError("RESOURCE_EXHAUSTED", provider="gemini")),
            ),
        ):
            with pytest.raises(LLMError):
                await _export_optimized_cv_file("# Jane", "key")
