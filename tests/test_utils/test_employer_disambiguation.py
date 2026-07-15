"""Unit tests for employer disambiguation helpers."""

from utils.employer_disambiguation import (
    build_company_research_cache_disambiguators,
    build_primary_location,
    format_url_signals_block,
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


def test_greenhouse_url_extracts_slug() -> None:
    signals = parse_job_url_signals("https://boards.greenhouse.io/acme/jobs/123")
    assert signals is not None
    assert signals.ats_platform == "greenhouse"
    assert signals.ats_slug == "acme"


def test_ashby_url_extracts_slug() -> None:
    signals = parse_job_url_signals("https://jobs.ashbyhq.com/acme/abc")
    assert signals is not None
    assert signals.ats_platform == "ashby"
    assert signals.ats_slug == "acme"


def test_build_primary_location_with_extras() -> None:
    job_analysis = {
        "job_city": "Boston",
        "job_state": "MA",
        "job_country": "US",
        "additional_locations": ["Remote", "NYC"],
    }
    loc = build_primary_location(job_analysis)
    assert "Boston" in loc
    assert "Remote" in loc


def test_format_url_signals_block_job_board() -> None:
    block = format_url_signals_block(
        {"job_url": "https://www.indeed.com/viewjob?jk=abc"}
    )
    assert "job board" in block.lower()


def test_should_skip_medium_confidence_returns_false() -> None:
    job_analysis = {"company_name_confidence": "MEDIUM", "employer_type": "direct"}
    assert should_skip_disambiguation_step("Datadog", job_analysis, {"url_domain": "lever:dd"}) is False


def test_should_skip_staffing_agency_returns_false() -> None:
    job_analysis = {"company_name_confidence": "HIGH", "employer_type": "staffing_agency"}
    assert should_skip_disambiguation_step("Acme Staffing", job_analysis, {"url_domain": "x"}) is False


def test_empty_company_name_is_generic() -> None:
    assert is_generic_company_name("") is True


def test_icims_url_extracts_slug() -> None:
    signals = parse_job_url_signals("https://acme.icims.com/jobs/123/candidate")
    assert signals is not None
    assert signals.ats_platform == "icims"
    assert signals.ats_slug == "jobs"


def test_should_skip_low_confidence_returns_false() -> None:
    job_analysis = {"company_name_confidence": "LOW", "employer_type": "direct"}
    assert should_skip_disambiguation_step("Datadog", job_analysis, {"url_domain": "x"}) is False


def test_should_skip_missing_confidence_with_url_domain() -> None:
    job_analysis = {"employer_type": "direct"}
    assert should_skip_disambiguation_step("Datadog", job_analysis, {"url_domain": "lever:dd"}) is True


def test_workday_locale_slug_path() -> None:
    signals = parse_job_url_signals(
        "https://acme.wd5.myworkdayjobs.com/en-US/acme-careers/job/Engineer"
    )
    assert signals is not None
    assert signals.ats_slug == "acme-careers"


def test_format_url_signals_with_ats_metadata() -> None:
    block = format_url_signals_block(
        {"job_url": "https://jobs.lever.co/stripe/abc"}
    )
    assert "lever" in block.lower()
    assert "stripe" in block.lower()


def test_short_generic_name_is_generic() -> None:
    assert is_generic_company_name("Apex") is True


def test_cache_disambiguators_without_ats_slug_uses_domain() -> None:
    disamb = build_company_research_cache_disambiguators(
        "Acme",
        {"industry": "Tech"},
        {"job_url": "https://careers.acme.com/jobs/1"},
    )
    assert disamb["url_domain"] == "acme.com"
