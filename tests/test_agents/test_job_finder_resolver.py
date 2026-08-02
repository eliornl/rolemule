"""Unit tests for Job Finder resolver agent (mocked LLM)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.job_finder_resolver import JobFinderResolverAgent


@pytest.mark.asyncio
async def test_resolve_filters_blocked_hosts():
    agent = JobFinderResolverAgent()
    fake_response = {
        "response": """{
          "company_name": "Acme",
          "candidates": [
            {"url": "https://boards.greenhouse.io/acme", "provider_hint": "greenhouse", "confidence": "high"},
            {"url": "https://www.indeed.com/viewjob?jk=1", "provider_hint": "unknown", "confidence": "low"}
          ],
          "notes": "ok"
        }""",
        "done": True,
    }
    mock_client = MagicMock()
    mock_client.generate = AsyncMock(return_value=fake_response)

    with patch(
        "agents.job_finder_resolver.get_llm_client",
        new=AsyncMock(return_value=mock_client),
    ):
        result = await agent.resolve(
            "Acme",
            user_api_key="test-key",
            llm_provider="gemini",
        )

    assert result["company_name"] == "Acme"
    assert len(result["candidates"]) == 1
    assert "greenhouse.io" in result["candidates"][0]["url"]


@pytest.mark.asyncio
async def test_resolve_empty_company():
    agent = JobFinderResolverAgent()
    result = await agent.resolve("")
    assert result["candidates"] == []
