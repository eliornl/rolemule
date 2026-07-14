"""
Direct-handler coverage for remaining api/tools.py gaps.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from starlette.responses import Response

from api.tools import compare_jobs, get_followup_stages, get_salary_coaching
from models.database import AuthMethod, User, UserProfile
from tests.test_api.conftest import _NullSessionLocal
from tests.test_api.test_career_tools import (
    JOB_COMPARISON_RESULT,
    SALARY_RESULT,
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
