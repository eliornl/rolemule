"""Pinpoint HQ public postings provider."""

from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urlparse

from utils.job_finder.blocklists import host_matches_domain
from utils.job_finder.http import fetch_json
from utils.job_finder.normalize import html_to_text, parse_iso_datetime
from utils.job_finder.types import NormalizedJob, UnsupportedCareersPageError

_SLUG_RE = re.compile(r"([a-z0-9-]+)\.pinpointhq\.com", re.I)


class PinpointProvider:
    """Fetch jobs from Pinpoint HQ public postings.json."""

    id = "pinpoint"

    def detect(self, url: str) -> bool:
        """
        Return True when the URL host is Pinpoint HQ.

        Args:
            url: Careers or board URL

        Returns:
            True if pinpointhq.com is in the hostname
        """
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return False
        return host_matches_domain(host, "pinpointhq.com")

    def _slug(self, url: str) -> Optional[str]:
        """
        Parse company slug from a Pinpoint careers URL.

        Args:
            url: Pinpoint careers URL

        Returns:
            Slug string, or None
        """
        m = _SLUG_RE.search(url)
        return m.group(1) if m else None

    async def fetch(
        self,
        url: str,
        *,
        company_name: Optional[str] = None,
    ) -> List[NormalizedJob]:
        """
        Fetch openings from ``https://{slug}.pinpointhq.com/postings.json``.

        Args:
            url: Pinpoint careers URL
            company_name: Optional display company name override

        Returns:
            Normalized open roles

        Raises:
            UnsupportedCareersPageError: When slug cannot be parsed
        """
        slug = self._slug(url)
        if not slug:
            raise UnsupportedCareersPageError("Could not parse Pinpoint slug")
        host = f"{slug}.pinpointhq.com"
        api = f"https://{host}/postings.json"
        data = await fetch_json(api, allowed_hosts={host})
        jobs: list = []
        if isinstance(data, list):
            jobs = data
        elif isinstance(data, dict):
            jobs = data.get("data") or data.get("postings") or data.get("jobs") or []
        if not isinstance(jobs, list):
            return []
        company = company_name or slug.replace("-", " ").title()
        out: List[NormalizedJob] = []
        for j in jobs:
            if not isinstance(j, dict):
                continue
            attrs = j.get("attributes") if isinstance(j.get("attributes"), dict) else j
            job_url = (
                attrs.get("url")
                or attrs.get("external_url")
                or j.get("url")
                or ""
            )
            if not job_url and (attrs.get("id") or j.get("id")):
                jid = attrs.get("id") or j.get("id")
                job_url = f"https://{host}/en/postings/{jid}"
            if not str(job_url).startswith("https://"):
                continue
            loc = attrs.get("location") or attrs.get("workplace_type") or ""
            if isinstance(loc, dict):
                loc = loc.get("name") or loc.get("city") or ""
            html = (
                attrs.get("description")
                or attrs.get("key_responsibilities")
                or ""
            )
            out.append(
                NormalizedJob(
                    provider=self.id,
                    external_id=str(attrs.get("id") or j.get("id") or job_url),
                    title=str(attrs.get("title") or j.get("title") or "").strip()
                    or "Untitled",
                    company=company,
                    location=str(loc),
                    url=str(job_url),
                    description_html=str(html) if html else None,
                    description_text=html_to_text(str(html)) if html else None,
                    posted_at=parse_iso_datetime(
                        attrs.get("created_at")
                        or attrs.get("published_at")
                        or j.get("created_at")
                    ),
                )
            )
        return out
