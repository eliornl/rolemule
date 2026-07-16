"""
Unit tests for the Hiring Outreach Agent.
Mocks LLM client — no network calls.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.hiring_outreach import HiringOutreachAgent, MAX_CONTACTS

# =============================================================================
# FIXTURES
# =============================================================================

SAMPLE_JOB_ANALYSIS = {
    "job_title": "Backend Engineer",
    "company_name": "Acme Corp",
    "required_skills": ["Python", "PostgreSQL"],
    "responsibilities": ["Build APIs", "Own data layer"],
    "job_city": "Remote",
    "industry": "Technology",
}

SAMPLE_COMPANY_RESEARCH = {
    "company_overview": {
        "industry": "Technology",
        "website": "https://acme.example",
        "mission_vision": "Build reliable infrastructure",
    },
    "leadership_info": [
        {"name": "Jane Doe", "title": "VP Engineering"},
    ],
}

SAMPLE_PROFILE_MATCHING = {
    "overall_match_score": 82,
    "key_strengths": ["Python backend experience", "API design"],
    "competitive_positioning": "Strong fit for platform work",
}

SAMPLE_USER_PROFILE = {
    "professional_title": "Software Engineer",
    "years_experience": 8,
    "summary": "Backend engineer focused on scalable services.",
    "skills": ["Python", "PostgreSQL", "Redis"],
}


def _two_contacts_payload() -> str:
    """Valid LLM JSON with two contacts."""
    return json.dumps(
        {
            "summary": "Found two credible public contacts.",
            "contacts": [
                {
                    "name": "Sarah Chen",
                    "role_type": "hiring_manager",
                    "likely_title": "Engineering Manager, Platform",
                    "why_them": "Owns the platform team hiring for this role",
                    "confidence": "high",
                    "evidence": "Listed on company team page",
                    "source_hint": "company website",
                    "short_message": "Hi Sarah, I applied for the Backend Engineer role and would love to connect.",
                    "subject_line": "Backend Engineer application — Acme Corp",
                    "email_body": (
                        "Hi Sarah,\n\n"
                        "I recently applied for the Backend Engineer position at Acme Corp. "
                        "My experience building Python APIs aligns well with the team's needs.\n\n"
                        "Best regards,"
                    ),
                },
                {
                    "name": "Alex Rivera",
                    "role_type": "recruiter",
                    "likely_title": "Technical Recruiter",
                    "why_them": "Handles engineering hiring",
                    "confidence": "medium",
                    "evidence": "Quoted in a company careers blog post",
                    "source_hint": "news",
                    "short_message": "Hi Alex, following up on my Backend Engineer application at Acme Corp.",
                    "subject_line": "Following up — Backend Engineer at Acme Corp",
                    "email_body": (
                        "Hi Alex,\n\n"
                        "I wanted to follow up on my application for the Backend Engineer role.\n\n"
                        "Best regards,"
                    ),
                },
            ],
        }
    )


@pytest.fixture
def mock_gemini_two_contacts():
    """Mock Gemini client returning two valid contacts."""
    client = AsyncMock()
    client.generate.return_value = {
        "response": _two_contacts_payload(),
        "filtered": False,
    }
    return client


@pytest.fixture
def agent_kwargs():
    """Common generate() kwargs for tests."""
    return {
        "job_analysis": SAMPLE_JOB_ANALYSIS,
        "company_research": SAMPLE_COMPANY_RESEARCH,
        "profile_matching": SAMPLE_PROFILE_MATCHING,
        "user_profile": SAMPLE_USER_PROFILE,
    }


# =============================================================================
# HAPPY PATH
# =============================================================================


class TestHiringOutreachHappyPath:
    """Successful generation with mocked LLM."""

    @pytest.mark.asyncio
    async def test_happy_path_two_contacts(self, mock_gemini_two_contacts, agent_kwargs):
        """Two contacts returned with version 1 schema."""
        agent = HiringOutreachAgent()

        with patch(
            "agents.hiring_outreach.get_gemini_client",
            return_value=mock_gemini_two_contacts,
        ):
            result = await agent.generate(**agent_kwargs)

        assert result["version"] == 1
        assert result["company_name"] == "Acme Corp"
        assert result["job_title"] == "Backend Engineer"
        assert len(result["contacts"]) == 2
        assert result["contacts"][0]["name"] == "Sarah Chen"
        assert result["contacts"][0]["confidence"] == "high"
        assert result["contacts"][0]["role_type"] == "hiring_manager"
        assert result["fallback"]["used"] is False
        assert result["grounding_used"] is True
        datetime.fromisoformat(result["generated_at"].replace("Z", "+00:00"))

    @pytest.mark.asyncio
    async def test_grounding_flag_passed_when_enabled(
        self, mock_gemini_two_contacts, agent_kwargs
    ):
        """Gemini provider with grounding enabled passes use_google_search_grounding=True."""
        agent = HiringOutreachAgent()

        with patch(
            "agents.hiring_outreach.get_gemini_client",
            return_value=mock_gemini_two_contacts,
        ), patch(
            "agents.hiring_outreach.get_settings",
            return_value=MagicMock(hiring_outreach_grounding_enabled=True),
        ):
            await agent.generate(**agent_kwargs, llm_provider="gemini")

        call_kwargs = mock_gemini_two_contacts.generate.call_args[1]
        assert call_kwargs.get("use_google_search_grounding") is True


# =============================================================================
# ERROR / DEGRADED PATHS
# =============================================================================


class TestHiringOutreachDegradedPaths:
    """Fallback and degraded behavior."""

    @pytest.mark.asyncio
    async def test_invalid_json_uses_fallback(self, agent_kwargs):
        """Non-JSON LLM response triggers fallback without raising."""
        client = AsyncMock()
        client.generate.return_value = {
            "response": "Here are some contacts you could try...",
            "filtered": False,
        }
        agent = HiringOutreachAgent()

        with patch("agents.hiring_outreach.get_gemini_client", return_value=client):
            result = await agent.generate(**agent_kwargs)

        assert result["version"] == 1
        assert result["contacts"] == []
        assert result["fallback"]["used"] is True
        assert result["fallback"]["subject_line"]
        assert result["fallback"]["email_body"]
        assert "Best regards," in result["fallback"]["email_body"]

    @pytest.mark.asyncio
    async def test_missing_company_degraded(self, agent_kwargs):
        """Missing company name yields degraded summary and Unknown employer label."""
        client = AsyncMock()
        client.generate.return_value = {
            "response": json.dumps({"summary": "Limited context.", "contacts": []}),
            "filtered": False,
        }
        agent = HiringOutreachAgent()
        kwargs = {**agent_kwargs, "job_analysis": {**SAMPLE_JOB_ANALYSIS, "company_name": "Unknown"}}

        with patch("agents.hiring_outreach.get_gemini_client", return_value=client):
            result = await agent.generate(**kwargs)

        assert result["company_name"] == "Unknown employer"
        assert "missing" in result["summary"].lower() or "unclear" in result["summary"].lower()
        assert result["fallback"]["used"] is True
        call_kwargs = client.generate.call_args[1]
        assert call_kwargs.get("use_google_search_grounding") is False

    @pytest.mark.asyncio
    async def test_empty_contacts_populates_fallback(self, agent_kwargs):
        """Empty contacts array sets fallback drafts."""
        client = AsyncMock()
        client.generate.return_value = {
            "response": json.dumps({"summary": "No public contacts found.", "contacts": []}),
            "filtered": False,
        }
        agent = HiringOutreachAgent()

        with patch("agents.hiring_outreach.get_gemini_client", return_value=client):
            result = await agent.generate(**agent_kwargs)

        assert result["contacts"] == []
        assert result["fallback"]["used"] is True
        assert "Acme Corp" in result["fallback"]["subject_line"]


# =============================================================================
# GROUNDING GATES
# =============================================================================


class TestHiringOutreachGrounding:
    """Grounding disabled for ollama and when setting is off."""

    @pytest.mark.asyncio
    async def test_ollama_disables_grounding(self, mock_gemini_two_contacts, agent_kwargs):
        """Ollama provider must not enable web search grounding."""
        agent = HiringOutreachAgent()

        with patch(
            "agents.hiring_outreach.get_gemini_client",
            return_value=mock_gemini_two_contacts,
        ), patch(
            "agents.hiring_outreach.get_settings",
            return_value=MagicMock(hiring_outreach_grounding_enabled=True),
        ):
            result = await agent.generate(**agent_kwargs, llm_provider="ollama")

        call_kwargs = mock_gemini_two_contacts.generate.call_args[1]
        assert call_kwargs.get("use_google_search_grounding") is False
        assert result["grounding_used"] is False

    @pytest.mark.asyncio
    async def test_grounding_setting_off(self, mock_gemini_two_contacts, agent_kwargs):
        """When hiring_outreach_grounding_enabled is False, grounding stays off."""
        agent = HiringOutreachAgent()

        with patch(
            "agents.hiring_outreach.get_gemini_client",
            return_value=mock_gemini_two_contacts,
        ), patch(
            "agents.hiring_outreach.get_settings",
            return_value=MagicMock(hiring_outreach_grounding_enabled=False),
        ):
            result = await agent.generate(**agent_kwargs, llm_provider="gemini")

        call_kwargs = mock_gemini_two_contacts.generate.call_args[1]
        assert call_kwargs.get("use_google_search_grounding") is False
        assert result["grounding_used"] is False

    @pytest.mark.asyncio
    async def test_grounding_failover_retries_without_grounding(self, agent_kwargs):
        """Grounding failure retries once with use_google_search_grounding=False."""
        client = AsyncMock()
        client.generate.side_effect = [
            RuntimeError("Grounding unavailable"),
            {"response": _two_contacts_payload(), "filtered": False},
        ]
        agent = HiringOutreachAgent()

        with patch(
            "agents.hiring_outreach.get_gemini_client",
            return_value=client,
        ), patch(
            "agents.hiring_outreach.get_settings",
            return_value=MagicMock(hiring_outreach_grounding_enabled=True),
        ):
            result = await agent.generate(**agent_kwargs, llm_provider="gemini")

        assert client.generate.call_count == 2
        first_kwargs = client.generate.call_args_list[0][1]
        second_kwargs = client.generate.call_args_list[1][1]
        assert first_kwargs.get("use_google_search_grounding") is True
        assert second_kwargs.get("use_google_search_grounding") is False
        assert result["grounding_used"] is False
        assert len(result["contacts"]) == 2


# =============================================================================
# POST-PROCESSING
# =============================================================================


class TestHiringOutreachPostProcessing:
    """LinkedIn strip, placeholder cleanup, contact clamping."""

    @pytest.mark.asyncio
    async def test_linkedin_url_stripped(self, agent_kwargs):
        """linkedin.com URLs are removed from stored string fields."""
        linkedin_url = "https://www.linkedin.com/in/sarah-chen"
        payload = json.dumps(
            {
                "summary": f"Found via {linkedin_url} and team page.",
                "contacts": [
                    {
                        "name": "Sarah Chen",
                        "role_type": "hiring_manager",
                        "likely_title": "Engineering Manager",
                        "why_them": "Team lead",
                        "confidence": "high",
                        "evidence": f"Profile at {linkedin_url}",
                        "source_hint": "company website",
                        "short_message": f"See {linkedin_url} for context.",
                        "subject_line": "Hello",
                        "email_body": f"Reference: {linkedin_url}\n\nBest regards,",
                    }
                ],
            }
        )
        client = AsyncMock()
        client.generate.return_value = {"response": payload, "filtered": False}
        agent = HiringOutreachAgent()

        with patch("agents.hiring_outreach.get_gemini_client", return_value=client):
            result = await agent.generate(**agent_kwargs)

        combined = json.dumps(result)
        assert "linkedin.com" not in combined.lower()
        assert "lnkd.in" not in combined.lower()

    @pytest.mark.asyncio
    async def test_bracket_placeholders_cleaned(self, agent_kwargs):
        """[Your Name] and similar bracket placeholders are stripped."""
        payload = json.dumps(
            {
                "summary": "Drafts need cleanup.",
                "contacts": [
                    {
                        "name": "Sarah Chen",
                        "role_type": "recruiter",
                        "likely_title": "Recruiter",
                        "why_them": "Hiring contact",
                        "confidence": "medium",
                        "evidence": "Public listing",
                        "source_hint": "news",
                        "short_message": "Hi Sarah from [Your Name]",
                        "subject_line": "[Company] Backend role",
                        "email_body": "Hi Sarah,\n\nRegards,\n[Your Name]",
                    }
                ],
            }
        )
        client = AsyncMock()
        client.generate.return_value = {"response": payload, "filtered": False}
        agent = HiringOutreachAgent()

        with patch("agents.hiring_outreach.get_gemini_client", return_value=client):
            result = await agent.generate(**agent_kwargs)

        contact = result["contacts"][0]
        assert "[Your Name]" not in contact["short_message"]
        assert "[Your Name]" not in contact["email_body"]
        assert "[Company]" not in contact["subject_line"]

    @pytest.mark.asyncio
    async def test_more_than_four_contacts_truncated(self, agent_kwargs):
        """LLM returning >4 contacts is clamped to MAX_CONTACTS."""
        contacts = []
        for i in range(6):
            contacts.append(
                {
                    "name": f"Person {i}",
                    "role_type": "generic",
                    "likely_title": "Staff",
                    "why_them": "Might be relevant",
                    "confidence": "low",
                    "evidence": "Public mention",
                    "source_hint": "other_public",
                    "short_message": f"Note {i}",
                    "subject_line": f"Subject {i}",
                    "email_body": f"Body {i}\n\nBest regards,",
                }
            )
        client = AsyncMock()
        client.generate.return_value = {
            "response": json.dumps({"summary": "Many guesses.", "contacts": contacts}),
            "filtered": False,
        }
        agent = HiringOutreachAgent()

        with patch("agents.hiring_outreach.get_gemini_client", return_value=client):
            result = await agent.generate(**agent_kwargs)

        assert len(result["contacts"]) == MAX_CONTACTS
        assert MAX_CONTACTS == 4

    @pytest.mark.asyncio
    async def test_confidence_normalized(self, agent_kwargs):
        """Confidence values are normalized to high|medium|low."""
        payload = json.dumps(
            {
                "summary": "Mixed confidence labels.",
                "contacts": [
                    {
                        "name": "A",
                        "role_type": "generic",
                        "likely_title": "T",
                        "why_them": "W",
                        "confidence": "HIGH",
                        "evidence": "E",
                        "source_hint": "news",
                        "short_message": "S",
                        "subject_line": "Sub",
                        "email_body": "Body",
                    },
                    {
                        "name": "B",
                        "role_type": "generic",
                        "likely_title": "T",
                        "why_them": "W",
                        "confidence": "moderate",
                        "evidence": "E",
                        "source_hint": "news",
                        "short_message": "S",
                        "subject_line": "Sub",
                        "email_body": "Body",
                    },
                ],
            }
        )
        client = AsyncMock()
        client.generate.return_value = {"response": payload, "filtered": False}
        agent = HiringOutreachAgent()

        with patch("agents.hiring_outreach.get_gemini_client", return_value=client):
            result = await agent.generate(**agent_kwargs)

        assert result["contacts"][0]["confidence"] == "high"
        assert result["contacts"][1]["confidence"] == "medium"


# =============================================================================
# Helper unit tests (coverage for normalize / sanitize edge paths)
# =============================================================================


class TestHiringOutreachHelpers:
    def test_strip_and_reject_empty_and_non_string(self):
        from agents.hiring_outreach import (
            _reject_placeholders,
            _sanitize_string_field,
            _strip_linkedin_urls,
        )

        assert _strip_linkedin_urls("") == ""
        assert _reject_placeholders("") == ""
        assert _sanitize_string_field(None) is None
        assert _sanitize_string_field(12) == 12

    def test_normalize_confidence_aliases(self):
        from agents.hiring_outreach import _normalize_confidence

        assert _normalize_confidence(None) == "low"
        assert _normalize_confidence("") == "low"
        assert _normalize_confidence("HIGH") == "high"
        assert _normalize_confidence("h") == "high"
        assert _normalize_confidence("strong") == "high"
        assert _normalize_confidence("m") == "medium"
        assert _normalize_confidence("moderate") == "medium"
        assert _normalize_confidence("unknown") == "low"

    def test_normalize_role_and_source_aliases(self):
        from agents.hiring_outreach import _normalize_role_type, _normalize_source_hint

        assert _normalize_role_type(None) == "generic"
        assert _normalize_role_type("") == "generic"
        assert _normalize_role_type("Hiring Manager") == "hiring_manager"
        assert _normalize_role_type("talent-recruiter") == "recruiter"
        assert _normalize_role_type("team peer engineer") == "team_peer"
        assert _normalize_role_type("something else") == "generic"

        assert _normalize_source_hint(None) == "other_public"
        assert _normalize_source_hint("") == "other_public"
        assert _normalize_source_hint("Press release") == "news"
        assert _normalize_source_hint("Company Website") == "company website"
        assert _normalize_source_hint("blog") == "other_public"
