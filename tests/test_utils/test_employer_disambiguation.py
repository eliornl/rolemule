"""Unit tests for employer disambiguation helpers."""

from utils.employer_disambiguation import (
    build_company_research_cache_disambiguators,
    is_generic_company_name,
    parse_job_url_signals,
    should_skip_disambiguation_step,
)
from utils.cache import _get_company_research_cache_key


def test_lever_url_extracts_slug() -> None:
    signals = parse_job_url_signals("https://jobs.lever.co/notion/abc-123")
    assert signals is not None
    assert signals.ats_platform == "lever"
    assert signals.ats_slug == "notion"


def test_workday_url_extracts_slug() -> None:
    signals = parse_job_url_signals(
        "https://acme.wd5.myworkdayjobs.com/en-US/acme/job/Engineer_123"
    )
    assert signals is not None
    assert signals.ats_platform == "workday"
    assert signals.ats_slug == "acme"


def test_invalid_url_returns_none() -> None:
    assert parse_job_url_signals("javascript:alert(1)") is None
    assert parse_job_url_signals("") is None


def test_generic_name_atlas() -> None:
    assert is_generic_company_name("Atlas") is True


def test_specific_name_datadog() -> None:
    assert is_generic_company_name("Datadog") is False


def test_cache_disambiguators_differ_by_domain() -> None:
    job_analysis = {"industry": "Healthcare", "job_city": "Boston"}
    d1 = build_company_research_cache_disambiguators(
        "Acme",
        job_analysis,
        {"job_url": "https://acme-health.wd5.myworkdayjobs.com/en-US/acme-health/job/x"},
    )
    d2 = build_company_research_cache_disambiguators(
        "Acme",
        job_analysis,
        {"job_url": "https://acme-fintech.wd5.myworkdayjobs.com/en-US/acme-fintech/job/x"},
    )
    key1 = _get_company_research_cache_key("Acme", disambiguators=d1)
    key2 = _get_company_research_cache_key("Acme", disambiguators=d2)
    assert key1 != key2


def test_skip_disambiguation_high_confidence_specific_name() -> None:
    job_analysis = {
        "company_name_confidence": "HIGH",
        "employer_type": "direct",
    }
    disambiguators = {"url_domain": "lever:stripe"}
    assert should_skip_disambiguation_step("Stripe Inc", job_analysis, disambiguators) is True


def test_no_skip_disambiguation_generic_name() -> None:
    job_analysis = {"company_name_confidence": "HIGH", "employer_type": "direct"}
    disambiguators = {"url_domain": ""}
    assert should_skip_disambiguation_step("Atlas", job_analysis, disambiguators) is False
