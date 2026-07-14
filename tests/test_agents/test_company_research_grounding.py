"""Unit tests for company research grounding helper behavior."""

from unittest.mock import MagicMock, patch

from agents.company_research import (
    _grounding_hint_for_provider,
    _should_enable_grounding,
)


def test_grounding_hint_gemini_vs_web() -> None:
    gemini = _grounding_hint_for_provider("gemini")
    openai = _grounding_hint_for_provider("openai")
    assert "Google Search" in gemini
    assert "web search" in openai.lower()
    assert "Google Search" not in openai


def test_should_enable_grounding_disabled_for_ollama() -> None:
    with patch(
        "agents.company_research.get_settings",
        return_value=MagicMock(
            company_research_grounding_enabled=True,
            company_research_grounding_min_confidence="MEDIUM",
        ),
    ):
        assert (
            _should_enable_grounding(
                company_name="Acme Corp",
                job_analysis={"company_name_confidence": "LOW"},
                disambiguation_confidence="LOW",
                llm_provider="ollama",
            )
            is False
        )


def test_should_enable_grounding_when_flag_on() -> None:
    with patch(
        "agents.company_research.get_settings",
        return_value=MagicMock(
            company_research_grounding_enabled=True,
            company_research_grounding_min_confidence="MEDIUM",
        ),
    ):
        assert (
            _should_enable_grounding(
                company_name="Acme Corp",
                job_analysis={"company_name_confidence": "LOW"},
                disambiguation_confidence="LOW",
                llm_provider="openai",
            )
            is True
        )
