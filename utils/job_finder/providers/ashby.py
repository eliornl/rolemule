"""Ashby public job board provider."""

from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urlparse

from utils.job_finder.blocklists import host_matches_domain
from utils.job_finder.http import fetch_json
from utils.job_finder.normalize import html_to_text, parse_iso_datetime
from utils.job_finder.types import NormalizedJob, UnsupportedCareersPageError

ALLOWED_HOSTS = {
    "jobs.ashbyhq.com",
    "api.ashbyhq.com",
}

_SLUG_RE = re.compile(r"jobs\.ashbyhq\.com/([^/?#]+)", re.I)


class AshbyProvider:
    """Fetch jobs from Ashby public posting API."""

    id = "ashby"

    def detect(self, url: str) -> bool:
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return False
        return host_matches_domain(host, "ashbyhq.com")

    def _slug(self, url: str) -> Optional[str]:
        m = _SLUG_RE.search(url)
        if m:
            return m.group(1)
        m2 = re.search(r"/job-board/([^/?#]+)", url, re.I)
        return m2.group(1) if m2 else None

    async def fetch(
        self,
        url: str,
        *,
        company_name: Optional[str] = None,
    ) -> List[NormalizedJob]:
        slug = self._slug(url)
        if not slug:
            raise UnsupportedCareersPageError("Could not parse Ashby board slug")
        api = (
            f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
            "?includeCompensation=true"
        )
        data = await fetch_json(api, allowed_hosts=ALLOWED_HOSTS)
        jobs = []
        if isinstance(data, dict):
            jobs = data.get("jobs") or data.get("jobBoard", {}).get("jobPostings") or []
        if not isinstance(jobs, list):
            return []
        company = company_name or slug.replace("-", " ").title()
        out: List[NormalizedJob] = []
        for j in jobs:
            if not isinstance(j, dict):
                continue
            job_url = (
                j.get("jobUrl")
                or j.get("applyUrl")
                or j.get("absoluteUrl")
                or ""
            )
            if not job_url and j.get("id"):
                job_url = f"https://jobs.ashbyhq.com/{slug}/{j.get('id')}"
            if not str(job_url).startswith("https://"):
                continue
            html = j.get("descriptionHtml") or j.get("description") or ""
            plain = j.get("descriptionPlain") or html_to_text(str(html))
            loc = j.get("location") or j.get("locationName") or ""
            if isinstance(loc, dict):
                loc = loc.get("name") or ""
            out.append(
                NormalizedJob(
                    provider=self.id,
                    external_id=str(j.get("id") or job_url),
                    title=str(j.get("title") or "").strip() or "Untitled",
                    company=company,
                    location=str(loc),
                    url=str(job_url),
                    description_html=str(html) if html else None,
                    description_text=str(plain) if plain else None,
                    posted_at=parse_iso_datetime(
                        j.get("publishedAt") or j.get("updatedAt")
                    ),
                )
            )
        return out
