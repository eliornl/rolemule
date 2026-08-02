"""Unit tests for Job Finder orchestrator state machine."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.job_finder.orchestrator import (
    JobFinderOrchestrator,
    filters_proposal_text,
    seed_filters_from_profile,
)
from utils.job_finder.types import NormalizedJob


@pytest.fixture
def profile() -> dict:
    return {
        "professional_title": "Backend Engineer",
        "city": "Austin",
        "state": "TX",
        "country": "US",
        "work_arrangements": ["remote"],
        "job_types": ["full-time"],
    }


@pytest.fixture
def orchestrator() -> JobFinderOrchestrator:
    orch = JobFinderOrchestrator()
    orch._registry = MagicMock()
    orch._resolver = MagicMock()
    return orch


class TestSeedFilters:
    def test_seed_filters_from_profile(self, profile):
        filters = seed_filters_from_profile(profile)
        assert filters.title == "Backend Engineer"
        assert "Austin" in filters.locations
        assert "remote" in filters.work_arrangements

    def test_filters_proposal_text_includes_title(self, profile):
        filters = seed_filters_from_profile(profile)
        text = filters_proposal_text(filters)
        assert "Backend Engineer" in text


class TestFilterConfirmPhase:
    @pytest.mark.asyncio
    async def test_yes_moves_to_await_company(self, orchestrator, profile):
        filters = seed_filters_from_profile(profile)
        result = await orchestrator.handle_user_message(
            user_text="yes",
            phase="await_filter_confirm",
            confirmed_filters=filters.to_dict(),
            last_listings=[],
            profile=profile,
            user_api_key="key",
            model=None,
            llm_provider="gemini",
        )
        assert result["phase"] == "await_company"
        assert any("company" in m["content"].lower() for m in result["assistant_messages"])


class TestResolveAndListHappyPath:
    @pytest.mark.asyncio
    async def test_company_name_triggers_listings(self, orchestrator, profile):
        filters = seed_filters_from_profile(profile)
        sample_job = NormalizedJob(
            provider="greenhouse",
            external_id="101",
            title="Backend Engineer",
            company="Acme",
            location="Remote",
            url="https://boards.greenhouse.io/acme/jobs/101",
            description_text="Python remote backend services",
        )
        orchestrator._resolver.resolve = AsyncMock(
            return_value={
                "company_name": "Acme",
                "candidates": [
                    {
                        "url": "https://boards.greenhouse.io/acme",
                        "provider_hint": "greenhouse",
                        "confidence": "high",
                    }
                ],
            }
        )
        orchestrator._registry.fetch_jobs = AsyncMock(return_value=[sample_job])
        orchestrator._registry.detect_provider_id = MagicMock(return_value="greenhouse")

        with patch(
            "utils.job_finder.orchestrator.get_cached_job_finder_company",
            AsyncMock(return_value=None),
        ), patch(
            "utils.job_finder.orchestrator.cache_job_finder_company",
            AsyncMock(return_value=True),
        ):
            result = await orchestrator.handle_user_message(
                user_text="Acme",
                phase="await_company",
                confirmed_filters=filters.to_dict(),
                last_listings=[],
                profile=profile,
                user_api_key="key",
                model=None,
                llm_provider="gemini",
            )

        assert result["phase"] == "await_selection"
        assert result["last_listings"]
        assert result["last_board"]["provider"] == "greenhouse"
        picker = next(
            m for m in result["assistant_messages"] if m.get("meta", {}).get("type") == "job_picker"
        )
        assert picker["meta"]["jobs"][0]["title"] == "Backend Engineer"


class TestCareersUrlPaste:
    @pytest.mark.asyncio
    async def test_pasted_careers_url_fetches_directly(self, orchestrator, profile):
        filters = seed_filters_from_profile(profile)
        sample_job = NormalizedJob(
            provider="greenhouse",
            external_id="55",
            title="Staff Engineer",
            company="Acme",
            location="Remote",
            url="https://boards.greenhouse.io/acme/jobs/55",
            description_text="Lead backend architecture",
        )
        orchestrator._registry.fetch_jobs = AsyncMock(return_value=[sample_job])
        orchestrator._registry.detect_provider_id = MagicMock(return_value="greenhouse")

        result = await orchestrator.handle_user_message(
            user_text="https://boards.greenhouse.io/acme",
            phase="await_company",
            confirmed_filters=filters.to_dict(),
            last_listings=[],
            profile=profile,
            user_api_key=None,
            model=None,
            llm_provider=None,
        )

        assert result["phase"] == "await_selection"
        assert len(result["last_listings"]) == 1

    @pytest.mark.asyncio
    async def test_blocked_job_board_url_returns_error(self, orchestrator, profile):
        filters = seed_filters_from_profile(profile)
        result = await orchestrator.handle_user_message(
            user_text="https://www.indeed.com/viewjob?jk=1",
            phase="await_company",
            confirmed_filters=filters.to_dict(),
            last_listings=[],
            profile=profile,
            user_api_key=None,
            model=None,
            llm_provider=None,
        )
        assert result["phase"] == "await_company"
        assert any(m.get("meta", {}).get("type") == "error" for m in result["assistant_messages"])
