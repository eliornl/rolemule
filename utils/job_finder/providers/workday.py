"""Workday public CXS job board provider."""

from __future__ import annotations

import re
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from utils.job_finder.blocklists import host_matches_domain
from utils.job_finder.http import WORKDAY_TIMEOUT, fetch_json
from utils.job_finder.normalize import html_to_text, parse_iso_datetime
from utils.job_finder.types import NormalizedJob, UnsupportedCareersPageError

_LOCALE_RE = re.compile(r"^[a-z]{2}(?:-[A-Za-z]{2})?$", re.I)


class WorkdayProvider:
    """Fetch jobs from Workday CXS public careers boards."""

    id = "workday"

    def detect(self, url: str) -> bool:
        """
        Return True when the URL host is a Workday careers board.

        Args:
            url: Careers or board URL

        Returns:
            True if hostname contains myworkdayjobs.com
        """
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return False
        return host_matches_domain(host, "myworkdayjobs.com")

    def _parse_tenant_site(self, url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Parse host, tenant, and site from a Workday board URL.

        Expected shape:
        ``https://{tenant}.{dc}.myworkdayjobs.com/{locale?}/{site}``

        Args:
            url: Workday careers URL

        Returns:
            Tuple of (host, tenant, site); any may be None if unparsable
        """
        try:
            parsed = urlparse(url)
        except Exception:
            return None, None, None
        host = (parsed.hostname or "").lower()
        if not host_matches_domain(host, "myworkdayjobs.com"):
            return None, None, None
        labels = host.split(".")
        # tenant.wd5.myworkdayjobs.com
        if len(labels) < 4:
            return host, None, None
        tenant = labels[0]
        path_parts = [p for p in (parsed.path or "").split("/") if p]
        site: Optional[str] = None
        if path_parts:
            if _LOCALE_RE.match(path_parts[0]) and len(path_parts) > 1:
                site = path_parts[1]
            else:
                site = path_parts[0]
        return host, tenant, site

    def _absolute_job_url(self, host: str, posting: dict) -> str:
        """
        Build an absolute https job URL from a CXS posting.

        Prefers ``externalPath`` when present (absolute or site-relative).

        Args:
            host: Workday board hostname
            posting: Single jobPostings entry

        Returns:
            Absolute https URL, or empty string if none
        """
        external = posting.get("externalPath") or posting.get("externalUrl") or ""
        external = str(external).strip()
        if external.startswith("https://"):
            return external
        if external.startswith("http://"):
            return ""
        if external.startswith("/"):
            return f"https://{host}{external}"
        if external:
            return f"https://{host}/{external.lstrip('/')}"
        return ""

    async def fetch(
        self,
        url: str,
        *,
        company_name: Optional[str] = None,
    ) -> List[NormalizedJob]:
        """
        POST to the Workday CXS jobs endpoint and normalize listings.

        Args:
            url: Workday board URL
            company_name: Optional display company name override

        Returns:
            Normalized open roles

        Raises:
            UnsupportedCareersPageError: When tenant/site cannot be parsed
        """
        host, tenant, site = self._parse_tenant_site(url)
        if not host or not tenant or not site:
            raise UnsupportedCareersPageError(
                "Could not parse Workday tenant/site from URL"
            )
        api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
        data = await fetch_json(
            api,
            allowed_hosts={host},
            allow_careers_heuristic=False,
            method="POST",
            json_body={
                "appliedFacets": {},
                "limit": 20,
                "offset": 0,
                "searchText": "",
            },
            timeout=WORKDAY_TIMEOUT,
        )
        postings = data.get("jobPostings") if isinstance(data, dict) else None
        if not isinstance(postings, list):
            return []
        company = company_name or tenant.replace("-", " ").title()
        out: List[NormalizedJob] = []
        for j in postings:
            if not isinstance(j, dict):
                continue
            job_url = self._absolute_job_url(host, j)
            if not job_url.startswith("https://"):
                continue
            title = str(j.get("title") or "").strip() or "Untitled"
            loc = j.get("locationsText") or j.get("location") or ""
            if isinstance(loc, dict):
                loc = loc.get("descriptor") or loc.get("name") or ""
            html = j.get("jobDescription") or j.get("description") or ""
            bulleted = j.get("bulletFields")
            if not html and isinstance(bulleted, list):
                html = "<br/>".join(str(b) for b in bulleted if b)
            external_id = str(
                j.get("id")
                or j.get("jobReqId")
                or j.get("externalPath")
                or job_url
            )
            out.append(
                NormalizedJob(
                    provider=self.id,
                    external_id=external_id,
                    title=title,
                    company=company,
                    location=str(loc),
                    url=job_url,
                    description_html=str(html) if html else None,
                    description_text=html_to_text(str(html)) if html else None,
                    posted_at=parse_iso_datetime(
                        j.get("postedOn") or j.get("postedOnDate")
                    ),
                )
            )
        return out
