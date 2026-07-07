"""
Unit tests for the Company Research Agent.
Tests company research with mocked LLM and Redis responses.
"""

import pytest
from unittest.mock import AsyncMock, patch
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from agents.company_research import CompanyResearchAgent


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def create_test_workflow_state(
    user_id: str = "test-user-123",
    session_id: str = "test-session-456",
    job_analysis: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Create a workflow state dict for testing."""
    return {
        "user_id": user_id,
        "session_id": session_id,
        "user_profile": {"full_name": "Test User"},
        "user_api_key": None,
        "job_input_data": {"input_method": "manual"},
        "job_analysis": job_analysis,
        "company_research": None,
        "profile_matching": None,
        "resume_recommendations": None,
        "cover_letter": None,
        "current_phase": "company_research",
        "workflow_status": "running",
        "processing_start_time": datetime.now(timezone.utc).isoformat(),
        "processing_end_time": None,
        "agent_status": {},
        "completed_agents": ["job_analyzer"],
        "failed_agents": [],
        "current_agent": "company_research",
        "error_messages": [],
        "warning_messages": [],
        "agent_start_times": {},
    }


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_gemini_client():
    """Create a mock Gemini client that returns valid company research JSON."""
    client = AsyncMock()
    client.generate.return_value = {
        "response": '''{
            "company_overview": {
                "company_size": "10,000-50,000 employees",
                "industry": "Technology",
                "headquarters": "San Francisco, CA",
                "founded_year": 2010,
                "website": "https://techcorp.com"
            },
            "culture_and_values": {
                "core_values": ["Innovation", "Integrity", "Customer Focus"],
                "work_environment": "Fast-paced, collaborative"
            },
            "interview_intelligence": {
                "typical_process": ["Phone screen", "Technical interview", "Onsite"],
                "timeline": "2-4 weeks"
            },
            "leadership_info": [{"name": "Jane Smith", "title": "CEO"}],
            "competitive_landscape": {
                "competitors": ["Amazon", "Microsoft"],
                "market_position": "Top 3 in cloud computing"
            },
            "recent_news": [{"title": "TechCorp launches new AI platform"}],
            "application_insights": {
                "what_to_emphasize": ["Technical skills", "Innovation mindset"]
            },
            "confidence_assessment": {
                "overall_confidence": "HIGH"
            }
        }''',
        "filtered": False,
    }
    return client


@pytest.fixture
def expected_research_result():
    """Expected structure after CompanyResearchResult.to_dict()."""
    return {
        "company_size": "10,000-50,000 employees",
        "industry": "Technology",
        "headquarters": "San Francisco, CA",
        "founded_year": 2010,
        "website": "https://techcorp.com",
        "core_values": ["Innovation", "Integrity", "Customer Focus"],
        "work_environment": "Fast-paced, collaborative",
    }


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client."""
    client = AsyncMock()
    client.get.return_value = None  # No cache by default
    client.set.return_value = True
    return client


@pytest.fixture
def workflow_state_with_job_analysis():
    """Create workflow state with completed job analysis."""
    return create_test_workflow_state(
        job_analysis={
            "job_title": "Software Engineer",
            "company_name": "TechCorp Inc",
        }
    )


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================


class TestCompanyResearchInit:
    """Tests for CompanyResearchAgent initialization."""

    def test_init_with_valid_gemini_client(self, mock_gemini_client):
        """Test successful initialization with valid Gemini client."""
        agent = CompanyResearchAgent(gemini_client=mock_gemini_client)
        assert agent.gemini_client is mock_gemini_client

    def test_init_redis_client_deprecated_but_accepted(self, mock_gemini_client, mock_redis_client):
        """redis_client is accepted for backward compat but not stored (caching moved to utils/cache.py)."""
        # Should not raise even with redis_client provided
        agent = CompanyResearchAgent(
            gemini_client=mock_gemini_client,
            redis_client=mock_redis_client,
        )
        assert agent.gemini_client is mock_gemini_client

    def test_init_with_none_gemini_raises_error(self, mock_redis_client):
        """Test that None Gemini client raises TypeError."""
        with pytest.raises(TypeError, match="gemini_client cannot be None"):
            CompanyResearchAgent(
                gemini_client=None,
                redis_client=mock_redis_client,
            )

    def test_init_without_redis_client(self, mock_gemini_client):
        """Test that omitting Redis client is allowed (caching via utils/cache.py)."""
        agent = CompanyResearchAgent(gemini_client=mock_gemini_client)
        assert agent.gemini_client is mock_gemini_client


# =============================================================================
# PROCESSING TESTS
# =============================================================================


_CACHE_PATCHES = dict(
    get_cached=patch("agents.company_research.get_cached_company_research", return_value=None),
    acquire=patch("agents.company_research.acquire_compute_lock", return_value=True),
    release=patch("agents.company_research.release_compute_lock", return_value=None),
    write=patch("agents.company_research.cache_company_research", return_value=None),
)


class TestCompanyResearchProcessing:
    """Tests for company research processing."""

    @pytest.mark.asyncio
    async def test_process_success(
        self, mock_gemini_client, workflow_state_with_job_analysis
    ):
        """Test successful company research processing."""
        agent = CompanyResearchAgent(gemini_client=mock_gemini_client)

        with patch("agents.company_research.get_cached_company_research", return_value=None), \
             patch("agents.company_research.acquire_compute_lock", return_value=True), \
             patch("agents.company_research.release_compute_lock", return_value=None), \
             patch("agents.company_research.cache_company_research", return_value=None):
            result = await agent.process(workflow_state_with_job_analysis)

        assert "company_research" in result
        assert result["company_research"]["industry"] == "Technology"

    @pytest.mark.asyncio
    async def test_process_missing_job_analysis_raises_error(self, mock_gemini_client):
        """Test that missing job analysis raises error."""
        agent = CompanyResearchAgent(gemini_client=mock_gemini_client)
        state = create_test_workflow_state(job_analysis=None)

        with pytest.raises(ValueError, match="[Jj]ob analysis|required"):
            await agent.process(state)

    @pytest.mark.asyncio
    async def test_process_missing_company_name_uses_unnamed_employer_flow(
        self, mock_gemini_client
    ):
        """When the posting omits the employer (founding/confidential), research still runs on job context."""
        agent = CompanyResearchAgent(gemini_client=mock_gemini_client)
        state = create_test_workflow_state(
            job_analysis={
                "job_title": "AI Engineer (Founding Team)",
                "company_name": "",
                "industry": "Technology",
                "responsibilities": ["Build ML pipelines"],
            }
        )

        with patch("agents.company_research.get_cached_company_research", return_value=None), \
             patch("agents.company_research.acquire_compute_lock", return_value=True), \
             patch("agents.company_research.release_compute_lock", return_value=None), \
             patch("agents.company_research.cache_company_research", return_value=None):
            result = await agent.process(state)

        assert "company_research" in result
        assert result["company_research"]["industry"] == "Technology"
        mock_gemini_client.generate.assert_called()


# =============================================================================
# CACHING TESTS
# =============================================================================


class TestCompanyResearchCaching:
    """Tests for company research caching via utils/cache.py helpers."""

    @pytest.mark.asyncio
    async def test_returns_cached_result_when_available(
        self, mock_gemini_client, workflow_state_with_job_analysis
    ):
        """Test that cached results are returned when available (via get_cached_company_research)."""
        cached_data = {"industry": "Cached Industry", "company_size": "1000+"}

        agent = CompanyResearchAgent(gemini_client=mock_gemini_client)

        with patch(
            "agents.company_research.get_cached_company_research",
            return_value=cached_data,
        ):
            result = await agent.process(workflow_state_with_job_analysis)

        # Should use cached result — LLM should not be called
        assert result["company_research"]["industry"] == "Cached Industry"
        mock_gemini_client.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_caches_result_after_fresh_research(
        self, mock_gemini_client, workflow_state_with_job_analysis
    ):
        """Test that results are written to cache after fresh research."""
        agent = CompanyResearchAgent(gemini_client=mock_gemini_client)

        with patch(
            "agents.company_research.get_cached_company_research", return_value=None
        ), patch(
            "agents.company_research.cache_company_research"
        ) as mock_cache_write, patch(
            "agents.company_research.acquire_compute_lock", return_value=True
        ), patch(
            "agents.company_research.release_compute_lock", return_value=None
        ):
            await agent.process(workflow_state_with_job_analysis)

        mock_cache_write.assert_called()

    @pytest.mark.asyncio
    async def test_fresh_research_when_no_cache(
        self, mock_gemini_client, workflow_state_with_job_analysis
    ):
        """LLM should be called when there is no cached result."""
        agent = CompanyResearchAgent(gemini_client=mock_gemini_client)

        with patch(
            "agents.company_research.get_cached_company_research", return_value=None
        ), patch(
            "agents.company_research.acquire_compute_lock", return_value=True
        ), patch(
            "agents.company_research.release_compute_lock", return_value=None
        ), patch(
            "agents.company_research.cache_company_research", return_value=None
        ):
            result = await agent.process(workflow_state_with_job_analysis)

        assert "company_research" in result
        mock_gemini_client.generate.assert_called_once()


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_handles_llm_filtered_response(self, workflow_state_with_job_analysis):
        """Test handling of filtered LLM response — returns fallback, does not raise."""
        mock_gemini = AsyncMock()
        mock_gemini.generate.return_value = {
            "response": "Content filtered",
            "filtered": True,
        }

        agent = CompanyResearchAgent(gemini_client=mock_gemini)

        with patch("agents.company_research.get_cached_company_research", return_value=None), \
             patch("agents.company_research.acquire_compute_lock", return_value=True), \
             patch("agents.company_research.release_compute_lock", return_value=None), \
             patch("agents.company_research.cache_company_research", return_value=None):
            result = await agent.process(workflow_state_with_job_analysis)

        assert "company_research" in result

    @pytest.mark.asyncio
    async def test_handles_invalid_json_response(self, workflow_state_with_job_analysis):
        """Test handling of invalid JSON from LLM — returns fallback, does not raise."""
        mock_gemini = AsyncMock()
        mock_gemini.generate.return_value = {
            "response": "This is not valid JSON at all",
            "filtered": False,
        }

        agent = CompanyResearchAgent(gemini_client=mock_gemini)

        with patch("agents.company_research.get_cached_company_research", return_value=None), \
             patch("agents.company_research.acquire_compute_lock", return_value=True), \
             patch("agents.company_research.release_compute_lock", return_value=None), \
             patch("agents.company_research.cache_company_research", return_value=None):
            result = await agent.process(workflow_state_with_job_analysis)

        assert "company_research" in result


# =============================================================================
# ADDITIONAL COVERAGE — LLM CALL COUNT, EXCEPTION PROPAGATION, STALE CACHE
# =============================================================================


class TestCompanyResearchAdditional:
    """Additional coverage for edge cases not in the base tests."""

    @pytest.mark.asyncio
    async def test_llm_exception_returns_fallback(
        self, mock_redis_client, workflow_state_with_job_analysis
    ):
        """LLM exception is caught internally and returns a fallback result (not re-raised)."""
        failing_client = AsyncMock()
        failing_client.generate.side_effect = RuntimeError("LLM down")

        agent = CompanyResearchAgent(
            gemini_client=failing_client,
            redis_client=mock_redis_client,
        )

        with patch(
            "agents.company_research.get_cached_company_research", return_value=None
        ), patch(
            "agents.company_research.acquire_compute_lock", return_value=True
        ), patch(
            "agents.company_research.release_compute_lock", return_value=None
        ):
            result = await agent.process(workflow_state_with_job_analysis)

        # company_research catches and returns fallback — should not raise
        assert "company_research" in result

    @pytest.mark.asyncio
    async def test_llm_called_exactly_once_on_cache_miss(
        self, mock_gemini_client, mock_redis_client, workflow_state_with_job_analysis
    ):
        """LLM should be called exactly once when there is no cached result."""
        agent = CompanyResearchAgent(
            gemini_client=mock_gemini_client,
            redis_client=mock_redis_client,
        )

        await agent.process(workflow_state_with_job_analysis)

        assert mock_gemini_client.generate.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_miss_triggers_fresh_research(
        self, mock_gemini_client, workflow_state_with_job_analysis
    ):
        """When get_cached_company_research returns None, LLM is called for fresh data."""
        agent = CompanyResearchAgent(gemini_client=mock_gemini_client)

        with patch(
            "agents.company_research.get_cached_company_research", return_value=None
        ), patch(
            "agents.company_research.acquire_compute_lock", return_value=True
        ), patch(
            "agents.company_research.release_compute_lock", return_value=None
        ), patch(
            "agents.company_research.cache_company_research", return_value=None
        ):
            result = await agent.process(workflow_state_with_job_analysis)

        assert result["company_research"]["industry"] == "Technology"
        mock_gemini_client.generate.assert_called_once()


class TestCompanyResearchHelpersAndEdges:
    """Cover stampede wait, placeholder names, and timeout propagation."""

    def test_has_usable_company_name_rejects_dashes_and_placeholders(self):
        from agents.company_research import (
            _format_job_context_for_unnamed_employer,
            _has_usable_company_name,
        )

        assert _has_usable_company_name("---") is False
        assert _has_usable_company_name("unknown") is False
        ctx = _format_job_context_for_unnamed_employer(
            {
                "job_title": "Founding Engineer",
                "team_info": "Small platform team building core APIs",
                "responsibilities": ["Ship features"],
            }
        )
        assert "Team / role context" in ctx

    @pytest.mark.asyncio
    async def test_stampede_lock_wait_returns_cached(
        self, mock_gemini_client, workflow_state_with_job_analysis
    ):
        agent = CompanyResearchAgent(gemini_client=mock_gemini_client)
        cached_data = {"industry": "Wait Cached", "company_size": "500+"}

        async def _lookup(*args, **kwargs):
            _lookup.calls += 1
            if _lookup.calls >= 2:
                return cached_data
            return None

        _lookup.calls = 0

        with patch(
            "agents.company_research.get_cached_company_research", side_effect=_lookup
        ), patch(
            "agents.company_research.acquire_compute_lock", AsyncMock(return_value=False)
        ), patch(
            "agents.company_research.release_compute_lock", AsyncMock()
        ), patch(
            "agents.company_research.asyncio.sleep", AsyncMock()
        ):
            result = await agent.process(workflow_state_with_job_analysis)

        assert result["company_research"]["industry"] == "Wait Cached"
        mock_gemini_client.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_stampede_lock_wait_timeout_computes(
        self, mock_gemini_client, workflow_state_with_job_analysis
    ):
        agent = CompanyResearchAgent(gemini_client=mock_gemini_client)

        with patch(
            "agents.company_research.get_cached_company_research", AsyncMock(return_value=None)
        ), patch(
            "agents.company_research.acquire_compute_lock", AsyncMock(return_value=False)
        ), patch(
            "agents.company_research.release_compute_lock", AsyncMock()
        ), patch(
            "agents.company_research.cache_company_research", AsyncMock()
        ), patch(
            "agents.company_research.asyncio.sleep", AsyncMock()
        ):
            result = await agent.process(workflow_state_with_job_analysis)

        assert result["company_research"]["industry"] == "Technology"
        mock_gemini_client.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_timeout_propagates(
        self, mock_gemini_client, workflow_state_with_job_analysis
    ):
        agent = CompanyResearchAgent(gemini_client=mock_gemini_client)

        with patch(
            "agents.company_research.get_cached_company_research",
            AsyncMock(side_effect=asyncio.TimeoutError()),
        ):
            with pytest.raises(asyncio.TimeoutError):
                await agent.process(workflow_state_with_job_analysis)
