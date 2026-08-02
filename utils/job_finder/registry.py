"""Registry: detect ATS provider from URL and fetch normalized jobs."""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence

from utils.job_finder.blocklists import url_host_is_blocked
from utils.job_finder.providers.ashby import AshbyProvider
from utils.job_finder.providers.bamboohr import BambooHRProvider
from utils.job_finder.providers.breezy import BreezyProvider
from utils.job_finder.providers.greenhouse import GreenhouseProvider
from utils.job_finder.providers.jsonld_generic import JsonLdGenericProvider
from utils.job_finder.providers.lever import LeverProvider
from utils.job_finder.providers.pinpoint import PinpointProvider
from utils.job_finder.providers.recruitee import RecruiteeProvider
from utils.job_finder.providers.rippling import RipplingProvider
from utils.job_finder.providers.smartrecruiters import SmartRecruitersProvider
from utils.job_finder.providers.teamtailor import TeamtailorProvider
from utils.job_finder.providers.workable import WorkableProvider
from utils.job_finder.providers.workday import WorkdayProvider
from utils.job_finder.types import (
    BlockedHostError,
    NormalizedJob,
    UnsupportedCareersPageError,
)
from utils.logging_config import sanitize_log_value

logger = logging.getLogger(__name__)


def _default_providers() -> List:
    return [
        GreenhouseProvider(),
        AshbyProvider(),
        LeverProvider(),
        WorkdayProvider(),
        SmartRecruitersProvider(),
        TeamtailorProvider(),
        RecruiteeProvider(),
        BambooHRProvider(),
        WorkableProvider(),
        BreezyProvider(),
        PinpointProvider(),
        RipplingProvider(),
    ]


class ProviderRegistry:
    """Detect and fetch from registered ATS providers."""

    def __init__(self, providers: Optional[Sequence] = None) -> None:
        self._providers = list(providers) if providers is not None else _default_providers()
        self._generic = JsonLdGenericProvider()

    def detect_provider_id(self, url: str) -> Optional[str]:
        """Return provider id that claims this URL, or None."""
        for p in self._providers:
            try:
                if p.detect(url):
                    return getattr(p, "id", None)
            except Exception:
                logger.debug("detect failed", exc_info=True)
        return None

    async def fetch_jobs(
        self,
        url: str,
        *,
        company_name: Optional[str] = None,
        allow_generic: bool = True,
    ) -> List[NormalizedJob]:
        """
        Fetch jobs for a careers / ATS URL.

        Raises:
            BlockedHostError: job board / shortener
            UnsupportedCareersPageError: no provider could fetch
        """
        if url_host_is_blocked(url):
            raise BlockedHostError(
                "That link looks like a job board, not a company careers page."
            )

        for p in self._providers:
            try:
                if not p.detect(url):
                    continue
            except Exception:
                continue
            try:
                jobs = await p.fetch(url, company_name=company_name)
                if jobs:
                    return jobs
                # Empty board is still a successful detect
                return []
            except Exception as exc:
                logger.info(
                    "Provider %s failed for URL: %s",
                    sanitize_log_value(getattr(p, "id", "?")),
                    sanitize_log_value(str(exc)),
                    exc_info=True,
                )

        if allow_generic:
            try:
                jobs = await self._generic.fetch(url, company_name=company_name)
                if jobs:
                    return jobs
            except Exception as exc:
                logger.info(
                    "Generic JSON-LD fetch failed: %s",
                    sanitize_log_value(str(exc)),
                    exc_info=True,
                )

        raise UnsupportedCareersPageError(
            "We couldn't read open roles from that careers page."
        )


_REGISTRY: Optional[ProviderRegistry] = None


def get_provider_registry() -> ProviderRegistry:
    """Process-wide registry singleton."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ProviderRegistry()
    return _REGISTRY
