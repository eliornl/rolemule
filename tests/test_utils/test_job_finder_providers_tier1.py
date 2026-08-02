"""Unit tests for tier-1 Job Finder ATS providers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.test_utils.job_finder_test_helpers import load_fixture
from utils.job_finder.providers.ashby import AshbyProvider
from utils.job_finder.providers.greenhouse import GreenhouseProvider
from utils.job_finder.providers.lever import LeverProvider
from utils.job_finder.providers.smartrecruiters import SmartRecruitersProvider
from utils.job_finder.providers.workday import WorkdayProvider


class TestGreenhouseProvider:
    def test_detect_and_board_token(self):
        provider = GreenhouseProvider()
        url = "https://boards.greenhouse.io/acme"
        assert provider.detect(url)
        assert provider._board_token(url) == "acme"

    @pytest.mark.asyncio
    async def test_fetch_normalizes_jobs(self):
        provider = GreenhouseProvider()
        payload = load_fixture("greenhouse_jobs.json")
        with patch(
            "utils.job_finder.providers.greenhouse.fetch_json",
            AsyncMock(return_value=payload),
        ) as mock_fetch:
            jobs = await provider.fetch("https://boards.greenhouse.io/acme")

        mock_fetch.assert_awaited_once()
        assert len(jobs) == 1
        job = jobs[0]
        assert job.provider == "greenhouse"
        assert job.title == "Software Engineer"
        assert job.company == "Acme"
        assert job.location == "Remote"
        assert job.url.startswith("https://")
        assert "Python" in (job.description_text or "")


class TestAshbyProvider:
    def test_detect(self):
        assert AshbyProvider().detect("https://jobs.ashbyhq.com/acme")

    @pytest.mark.asyncio
    async def test_fetch_normalizes_jobs(self):
        provider = AshbyProvider()
        payload = load_fixture("ashby_jobs.json")
        with patch(
            "utils.job_finder.providers.ashby.fetch_json",
            AsyncMock(return_value=payload),
        ):
            jobs = await provider.fetch(
                "https://jobs.ashbyhq.com/acme",
                company_name="Acme",
            )

        assert len(jobs) == 1
        assert jobs[0].provider == "ashby"
        assert jobs[0].title == "Backend Engineer"
        assert jobs[0].company == "Acme"
        assert "ashbyhq.com" in jobs[0].url


class TestLeverProvider:
    def test_detect(self):
        assert LeverProvider().detect("https://jobs.lever.co/acme")

    @pytest.mark.asyncio
    async def test_fetch_normalizes_jobs(self):
        provider = LeverProvider()
        payload = load_fixture("lever_jobs.json")
        with patch(
            "utils.job_finder.providers.lever.fetch_json",
            AsyncMock(return_value=payload),
        ):
            jobs = await provider.fetch("https://jobs.lever.co/acme")

        assert len(jobs) == 1
        assert jobs[0].provider == "lever"
        assert jobs[0].title == "Software Engineer"
        assert jobs[0].location == "San Francisco, CA"


class TestWorkdayProvider:
    def test_detect(self):
        url = "https://acme.wd5.myworkdayjobs.com/en-US/External"
        assert WorkdayProvider().detect(url)

    def test_parse_tenant_site(self):
        provider = WorkdayProvider()
        host, tenant, site = provider._parse_tenant_site(
            "https://acme.wd5.myworkdayjobs.com/en-US/External"
        )
        assert host == "acme.wd5.myworkdayjobs.com"
        assert tenant == "acme"
        assert site == "External"

    @pytest.mark.asyncio
    async def test_fetch_posts_to_cxs_endpoint(self):
        provider = WorkdayProvider()
        payload = load_fixture("workday_jobs.json")
        mock_fetch = AsyncMock(return_value=payload)
        with patch(
            "utils.job_finder.providers.workday.fetch_json",
            mock_fetch,
        ):
            jobs = await provider.fetch(
                "https://acme.wd5.myworkdayjobs.com/en-US/External",
                company_name="Acme",
            )

        assert mock_fetch.await_args.kwargs["method"] == "POST"
        assert len(jobs) == 1
        assert jobs[0].provider == "workday"
        assert jobs[0].title == "Platform Engineer"
        assert jobs[0].url.startswith("https://acme.wd5.myworkdayjobs.com/")


class TestSmartRecruitersProvider:
    def test_detect(self):
        assert SmartRecruitersProvider().detect(
            "https://jobs.smartrecruiters.com/AcmeCorp"
        )

    @pytest.mark.asyncio
    async def test_fetch_normalizes_jobs(self):
        provider = SmartRecruitersProvider()
        payload = load_fixture("smartrecruiters_jobs.json")
        with patch(
            "utils.job_finder.providers.smartrecruiters.fetch_json",
            AsyncMock(return_value=payload),
        ):
            jobs = await provider.fetch(
                "https://jobs.smartrecruiters.com/AcmeCorp",
                company_name="Acme Corp",
            )

        assert len(jobs) == 1
        assert jobs[0].provider == "smartrecruiters"
        assert jobs[0].title == "DevOps Engineer"
        assert "Austin" in jobs[0].location
