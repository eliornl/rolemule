"""Unit tests for tier-2 Job Finder ATS providers and registry."""

from __future__ import annotations

from typing import List, Optional
from unittest.mock import AsyncMock, patch

import pytest

from tests.test_utils.job_finder_test_helpers import load_fixture
from utils.job_finder.providers.bamboohr import BambooHRProvider
from utils.job_finder.providers.breezy import BreezyProvider
from utils.job_finder.providers.pinpoint import PinpointProvider
from utils.job_finder.providers.recruitee import RecruiteeProvider
from utils.job_finder.providers.rippling import RipplingProvider
from utils.job_finder.providers.teamtailor import TeamtailorProvider
from utils.job_finder.providers.workable import WorkableProvider
from utils.job_finder.registry import ProviderRegistry
from utils.job_finder.types import BlockedHostError, NormalizedJob, UnsupportedCareersPageError


class FakeProvider:
    """Minimal provider for registry integration tests."""

    id = "fake"

    def detect(self, url: str) -> bool:
        return "fake-ats.example.com" in url

    async def fetch(
        self,
        url: str,
        *,
        company_name: Optional[str] = None,
    ) -> List[NormalizedJob]:
        return [
            NormalizedJob(
                provider=self.id,
                external_id="1",
                title="Fake Role",
                company=company_name or "Fake Co",
                location="Remote",
                url="https://fake-ats.example.com/jobs/1",
                description_text="Synthetic listing",
            )
        ]


class TestTeamtailorProvider:
    @pytest.mark.asyncio
    async def test_fetch_from_json_api(self):
        provider = TeamtailorProvider()
        payload = load_fixture("teamtailor_jobs.json")
        with patch(
            "utils.job_finder.providers.teamtailor.fetch_json",
            AsyncMock(return_value=payload),
        ):
            jobs = await provider.fetch(
                "https://acme.teamtailor.com/jobs",
                company_name="Acme",
            )

        assert len(jobs) == 1
        assert jobs[0].provider == "teamtailor"
        assert jobs[0].title == "Product Designer"


class TestRecruiteeProvider:
    @pytest.mark.asyncio
    async def test_fetch_normalizes_offers(self):
        provider = RecruiteeProvider()
        payload = load_fixture("recruitee_jobs.json")
        with patch(
            "utils.job_finder.providers.recruitee.fetch_json",
            AsyncMock(return_value=payload),
        ):
            jobs = await provider.fetch("https://acme.recruitee.com/")

        assert len(jobs) == 1
        assert jobs[0].provider == "recruitee"
        assert jobs[0].title == "Frontend Engineer"


class TestBambooHRProvider:
    @pytest.mark.asyncio
    async def test_fetch_normalizes_list(self):
        provider = BambooHRProvider()
        payload = load_fixture("bamboohr_jobs.json")
        with patch(
            "utils.job_finder.providers.bamboohr.fetch_json",
            AsyncMock(return_value=payload),
        ):
            jobs = await provider.fetch("https://acme.bamboohr.com/careers")

        assert len(jobs) == 1
        assert jobs[0].provider == "bamboohr"
        assert jobs[0].title == "Customer Success Manager"


class TestWorkableProvider:
    @pytest.mark.asyncio
    async def test_fetch_builds_apply_url(self):
        provider = WorkableProvider()
        payload = load_fixture("workable_jobs.json")
        with patch(
            "utils.job_finder.providers.workable.fetch_json",
            AsyncMock(return_value=payload),
        ):
            jobs = await provider.fetch("https://apply.workable.com/acme")

        assert len(jobs) == 1
        assert jobs[0].provider == "workable"
        assert jobs[0].title == "Data Analyst"
        assert "apply.workable.com" in jobs[0].url


class TestBreezyProvider:
    @pytest.mark.asyncio
    async def test_fetch_normalizes_positions(self):
        provider = BreezyProvider()
        payload = load_fixture("breezy_jobs.json")
        with patch(
            "utils.job_finder.providers.breezy.fetch_json",
            AsyncMock(return_value=payload),
        ):
            jobs = await provider.fetch("https://acme.breezy.hr/")

        assert len(jobs) == 1
        assert jobs[0].provider == "breezy"
        assert jobs[0].title == "Mobile Engineer"


class TestPinpointProvider:
    @pytest.mark.asyncio
    async def test_fetch_normalizes_postings(self):
        provider = PinpointProvider()
        payload = load_fixture("pinpoint_jobs.json")
        with patch(
            "utils.job_finder.providers.pinpoint.fetch_json",
            AsyncMock(return_value=payload),
        ):
            jobs = await provider.fetch("https://acme.pinpointhq.com/")

        assert len(jobs) == 1
        assert jobs[0].provider == "pinpoint"
        assert jobs[0].title == "Security Engineer"


class TestRipplingProvider:
    @pytest.mark.asyncio
    async def test_fetch_normalizes_jobs(self):
        provider = RipplingProvider()
        payload = load_fixture("rippling_jobs.json")
        with patch(
            "utils.job_finder.providers.rippling.fetch_json",
            AsyncMock(return_value=payload),
        ):
            jobs = await provider.fetch("https://ats.rippling.com/acme/jobs")

        assert len(jobs) == 1
        assert jobs[0].provider == "rippling"
        assert jobs[0].title == "People Operations Lead"


class TestProviderRegistry:
    @pytest.mark.asyncio
    async def test_register_fake_provider_and_fetch(self):
        registry = ProviderRegistry(providers=[FakeProvider()])
        assert registry.detect_provider_id("https://fake-ats.example.com/board") == "fake"
        jobs = await registry.fetch_jobs("https://fake-ats.example.com/board")
        assert len(jobs) == 1
        assert jobs[0].provider == "fake"

    @pytest.mark.asyncio
    async def test_blocked_host_raises(self):
        registry = ProviderRegistry(providers=[FakeProvider()])
        with pytest.raises(BlockedHostError):
            await registry.fetch_jobs("https://www.indeed.com/viewjob")

    @pytest.mark.asyncio
    async def test_unsupported_url_raises(self):
        registry = ProviderRegistry(providers=[FakeProvider()])
        with pytest.raises(UnsupportedCareersPageError):
            await registry.fetch_jobs("https://careers.unsupported.example.com/")

    @pytest.mark.asyncio
    async def test_empty_detected_board_returns_empty_list(self):
        class EmptyProvider:
            id = "empty"

            def detect(self, url: str) -> bool:
                return True

            async def fetch(self, url: str, *, company_name=None):
                return []

        registry = ProviderRegistry(providers=[EmptyProvider()])
        jobs = await registry.fetch_jobs("https://boards.greenhouse.io/emptyco")
        assert jobs == []
