"""Lever public postings provider."""

from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urlparse

from utils.job_finder.blocklists import host_matches_domain
from utils.job_finder.http import fetch_json
from utils.job_finder.normalize import html_to_text, parse_iso_datetime
from utils.job_finder.types import NormalizedJob, UnsupportedCareersPageError

ALLOWED_HOSTS = {
    "jobs.lever.co",
    "jobs.eu.lever.co",
    "api.lever.co",
    "api.eu.lever.co",
}

_SLUG_RE = re.compile(r"jobs\.(?:eu\.)?lever\.co/([^/?#]+)", re.I)


class LeverProvider:
    """Fetch jobs from Lever public postings API."""

    id = "lever"

    def detect(self, url: str) -> bool:
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return False
        return host_matches_domain(host, "lever.co")

    def _slug_and_api(self, url: str) -> tuple[Optional[str], Optional[str]]:
        m = _SLUG_RE.search(url)
        if not m:
            return None, None
        slug = m.group(1)
        eu = "jobs.eu.lever.co" in url.lower()
        api_host = "api.eu.lever.co" if eu else "api.lever.co"
        return slug, f"https://{api_host}/v0/postings/{slug}?mode=json"

    async def fetch(
        self,
        url: str,
        *,
        company_name: Optional[str] = None,
    ) -> List[NormalizedJob]:
        slug, api = self._slug_and_api(url)
        if not slug or not api:
            raise UnsupportedCareersPageError("Could not parse Lever board slug")
        data = await fetch_json(api, allowed_hosts=ALLOWED_HOSTS)
        jobs = data if isinstance(data, list) else []
        company = company_name or slug.replace("-", " ").title()
        out: List[NormalizedJob] = []
        for j in jobs:
            if not isinstance(j, dict):
                continue
            job_url = j.get("hostedUrl") or j.get("applyUrl") or ""
            if not str(job_url).startswith("https://"):
                continue
            desc = j.get("descriptionPlain") or ""
            if not desc:
                desc = html_to_text(j.get("description") or "")
            cats = j.get("categories") or {}
            loc = ""
            if isinstance(cats, dict):
                loc = cats.get("location") or cats.get("commitment") or ""
            out.append(
                NormalizedJob(
                    provider=self.id,
                    external_id=str(j.get("id") or job_url),
                    title=str(j.get("text") or j.get("title") or "").strip()
                    or "Untitled",
                    company=company,
                    location=str(loc),
                    url=str(job_url),
                    description_html=j.get("description"),
                    description_text=str(desc) if desc else None,
                    posted_at=parse_iso_datetime(j.get("createdAt")),
                )
            )
        return out
