"""Golden-style tests for company research disambiguation and caching."""

import pytest
from unittest.mock import AsyncMock, patch

from agents.company_research import CompanyResearchAgent
from utils.cache import _get_company_research_cache_key
from utils.employer_disambiguation import build_company_research_cache_disambiguators


RESEARCH_JSON = '''{
    "company_overview": {"industry": "Healthcare", "company_size": "500-1000"},
    "culture_and_values": {"core_values": []},
    "interview_intelligence": {"typical_process": []},
    "leadership_info": [],
    "competitive_landscape": {"competitors": []},
    "application_insights": {},
    "confidence_assessment": {"overall_confidence": "HIGH"}
}'''

DISAMBIG_JSON = '''{
    "resolved_company_name": "Meridian Health",
    "confidence": "LOW",
    "employer_type": "direct",
    "disambiguation_signals": ["healthcare posting"],
    "rejected_matches": ["Meridian fintech"],
    "notes": "ambiguous"
}'''


def _mock_client():
    client = AsyncMock()

    async def _generate(**kwargs):
        prompt = kwargs.get("prompt", "")
        if "Identify the correct employer" in prompt:
            return {"response": DISAMBIG_JSON, "filtered": False}
        return {"response": RESEARCH_JSON, "filtered": False}

    client.generate.side_effect = _generate
    return client


@pytest.mark.asyncio
async def test_cr03_low_disambiguation_caps_confidence() -> None:
    """Ambiguous Meridian + healthcare context → LOW research quality."""
    agent = CompanyResearchAgent(gemini_client=_mock_client())
    state = {
        "user_api_key": None,
        "job_input_data": {"job_url": "https://jobs.example.com/meridian"},
        "job_analysis": {
            "job_title": "Nurse",
            "company_name": "Meridian",
            "industry": "Healthcare",
            "company_name_confidence": "LOW",
            "responsibilities": ["Patient care"],
        },
    }
    with patch("agents.company_research.get_cached_company_research", return_value=None), \
         patch("agents.company_research.acquire_compute_lock", return_value=True), \
         patch("agents.company_research.release_compute_lock", return_value=None), \
         patch("agents.company_research.cache_company_research", return_value=None):
        result = await agent.process(state)

    cr = result["company_research"]
    assert cr.get("research_quality") == "uncertain"
    assert cr.get("confidence_assessment", {}).get("overall_confidence") == "LOW"


@pytest.mark.asyncio
async def test_cr01_different_domains_different_cache_keys() -> None:
    """Same company name + different Workday slugs → different cache keys."""
    job_analysis = {"industry": "Tech", "job_city": "SF"}
    d1 = build_company_research_cache_disambiguators(
        "Acme",
        job_analysis,
        {"job_url": "https://acme-a.wd5.myworkdayjobs.com/en-US/acme-a/job/x"},
    )
    d2 = build_company_research_cache_disambiguators(
        "Acme",
        job_analysis,
        {"job_url": "https://acme-b.wd5.myworkdayjobs.com/en-US/acme-b/job/x"},
    )
    assert _get_company_research_cache_key("Acme", disambiguators=d1) != _get_company_research_cache_key(
        "Acme", disambiguators=d2
    )


@pytest.mark.asyncio
async def test_staffing_agency_uses_unnamed_path() -> None:
    """Staffing posts use posting-only research without caching by agency name."""
    agent = CompanyResearchAgent(gemini_client=_mock_client())
    state = {
        "user_api_key": None,
        "job_input_data": {},
        "job_analysis": {
            "job_title": "Engineer",
            "company_name": "Randstad",
            "employer_type": "staffing_agency",
            "industry": "Technology",
            "responsibilities": ["Build APIs"],
        },
    }
    with patch("agents.company_research.get_cached_company_research", return_value=None) as mock_get, \
         patch("agents.company_research.acquire_compute_lock", return_value=True), \
         patch("agents.company_research.release_compute_lock", return_value=None), \
         patch("agents.company_research.cache_company_research", return_value=None) as mock_set:
        result = await agent.process(state)

    mock_get.assert_not_called()
    mock_set.assert_not_called()
    assert result["company_research"].get("research_quality") == "posting_only"


@pytest.mark.asyncio
async def test_staffing_post_with_detected_company_researches_agency() -> None:
    """When analyzer omits employer but user/extension named the poster, research that agency."""
    agent = CompanyResearchAgent(gemini_client=_mock_client())
    state = {
        "user_api_key": None,
        "job_input_data": {"detected_company": "Syndesus, Inc."},
        "job_analysis": {
            "job_title": "Senior Backend Engineer",
            "company_name": None,
            "employer_type": "staffing_agency",
            "industry": "Technology",
            "responsibilities": ["Build APIs"],
        },
    }
    with patch("agents.company_research.get_cached_company_research", return_value=None), \
         patch("agents.company_research.acquire_compute_lock", return_value=True), \
         patch("agents.company_research.release_compute_lock", return_value=None), \
         patch("agents.company_research.cache_company_research", return_value=None) as mock_set:
        result = await agent.process(state)

    mock_set.assert_called_once()
    research = result["company_research"]
    assert research.get("research_quality") == "uncertain"
    assert research.get("employer_type") == "staffing_agency"
    assert research.get("industry") == "Healthcare"
