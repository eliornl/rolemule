"""Greenhouse public job board provider."""

from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urlparse

from utils.job_finder.http import fetch_json
from utils.job_finder.normalize import html_to_text, parse_iso_datetime
from utils.job_finder.types import NormalizedJob, UnsupportedCareersPageError

ALLOWED_HOSTS = {
    "boards-api.greenhouse.io",
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "job-boards.eu.greenhouse.io",
}

_SLUG_RE = re.compile(
    r"(?:boards|job-boards(?:\.eu)?)\.greenhouse\.io/([^/?#]+)",
    re.I,
)


class GreenhouseProvider:
    """Fetch jobs from Greenhouse public boards API."""

    id = "greenhouse"

    def detect(self, url: str) -> bool:
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return False
        return any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS) or bool(
            _SLUG_RE.search(url)
        )

    def _board_token(self, url: str) -> Optional[str]:
        m = _SLUG_RE.search(url)
        if m:
            return m.group(1)
        # api URL path /v1/boards/{token}/jobs
        m2 = re.search(r"/boards/([^/?#]+)/jobs", url, re.I)
        return m2.group(1) if m2 else None

    async def fetch(
        self,
        url: str,
        *,
        company_name: Optional[str] = None,
    ) -> List[NormalizedJob]:
        token = self._board_token(url)
        if not token:
            raise UnsupportedCareersPageError("Could not parse Greenhouse board token")
        api = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
        data = await fetch_json(api, allowed_hosts=ALLOWED_HOSTS)
        jobs = data.get("jobs") if isinstance(data, dict) else None
        if not isinstance(jobs, list):
            return []
        company = company_name or token.replace("-", " ").title()
        out: List[NormalizedJob] = []
        for j in jobs:
            if not isinstance(j, dict):
                continue
            abs_url = j.get("absolute_url") or ""
            if not str(abs_url).startswith("https://"):
                continue
            content = j.get("content") or ""
            loc = ""
            if isinstance(j.get("location"), dict):
                loc = j["location"].get("name") or ""
            out.append(
                NormalizedJob(
                    provider=self.id,
                    external_id=str(j.get("id") or abs_url),
                    title=str(j.get("title") or "").strip() or "Untitled",
                    company=company,
                    location=str(loc),
                    url=str(abs_url),
                    description_html=str(content) if content else None,
                    description_text=html_to_text(str(content)) if content else None,
                    posted_at=parse_iso_datetime(
                        j.get("first_published") or j.get("updated_at")
                    ),
                )
            )
        return out
