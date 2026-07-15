"""
Direct-handler coverage for remaining api/tools.py gaps.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from starlette.responses import Response

from api.tools import (
    FollowUpRequest,
    FollowUpStage,
    RejectionAnalysisRequest,
    ReferenceRequestRequest,
    ThankYouNoteRequest,
    _check_api_key_available,
    _get_user_api_key,
    _resolve_llm,
    analyze_rejection,
    compare_jobs,
    generate_followup,
    generate_reference_request,
    generate_thank_you_note,
    get_followup_stages,
    get_salary_coaching,
)
from models.database import AuthMethod, User, UserProfile, UserWorkflowPreferences
from tests.test_api.conftest import _NullSessionLocal
from tests.test_api.test_career_tools import (
    FOLLOWUP_RESULT,
    JOB_COMPARISON_RESULT,
    REJECTION_RESULT,
    REFERENCE_RESULT,
    SALARY_RESULT,
    THANK_YOU_RESULT,
)
from utils.error_responses import APIError
from utils.llm.availability import UserLLMContext


def _ready_llm_ctx():
    return UserLLMContext(
        provider="ollama",
        user_api_key=None,
        preferred_model=None,
        ready=True,
    )



def _user(uid: uuid.UUID, email: str) -> dict:
    return {"id": str(uid), "_id": str(uid), "email": email, "full_name": "Tools User"}


async def _seed_ollama_user() -> tuple[uuid.UUID, str]:
    uid = uuid.uuid4()
    email = f"tools_{uid.hex[:10]}@example.com"
    async with _NullSessionLocal() as db:
        db.add(
            User(
                id=uid,
                email=email,
                password_hash="$2b$12$placeholder",
                auth_method=AuthMethod.LOCAL.value,
                full_name="Tools User",
            )
        )
        db.add(
            UserWorkflowPreferences(
                id=uuid.uuid4(),
                user_id=uid,
                preferred_provider="ollama",
            )
        )
        await db.commit()
    return uid, email


async def _delete_user(uid: uuid.UUID) -> None:
    from sqlalchemy import delete

    async with _NullSessionLocal() as db:
        await db.execute(delete(UserWorkflowPreferences).where(UserWorkflowPreferences.user_id == uid))
        await db.execute(delete(UserProfile).where(UserProfile.user_id == uid))
        await db.execute(delete(User).where(User.id == uid))
        await db.commit()


class TestToolsHelpersDirect:
    @pytest.mark.asyncio
    async def test_resolve_llm_with_ollama_user(self) -> None:
        uid, _email = await _seed_ollama_user()
        try:
            async with _NullSessionLocal() as db:
                ctx = await _resolve_llm(db, uid)
            assert ctx.provider == "ollama"
            assert ctx.ready is True
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_check_api_key_unavailable_without_prefs(self) -> None:
        uid = uuid.uuid4()
        email = f"noprefs_{uid.hex[:10]}@example.com"
        async with _NullSessionLocal() as db:
            db.add(
                User(
                    id=uid,
                    email=email,
                    password_hash="$2b$12$placeholder",
                    auth_method=AuthMethod.LOCAL.value,
                    full_name="No Prefs",
                )
            )
            await db.commit()
        try:
            async with _NullSessionLocal() as db:
                assert await _check_api_key_available(db, uid) is False
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_get_user_api_key_non_cfg_exception_returns_none(self) -> None:
        uid, _email = await _seed_ollama_user()
        mock_db = AsyncMock()
        try:
            with patch(
                "utils.llm_context.require_user_llm_context",
                AsyncMock(side_effect=RuntimeError("db down")),
            ):
                assert await _get_user_api_key(mock_db, uid) is None
        finally:
            await _delete_user(uid)


class TestToolsDirectHandlers:
    @pytest.mark.asyncio
    async def test_compare_jobs_agent_path_builds_response(self) -> None:
        uid = uuid.uuid4()
        email = f"tools_{uid.hex[:10]}@example.com"
        async with _NullSessionLocal() as db:
            db.add(
                User(
                    id=uid,
                    email=email,
                    password_hash="$2b$12$placeholder",
                    auth_method=AuthMethod.LOCAL.value,
                    full_name="Tools User",
                )
            )
            await db.commit()
        try:
            from api.tools import JobComparisonRequest, JobInput

            request = JobComparisonRequest(
                jobs=[
                    JobInput(title="A", company="Co1", description="Desc1"),
                    JobInput(title="B", company="Co2", description="Desc2"),
                ]
            )
            response = Response()
            mock_db = AsyncMock()
            with (
                patch("api.tools._check_rate_limit_and_get_headers", AsyncMock(return_value={})),
                patch("api.tools._check_api_key_available", AsyncMock(return_value=True)),
                patch("api.tools._get_user_api_key", AsyncMock(return_value=None)),
                patch("api.tools._resolve_llm", AsyncMock(return_value=_ready_llm_ctx())),
                patch("utils.llm_preferences.load_preferred_model", AsyncMock(return_value=None)),
                patch("api.tools.get_cached_tool_result", AsyncMock(return_value=None)),
                patch("api.tools.cache_tool_result", AsyncMock(return_value=None)),
                patch("api.tools._get_user_uuid", return_value=uid),
                patch("agents.job_comparison.JobComparisonAgent.compare", AsyncMock(return_value=JOB_COMPARISON_RESULT)),
            ):
                result = await compare_jobs(
                    request=request,
                    response=response,
                    current_user=_user(uid, email),
                    db=mock_db,
                )
            assert result.executive_summary
            assert result.jobs_compared == 2
        finally:
            async with _NullSessionLocal() as db:
                from sqlalchemy import delete

                await db.execute(delete(User).where(User.id == uid))
                await db.commit()

    @pytest.mark.asyncio
    async def test_salary_coach_reads_profile_years(self) -> None:
        uid = uuid.uuid4()
        email = f"salary_{uid.hex[:10]}@example.com"
        async with _NullSessionLocal() as db:
            db.add(
                User(
                    id=uid,
                    email=email,
                    password_hash="$2b$12$placeholder",
                    auth_method=AuthMethod.LOCAL.value,
                    full_name="Salary User",
                )
            )
            db.add(
                UserProfile(
                    id=uuid.uuid4(),
                    user_id=uid,
                    professional_title="Engineer",
                    years_experience=7,
                    summary="Summary.",
                    city="City",
                    state="ST",
                    country="US",
                )
            )
            await db.commit()
        try:
            from api.tools import SalaryCoachRequest

            request = SalaryCoachRequest(
                job_title="Engineer",
                company_name="TechCorp",
                offered_salary="$160,000",
            )
            response = Response()
            async with _NullSessionLocal() as db:
                with (
                    patch("api.tools._check_rate_limit_and_get_headers", AsyncMock(return_value={})),
                    patch("api.tools._check_api_key_available", AsyncMock(return_value=True)),
                    patch("api.tools._get_user_api_key", AsyncMock(return_value=None)),
                patch("api.tools._resolve_llm", AsyncMock(return_value=_ready_llm_ctx())),
                patch("utils.llm_preferences.load_preferred_model", AsyncMock(return_value=None)),
                    patch("api.tools.get_cached_tool_result", AsyncMock(return_value=None)),
                    patch("api.tools.cache_tool_result", AsyncMock(return_value=None)),
                    patch(
                        "agents.salary_coach.SalaryCoachAgent.generate_strategy",
                        AsyncMock(return_value=SALARY_RESULT),
                    ) as agent_mock,
                ):
                    result = await get_salary_coaching(
                        request=request,
                        response=response,
                        current_user=_user(uid, email),
                        db=db,
                    )
            assert result.job_title == "Engineer"
            assert agent_mock.await_args.kwargs.get("years_experience") == 7
        finally:
            async with _NullSessionLocal() as db:
                from sqlalchemy import delete

                await db.execute(delete(UserProfile).where(UserProfile.user_id == uid))
                await db.execute(delete(User).where(User.id == uid))
                await db.commit()

    @pytest.mark.asyncio
    async def test_salary_coach_cache_hit_direct(self) -> None:
        uid = uuid.uuid4()
        email = f"salaryc_{uid.hex[:10]}@example.com"
        from api.tools import SalaryCoachRequest

        request = SalaryCoachRequest(
            job_title="Engineer",
            company_name="Co",
            offered_salary="$150k",
            years_experience=5,
        )
        response = Response()
        mock_db = AsyncMock()
        with (
            patch("api.tools._check_rate_limit_and_get_headers", AsyncMock(return_value={})),
            patch("api.tools._check_api_key_available", AsyncMock(return_value=True)),
            patch("api.tools._get_user_api_key", AsyncMock(return_value=None)),
                patch("api.tools._resolve_llm", AsyncMock(return_value=_ready_llm_ctx())),
                patch("utils.llm_preferences.load_preferred_model", AsyncMock(return_value=None)),
            patch("api.tools.get_cached_tool_result", AsyncMock(return_value=SALARY_RESULT)),
            patch("api.tools._get_user_uuid", return_value=uid),
        ):
            result = await get_salary_coaching(
                request=request,
                response=response,
                current_user=_user(uid, email),
                db=mock_db,
            )
        assert result.job_title == SALARY_RESULT["job_title"]

    @pytest.mark.asyncio
    async def test_compare_jobs_value_error(self) -> None:
        uid = uuid.uuid4()
        from api.tools import JobComparisonRequest, JobInput

        request = JobComparisonRequest(
            jobs=[
                JobInput(title="A", company="Co1", description="D1"),
                JobInput(title="B", company="Co2", description="D2"),
            ]
        )
        response = Response()
        mock_db = AsyncMock()
        with (
            patch("api.tools._check_rate_limit_and_get_headers", AsyncMock(return_value={})),
            patch("api.tools._check_api_key_available", AsyncMock(return_value=True)),
            patch("api.tools._get_user_api_key", AsyncMock(return_value=None)),
                patch("api.tools._resolve_llm", AsyncMock(return_value=_ready_llm_ctx())),
                patch("utils.llm_preferences.load_preferred_model", AsyncMock(return_value=None)),
            patch("api.tools.get_cached_tool_result", AsyncMock(return_value=None)),
            patch("api.tools._get_user_uuid", return_value=uid),
            patch(
                "agents.job_comparison.JobComparisonAgent.compare",
                AsyncMock(side_effect=ValueError("bad input")),
            ),
        ):
            with pytest.raises(APIError) as exc:
                await compare_jobs(
                    request=request,
                    response=response,
                    current_user=_user(uid, "u@example.com"),
                    db=mock_db,
                )
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_get_followup_stages_direct(self) -> None:
        uid = uuid.uuid4()
        stages = await get_followup_stages(current_user=_user(uid, "u@example.com"))
        assert len(stages.stages) >= 1

    @pytest.mark.asyncio
    async def test_thank_you_cache_hit_direct(self) -> None:
        uid, email = await _seed_ollama_user()
        try:
            response = Response()
            async with _NullSessionLocal() as db:
                with (
                    patch("api.tools._check_rate_limit_and_get_headers", AsyncMock(return_value={})),
                    patch("api.tools.get_cached_tool_result", AsyncMock(return_value=THANK_YOU_RESULT)),
                ):
                    result = await generate_thank_you_note(
                        request=ThankYouNoteRequest(
                            interviewer_name="Sam",
                            interview_type="phone",
                            company_name="Co",
                            job_title="Engineer",
                        ),
                        response=response,
                        current_user=_user(uid, email),
                        db=db,
                    )
            assert result.email_body == THANK_YOU_RESULT["email_body"]
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_rejection_cache_hit_direct(self) -> None:
        uid, email = await _seed_ollama_user()
        try:
            response = Response()
            async with _NullSessionLocal() as db:
                with (
                    patch("api.tools._check_rate_limit_and_get_headers", AsyncMock(return_value={})),
                    patch("api.tools.get_cached_tool_result", AsyncMock(return_value=REJECTION_RESULT)),
                ):
                    result = await analyze_rejection(
                        request=RejectionAnalysisRequest(
                            rejection_email="Dear candidate, we regret...",
                        ),
                        response=response,
                        current_user=_user(uid, email),
                        db=db,
                    )
            assert result.encouragement == REJECTION_RESULT["encouragement"]
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_thank_you_direct_agent_path(self) -> None:
        uid, email = await _seed_ollama_user()
        try:
            response = Response()
            async with _NullSessionLocal() as db:
                with (
                    patch("api.tools._check_rate_limit_and_get_headers", AsyncMock(return_value={})),
                    patch("api.tools.get_cached_tool_result", AsyncMock(return_value=None)),
                    patch("api.tools.cache_tool_result", AsyncMock(return_value=None)),
                    patch(
                        "agents.thank_you_writer.ThankYouWriterAgent.generate",
                        AsyncMock(return_value=THANK_YOU_RESULT),
                    ),
                ):
                    result = await generate_thank_you_note(
                        request=ThankYouNoteRequest(
                            interviewer_name="Sam",
                            interview_type="phone",
                            company_name="Co",
                            job_title="Engineer",
                        ),
                        response=response,
                        current_user=_user(uid, email),
                        db=db,
                    )
            assert result.subject_line == THANK_YOU_RESULT["subject_line"]
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_rejection_direct_agent_path(self) -> None:
        uid, email = await _seed_ollama_user()
        try:
            response = Response()
            async with _NullSessionLocal() as db:
                with (
                    patch("api.tools._check_rate_limit_and_get_headers", AsyncMock(return_value={})),
                    patch("api.tools.get_cached_tool_result", AsyncMock(return_value=None)),
                    patch("api.tools.cache_tool_result", AsyncMock(return_value=None)),
                    patch(
                        "agents.rejection_analyzer.RejectionAnalyzerAgent.analyze",
                        AsyncMock(return_value=REJECTION_RESULT),
                    ),
                ):
                    result = await analyze_rejection(
                        request=RejectionAnalysisRequest(
                            rejection_email="Dear candidate, we regret to inform you...",
                        ),
                        response=response,
                        current_user=_user(uid, email),
                        db=db,
                    )
            assert result.analysis_summary == REJECTION_RESULT["analysis_summary"]
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_reference_request_direct_agent_path(self) -> None:
        uid, email = await _seed_ollama_user()
        try:
            response = Response()
            async with _NullSessionLocal() as db:
                with (
                    patch("api.tools._check_rate_limit_and_get_headers", AsyncMock(return_value={})),
                    patch("api.tools.get_cached_tool_result", AsyncMock(return_value=None)),
                    patch("api.tools.cache_tool_result", AsyncMock(return_value=None)),
                    patch(
                        "agents.reference_request_writer.ReferenceRequestWriterAgent.generate",
                        AsyncMock(return_value=REFERENCE_RESULT),
                    ),
                ):
                    result = await generate_reference_request(
                        request=ReferenceRequestRequest(
                            reference_name="Bob",
                            reference_relationship="Manager",
                        ),
                        response=response,
                        current_user=_user(uid, email),
                        db=db,
                    )
            assert result.email_body == REFERENCE_RESULT["email_body"]
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_followup_direct_agent_path(self) -> None:
        uid, email = await _seed_ollama_user()
        try:
            response = Response()
            async with _NullSessionLocal() as db:
                with (
                    patch("api.tools._check_rate_limit_and_get_headers", AsyncMock(return_value={})),
                    patch("api.tools.get_cached_tool_result", AsyncMock(return_value=None)),
                    patch("api.tools.cache_tool_result", AsyncMock(return_value=None)),
                    patch(
                        "agents.followup_generator.FollowUpGeneratorAgent.generate",
                        AsyncMock(return_value=FOLLOWUP_RESULT),
                    ),
                ):
                    result = await generate_followup(
                        request=FollowUpRequest(
                            stage=FollowUpStage.AFTER_INTERVIEW,
                            company_name="Co",
                            job_title="Engineer",
                        ),
                        response=response,
                        current_user=_user(uid, email),
                        db=db,
                    )
            assert result.stage == FOLLOWUP_RESULT["stage"]
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_thank_you_internal_error(self) -> None:
        uid, email = await _seed_ollama_user()
        try:
            response = Response()
            mock_db = AsyncMock()
            with (
                patch("api.tools._check_rate_limit_and_get_headers", AsyncMock(return_value={})),
                patch("api.tools._check_api_key_available", AsyncMock(return_value=True)),
                patch("api.tools._resolve_llm", AsyncMock(return_value=_ready_llm_ctx())),
                patch("utils.llm_preferences.load_preferred_model", AsyncMock(return_value=None)),
                patch("api.tools.get_cached_tool_result", AsyncMock(return_value=None)),
                patch(
                    "agents.thank_you_writer.ThankYouWriterAgent.generate",
                    AsyncMock(side_effect=RuntimeError("agent fail")),
                ),
            ):
                with pytest.raises(APIError) as exc:
                    await generate_thank_you_note(
                        request=ThankYouNoteRequest(
                            interviewer_name="Sam",
                            interview_type="phone",
                            company_name="Co",
                            job_title="Engineer",
                        ),
                        response=response,
                        current_user=_user(uid, email),
                        db=mock_db,
                    )
            assert exc.value.status_code == 500
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_compare_jobs_no_api_key(self) -> None:
        uid = uuid.uuid4()
        from api.tools import JobComparisonRequest, JobInput

        response = Response()
        mock_db = AsyncMock()
        with (
            patch("api.tools._check_rate_limit_and_get_headers", AsyncMock(return_value={})),
            patch("api.tools._check_api_key_available", AsyncMock(return_value=False)),
        ):
            with pytest.raises(APIError) as exc:
                await compare_jobs(
                    request=JobComparisonRequest(
                        jobs=[
                            JobInput(title="A", company="Co1", description="D1"),
                            JobInput(title="B", company="Co2", description="D2"),
                        ]
                    ),
                    response=response,
                    current_user=_user(uid, "u@example.com"),
                    db=mock_db,
                )
        assert exc.value.error_code.value == "CFG_6001"

    @pytest.mark.asyncio
    async def test_compare_jobs_with_analysis_arrays(self) -> None:
        uid, email = await _seed_ollama_user()
        from api.tools import JobComparisonRequest, JobInput, UserContext

        rich_result = {
            **JOB_COMPARISON_RESULT,
            "jobs_analysis": [
                {
                    "job_identifier": "Engineer",
                    "title": "Engineer",
                    "company": "Co1",
                    "overall_score": 80,
                    "scores": {"comp": 8},
                    "pros": ["Remote"],
                    "cons": ["Pay"],
                    "ideal_for": "Builders",
                    "concerns": ["None"],
                }
            ],
            "decision_factors": [
                {
                    "factor": "Compensation",
                    "importance": "High",
                    "winner": "Engineer",
                    "explanation": "Better pay",
                }
            ],
        }
        response = Response()
        mock_db = AsyncMock()
        try:
            with (
                patch("api.tools._check_rate_limit_and_get_headers", AsyncMock(return_value={})),
                patch("api.tools._check_api_key_available", AsyncMock(return_value=True)),
                patch("api.tools._resolve_llm", AsyncMock(return_value=_ready_llm_ctx())),
                patch("utils.llm_preferences.load_preferred_model", AsyncMock(return_value=None)),
                patch("api.tools.get_cached_tool_result", AsyncMock(return_value=None)),
                patch("api.tools.cache_tool_result", AsyncMock(return_value=None)),
                patch("api.tools._get_user_uuid", return_value=uid),
                patch(
                    "agents.job_comparison.JobComparisonAgent.compare",
                    AsyncMock(return_value=rich_result),
                ),
            ):
                result = await compare_jobs(
                    request=JobComparisonRequest(
                        jobs=[
                            JobInput(title="A", company="Co1", description="D1"),
                            JobInput(title="B", company="Co2", description="D2"),
                        ],
                        user_context=UserContext(career_goals="Lead", experience_years=5),
                    ),
                    response=response,
                    current_user=_user(uid, email),
                    db=mock_db,
                )
            assert len(result.jobs_analysis) == 1
            assert len(result.decision_factors) == 1
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_salary_coach_pushback_arrays(self) -> None:
        uid, email = await _seed_ollama_user()
        from api.tools import SalaryCoachRequest

        rich_salary = {
            **SALARY_RESULT,
            "market_analysis": {
                "salary_assessment": "Below market",
                "market_position": "Low",
                "recommended_target": "$180k",
                "negotiation_room": "High",
                "leverage_assessment": "Strong",
            },
            "strategy_overview": {
                "approach": "Collaborative",
                "key_messages": ["Value"],
                "timing_recommendation": "48h",
                "confidence_level": "High",
            },
            "main_script": {
                "opening": "Hi",
                "value_statement": "I bring",
                "counter_offer": "$180k",
                "closing": "Thanks",
            },
            "pushback_responses": [
                {"scenario": "Budget", "response_script": "Understand", "key_points": ["Flex"]}
            ],
            "alternative_asks": [
                {"item": "Bonus", "value": "$10k", "script": "Could we", "likelihood": "medium"}
            ],
            "email_template": {"subject": "Re: Offer", "body": "Dear"},
            "dos_and_donts": {"dos": ["Stay calm"], "donts": ["Bluff"]},
        }
        response = Response()
        try:
            async with _NullSessionLocal() as db:
                with (
                    patch("api.tools._check_rate_limit_and_get_headers", AsyncMock(return_value={})),
                    patch("api.tools._check_api_key_available", AsyncMock(return_value=True)),
                    patch("api.tools._resolve_llm", AsyncMock(return_value=_ready_llm_ctx())),
                    patch("utils.llm_preferences.load_preferred_model", AsyncMock(return_value=None)),
                    patch("api.tools.get_cached_tool_result", AsyncMock(return_value=None)),
                    patch("api.tools.cache_tool_result", AsyncMock(return_value=None)),
                    patch(
                        "agents.salary_coach.SalaryCoachAgent.generate_strategy",
                        AsyncMock(return_value=rich_salary),
                    ),
                ):
                    result = await get_salary_coaching(
                        request=SalaryCoachRequest(
                            job_title="Engineer",
                            company_name="Co",
                            offered_salary="$150k",
                        ),
                        response=response,
                        current_user=_user(uid, email),
                        db=db,
                    )
            assert len(result.pushback_responses) == 1
            assert len(result.alternative_asks) == 1
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_followup_value_error(self) -> None:
        uid, email = await _seed_ollama_user()
        try:
            response = Response()
            mock_db = AsyncMock()
            with (
                patch("api.tools._check_rate_limit_and_get_headers", AsyncMock(return_value={})),
                patch("api.tools._check_api_key_available", AsyncMock(return_value=True)),
                patch("api.tools._resolve_llm", AsyncMock(return_value=_ready_llm_ctx())),
                patch("utils.llm_preferences.load_preferred_model", AsyncMock(return_value=None)),
                patch("api.tools.get_cached_tool_result", AsyncMock(return_value=None)),
                patch(
                    "agents.followup_generator.FollowUpGeneratorAgent.generate",
                    AsyncMock(side_effect=ValueError("bad stage")),
                ),
            ):
                with pytest.raises(APIError) as exc:
                    await generate_followup(
                        request=FollowUpRequest(
                            stage=FollowUpStage.AFTER_APPLICATION,
                            company_name="Co",
                            job_title="Eng",
                        ),
                        response=response,
                        current_user=_user(uid, email),
                        db=mock_db,
                    )
            assert exc.value.status_code == 422
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_rejection_with_application_context(self) -> None:
        uid, email = await _seed_ollama_user()
        app_id = uuid.uuid4()
        async with _NullSessionLocal() as db:
            from models.database import JobApplication

            db.add(
                JobApplication(
                    id=app_id,
                    user_id=uid,
                    job_title="From App Title",
                    company_name="From App Co",
                    status="completed",
                )
            )
            await db.commit()
        try:
            response = Response()
            async with _NullSessionLocal() as db:
                with (
                    patch("api.tools._check_rate_limit_and_get_headers", AsyncMock(return_value={})),
                    patch("api.tools.get_cached_tool_result", AsyncMock(return_value=REJECTION_RESULT)),
                ):
                    result = await analyze_rejection(
                        request=RejectionAnalysisRequest(
                            rejection_email="Dear candidate...",
                            application_id=str(app_id),
                        ),
                        response=response,
                        current_user=_user(uid, email),
                        db=db,
                    )
            assert result.analysis_summary == REJECTION_RESULT["analysis_summary"]
        finally:
            async with _NullSessionLocal() as db:
                from sqlalchemy import delete

                await db.execute(delete(JobApplication).where(JobApplication.id == app_id))
                await db.execute(delete(UserWorkflowPreferences).where(UserWorkflowPreferences.user_id == uid))
                await db.execute(delete(User).where(User.id == uid))
                await db.commit()

    @pytest.mark.asyncio
    async def test_reference_request_internal_error(self) -> None:
        uid, email = await _seed_ollama_user()
        try:
            response = Response()
            mock_db = AsyncMock()
            with (
                patch("api.tools._check_rate_limit_and_get_headers", AsyncMock(return_value={})),
                patch("api.tools._check_api_key_available", AsyncMock(return_value=True)),
                patch("api.tools._resolve_llm", AsyncMock(return_value=_ready_llm_ctx())),
                patch("utils.llm_preferences.load_preferred_model", AsyncMock(return_value=None)),
                patch("api.tools.get_cached_tool_result", AsyncMock(return_value=None)),
                patch(
                    "agents.reference_request_writer.ReferenceRequestWriterAgent.generate",
                    AsyncMock(side_effect=RuntimeError("agent fail")),
                ),
            ):
                with pytest.raises(APIError) as exc:
                    await generate_reference_request(
                        request=ReferenceRequestRequest(
                            reference_name="Bob",
                            reference_relationship="Manager",
                        ),
                        response=response,
                        current_user=_user(uid, email),
                        db=mock_db,
                    )
            assert exc.value.status_code == 500
        finally:
            await _delete_user(uid)

    @pytest.mark.asyncio
    async def test_salary_coach_internal_error(self) -> None:
        uid, email = await _seed_ollama_user()
        from api.tools import SalaryCoachRequest

        try:
            response = Response()
            mock_db = AsyncMock()
            with (
                patch("api.tools._check_rate_limit_and_get_headers", AsyncMock(return_value={})),
                patch("api.tools._check_api_key_available", AsyncMock(return_value=True)),
                patch("api.tools._resolve_llm", AsyncMock(return_value=_ready_llm_ctx())),
                patch("utils.llm_preferences.load_preferred_model", AsyncMock(return_value=None)),
                patch("api.tools.get_cached_tool_result", AsyncMock(return_value=None)),
                patch(
                    "agents.salary_coach.SalaryCoachAgent.generate_strategy",
                    AsyncMock(side_effect=RuntimeError("agent fail")),
                ),
            ):
                with pytest.raises(APIError) as exc:
                    await get_salary_coaching(
                        request=SalaryCoachRequest(
                            job_title="Engineer",
                            company_name="Co",
                            offered_salary="$150k",
                        ),
                        response=response,
                        current_user=_user(uid, email),
                        db=mock_db,
                    )
            assert exc.value.status_code == 500
        finally:
            await _delete_user(uid)
