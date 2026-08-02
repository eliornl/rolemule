"""Unit tests for generic JSON-LD Job Finder extraction."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.test_utils.job_finder_test_helpers import load_fixture
from utils.job_finder.providers.jsonld_generic import (
    JsonLdGenericProvider,
    extract_from_html,
)


class TestExtractFromHtml:
    def test_extracts_job_posting_from_ld_json(self):
        html = load_fixture("jsonld_careers.html")
        jobs = extract_from_html(
            html,
            "https://careers.exampleco.com/open-roles",
            company_name="ExampleCo",
        )
        assert len(jobs) == 1
        job = jobs[0]
        assert job.provider == "jsonld_generic"
        assert job.title == "Site Reliability Engineer"
        assert job.company == "ExampleCo"
        assert "Seattle" in job.location
        assert job.url == "https://careers.exampleco.com/jobs/sre"

    def test_skips_http_job_urls(self):
        html = """
        <script type="application/ld+json">
        {"@type":"JobPosting","title":"Bad","url":"http://insecure.example/j"}
        </script>
        """
        jobs = extract_from_html(html, "https://careers.exampleco.com/")
        assert jobs == []

    def test_deduplicates_same_url(self):
        html = """
        <script type="application/ld+json">
        {"@type":"JobPosting","title":"A","url":"https://careers.exampleco.com/j/1"}
        </script>
        <script type="application/ld+json">
        {"@type":"JobPosting","title":"A duplicate","url":"https://careers.exampleco.com/j/1"}
        </script>
        """
        jobs = extract_from_html(html, "https://careers.exampleco.com/")
        assert len(jobs) == 1


class TestJsonLdGenericProvider:
    def test_detect_always_false(self):
        assert JsonLdGenericProvider().detect("https://careers.exampleco.com/") is False

    @pytest.mark.asyncio
    async def test_fetch_uses_fetch_text(self):
        provider = JsonLdGenericProvider()
        html = load_fixture("jsonld_careers.html")
        with patch(
            "utils.job_finder.providers.jsonld_generic.fetch_text",
            AsyncMock(return_value=html),
        ) as mock_fetch:
            jobs = await provider.fetch(
                "https://careers.exampleco.com/open-roles",
                company_name="ExampleCo",
            )

        mock_fetch.assert_awaited_once()
        assert len(jobs) == 1
        assert jobs[0].title == "Site Reliability Engineer"

    @pytest.mark.asyncio
    async def test_fetch_rejects_non_https(self):
        provider = JsonLdGenericProvider()
        jobs = await provider.fetch("http://careers.exampleco.com/")
        assert jobs == []
