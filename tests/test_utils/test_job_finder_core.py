"""Unit tests for Job Finder blocklists and SSRF URL validation."""

import pytest

from utils.job_finder.blocklists import (
    is_blocked_host,
    is_private_ip,
    url_host_is_blocked,
)
from utils.job_finder.http import _validate_url_for_fetch
from utils.job_finder.types import SsrfBlockedError


def test_blocks_job_board_hosts():
    assert is_blocked_host("www.indeed.com")
    assert is_blocked_host("linkedin.com")
    assert url_host_is_blocked("https://www.glassdoor.com/job/123")


def test_allows_ats_hosts():
    assert not is_blocked_host("boards.greenhouse.io")
    assert not is_blocked_host("jobs.ashbyhq.com")
    assert not url_host_is_blocked("https://jobs.lever.co/acme")


def test_private_ips():
    assert is_private_ip("127.0.0.1")
    assert is_private_ip("10.0.0.5")
    assert is_private_ip("169.254.169.254")
    assert not is_private_ip("8.8.8.8")


def test_validate_rejects_http_and_blocked():
    with pytest.raises(SsrfBlockedError):
        _validate_url_for_fetch(
            "http://boards.greenhouse.io/x",
            allowed_hosts={"boards.greenhouse.io"},
        )
    with pytest.raises(SsrfBlockedError):
        _validate_url_for_fetch(
            "https://www.indeed.com/viewjob",
            allow_careers_heuristic=True,
        )


def test_greenhouse_detect():
    from utils.job_finder.providers.greenhouse import GreenhouseProvider

    p = GreenhouseProvider()
    assert p.detect("https://boards.greenhouse.io/stripe")
    assert p._board_token("https://boards.greenhouse.io/stripe") == "stripe"


def test_apply_filters_title():
    from utils.job_finder.filters import apply_filters
    from utils.job_finder.types import NormalizedJob, SearchFilters

    jobs = [
        NormalizedJob(
            provider="greenhouse",
            external_id="1",
            title="Senior Backend Engineer",
            company="Acme",
            location="Remote",
            url="https://example.com/1",
            description_text="Python remote backend",
        ),
        NormalizedJob(
            provider="greenhouse",
            external_id="2",
            title="Designer",
            company="Acme",
            location="NYC",
            url="https://example.com/2",
            description_text="Figma",
        ),
    ]
    out = apply_filters(jobs, SearchFilters(title="Backend Engineer"))
    assert len(out) == 1
    assert out[0].external_id == "1"
