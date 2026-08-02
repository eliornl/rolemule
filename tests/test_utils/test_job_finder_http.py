"""Unit tests for Job Finder SSRF-safe HTTP helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.test_utils.job_finder_test_helpers import (
    mock_pinned_response,
)
from utils.job_finder.http import (
    MAX_RESPONSE_BYTES,
    _validate_url_for_fetch,
    fetch_json,
    fetch_json_safe,
    fetch_text,
)
from utils.job_finder.types import SsrfBlockedError


class TestValidateUrlForFetch:
    def test_rejects_non_https(self):
        with pytest.raises(SsrfBlockedError, match="Only HTTPS"):
            _validate_url_for_fetch("http://boards.greenhouse.io/acme")

    def test_rejects_blocked_job_board(self):
        with pytest.raises(SsrfBlockedError, match="not allowed"):
            _validate_url_for_fetch(
                "https://www.indeed.com/viewjob",
                allow_careers_heuristic=True,
            )

    def test_rejects_private_ip_literal(self):
        with pytest.raises(SsrfBlockedError, match="Private IP"):
            _validate_url_for_fetch("https://127.0.0.1/jobs")

    def test_requires_allowlist_or_heuristic(self):
        with pytest.raises(SsrfBlockedError, match="not allowlisted"):
            _validate_url_for_fetch("https://example.com/careers")

    def test_allowed_hosts_subdomain(self):
        url = _validate_url_for_fetch(
            "https://api.example.com/jobs",
            allowed_hosts={"example.com"},
        )
        assert url == "https://api.example.com/jobs"

    def test_careers_heuristic_allows_generic_https(self):
        url = _validate_url_for_fetch(
            "https://careers.exampleco.com/jobs",
            allow_careers_heuristic=True,
        )
        assert url.startswith("https://")


class TestResolvePublicIps:
    @pytest.mark.asyncio
    async def test_rejects_dns_private_resolution(self, monkeypatch):
        from utils.job_finder import http as http_mod

        class _Loop:
            async def getaddrinfo(self, host, port, *args, **kwargs):
                return [(2, 1, 6, "", ("10.0.0.1", port))]

        monkeypatch.setattr(
            http_mod.asyncio, "get_running_loop", lambda: _Loop()
        )
        with pytest.raises(SsrfBlockedError, match="Resolved to private IP"):
            await http_mod._resolve_public_ips("evil.example.com")

    @pytest.mark.asyncio
    async def test_rejects_ipv4_mapped_private(self, monkeypatch):
        from utils.job_finder import http as http_mod

        class _Loop:
            async def getaddrinfo(self, host, port, *args, **kwargs):
                return [(10, 1, 6, "", ("::ffff:10.0.0.1", port))]

        monkeypatch.setattr(
            http_mod.asyncio, "get_running_loop", lambda: _Loop()
        )
        with pytest.raises(SsrfBlockedError, match="Resolved to private IP"):
            await http_mod._resolve_public_ips("evil.example.com")


class TestFetchJson:
    @pytest.mark.asyncio
    async def test_fetch_json_success(self):
        payload = {"jobs": [{"id": 1}]}
        with patch(
            "utils.job_finder.http._pinned_https_request",
            mock_pinned_response(payload),
        ):
            data = await fetch_json(
                "https://boards.greenhouse.io/acme",
                allowed_hosts={"boards.greenhouse.io"},
            )
        assert data == payload

    @pytest.mark.asyncio
    async def test_fetch_json_rejects_redirect_status(self):
        with patch(
            "utils.job_finder.http._pinned_https_request",
            AsyncMock(side_effect=SsrfBlockedError("Redirects are not followed")),
        ):
            with pytest.raises(SsrfBlockedError, match="Redirect"):
                await fetch_json(
                    "https://boards.greenhouse.io/acme",
                    allowed_hosts={"boards.greenhouse.io"},
                )

    @pytest.mark.asyncio
    async def test_fetch_json_http_error(self):
        with patch(
            "utils.job_finder.http._pinned_https_request",
            mock_pinned_response({"error": "no"}, status_code=500),
        ):
            with pytest.raises(SsrfBlockedError, match="HTTP 500"):
                await fetch_json(
                    "https://boards.greenhouse.io/acme",
                    allowed_hosts={"boards.greenhouse.io"},
                )

    @pytest.mark.asyncio
    async def test_fetch_json_safe_returns_none(self):
        with patch(
            "utils.job_finder.http._pinned_https_request",
            AsyncMock(side_effect=SsrfBlockedError("nope")),
        ):
            assert (
                await fetch_json_safe(
                    "https://boards.greenhouse.io/acme",
                    allowed_hosts={"boards.greenhouse.io"},
                )
                is None
            )


class TestFetchText:
    @pytest.mark.asyncio
    async def test_fetch_text_success(self):
        html = "<html><body>jobs</body></html>"
        with patch(
            "utils.job_finder.http._pinned_https_request",
            mock_pinned_response(html, as_text=True),
        ):
            text = await fetch_text(
                "https://careers.example.com",
                allow_careers_heuristic=True,
            )
        assert "jobs" in text

    @pytest.mark.asyncio
    async def test_oversized_response_rejected(self):
        with patch(
            "utils.job_finder.http._pinned_https_request",
            AsyncMock(side_effect=SsrfBlockedError("Response too large")),
        ):
            with pytest.raises(SsrfBlockedError, match="too large"):
                await fetch_text(
                    "https://careers.example.com",
                    allow_careers_heuristic=True,
                )

    def test_max_response_bytes_constant(self):
        assert MAX_RESPONSE_BYTES == 5 * 1024 * 1024
