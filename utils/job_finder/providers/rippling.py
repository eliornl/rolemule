"""Rippling ATS public board provider."""

from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urlparse

from utils.job_finder.http import fetch_json
from utils.job_finder.normalize import html_to_text, parse_iso_datetime
from utils.job_finder.types import NormalizedJob, UnsupportedCareersPageError

ALLOWED_HOSTS = {"api.rippling.com"}

_SLUG_RE = re.compile(
    r"(?:ats\.rippling\.com|rippling\.com)/(?:ats/)?(?:board/)?([^/?#]+)",
    re.I,
)


class RipplingProvider:
    """Fetch jobs from Rippling public ATS board API."""

    id = "rippling"

    def detect(self, url: str) -> bool:
        """
        Return True when the URL is a Rippling ATS careers host.

        Args:
            url: Careers or board URL

        Returns:
            True if ats.rippling.com or rippling.com is in the hostname
        """
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return False
        return host == "ats.rippling.com" or host.endswith(".rippling.com") or (
            host == "rippling.com"
        )

    def _slug(self, url: str) -> Optional[str]:
        """
        Parse board slug from a Rippling careers URL.

        Args:
            url: Rippling ATS URL

        Returns:
            Board slug, or None
        """
        m = _SLUG_RE.search(url)
        if m:
            slug = m.group(1)
            if slug.lower() not in ("ats", "board", "jobs", "api", "platform"):
                return slug
        # path /board/{slug}/jobs style on api host
        m2 = re.search(r"/board/([^/?#]+)", url, re.I)
        return m2.group(1) if m2 else None

    async def fetch(
        self,
        url: str,
        *,
        company_name: Optional[str] = None,
    ) -> List[NormalizedJob]:
        """
        Fetch jobs from the Rippling ATS board API.

        Args:
            url: Rippling careers / board URL
            company_name: Optional display company name override

        Returns:
            Normalized open roles

        Raises:
            UnsupportedCareersPageError: When board slug cannot be parsed
        """
        slug = self._slug(url)
        if not slug:
            raise UnsupportedCareersPageError("Could not parse Rippling board slug")
        api = (
            f"https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs"
        )
        data = await fetch_json(api, allowed_hosts=ALLOWED_HOSTS)
        jobs: list = []
        if isinstance(data, list):
            jobs = data
        elif isinstance(data, dict):
            jobs = data.get("jobs") or data.get("items") or data.get("data") or []
        if not isinstance(jobs, list):
            return []
        company = company_name or slug.replace("-", " ").title()
        out: List[NormalizedJob] = []
        for j in jobs:
            if not isinstance(j, dict):
                continue
            job_url = (
                j.get("url")
                or j.get("jobUrl")
                or j.get("applyUrl")
                or j.get("absolute_url")
                or ""
            )
            if not job_url and j.get("id"):
                job_url = f"https://ats.rippling.com/{slug}/jobs/{j.get('id')}"
            if not str(job_url).startswith("https://"):
                continue
            loc = j.get("location") or j.get("locations") or ""
            if isinstance(loc, list):
                loc = ", ".join(
                    str(x.get("name") if isinstance(x, dict) else x) for x in loc if x
                )
            elif isinstance(loc, dict):
                loc = loc.get("name") or loc.get("city") or ""
            html = j.get("description") or j.get("jobDescription") or ""
            out.append(
                NormalizedJob(
                    provider=self.id,
                    external_id=str(j.get("id") or j.get("uuid") or job_url),
                    title=str(j.get("name") or j.get("title") or "").strip()
                    or "Untitled",
                    company=company,
                    location=str(loc),
                    url=str(job_url),
                    description_html=str(html) if html else None,
                    description_text=html_to_text(str(html)) if html else None,
                    posted_at=parse_iso_datetime(
                        j.get("createdAt")
                        or j.get("publishedAt")
                        or j.get("created_at")
                    ),
                )
            )
        return out
