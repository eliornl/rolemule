"""Unit tests for Job Finder host blocklists and private IP checks."""

from __future__ import annotations

import pytest

from utils.job_finder.blocklists import (
    hostname_matches_suffix,
    is_blocked_host,
    is_blocked_job_board_host,
    is_private_ip,
    is_url_shortener_host,
    url_host_is_blocked,
)


class TestJobBoardBlocklist:
    def test_blocks_known_job_boards(self):
        assert is_blocked_job_board_host("www.indeed.com")
        assert is_blocked_job_board_host("uk.linkedin.com")
        assert is_blocked_job_board_host("jobs.glassdoor.com")
        assert url_host_is_blocked("https://www.ziprecruiter.com/jobs/1")

    def test_allows_ats_hosts(self):
        assert not is_blocked_job_board_host("boards.greenhouse.io")
        assert not is_blocked_job_board_host("jobs.lever.co")
        assert not url_host_is_blocked("https://jobs.ashbyhq.com/acme")


class TestUrlShorteners:
    def test_blocks_shortener_hosts(self):
        assert is_url_shortener_host("bit.ly")
        assert is_url_shortener_host("t.co")
        assert is_blocked_host("forms.gle")

    def test_hostname_matches_suffix_subdomain(self):
        assert hostname_matches_suffix("x.bit.ly", ["bit.ly"])
        assert not hostname_matches_suffix("notbit.ly", ["bit.ly"])
        assert not hostname_matches_suffix("", ["bit.ly"])


class TestPrivateIp:
    @pytest.mark.parametrize(
        "addr,expected",
        [
            ("127.0.0.1", True),
            ("10.0.0.5", True),
            ("169.254.169.254", True),
            ("192.168.1.1", True),
            ("100.64.1.1", True),
            ("::ffff:10.0.0.1", True),
            ("::ffff:169.254.169.254", True),
            ("8.8.8.8", False),
            ("not-an-ip", False),
        ],
    )
    def test_private_ip_detection(self, addr: str, expected: bool):
        assert is_private_ip(addr) is expected


class TestHostMatchesDomain:
    def test_suffix_safe(self):
        from utils.job_finder.blocklists import host_matches_domain

        assert host_matches_domain("acme.teamtailor.com", "teamtailor.com")
        assert not host_matches_domain(
            "teamtailor.com.attacker.com", "teamtailor.com"
        )
        assert host_matches_domain("myworkdayjobs.com", "myworkdayjobs.com")
        assert not host_matches_domain(
            "evil.myworkdayjobs.com.attacker.com", "myworkdayjobs.com"
        )


class TestUrlHostIsBlocked:
    def test_path_only_url_without_host_is_not_blocked(self):
        # urlparse does not raise; missing hostname → not treated as blocked
        assert url_host_is_blocked("not-a-valid-url") is False

    def test_empty_host_not_blocked_via_parser(self):
        assert url_host_is_blocked("https:///path") is False
