"""Provider protocol for Job Finder ATS adapters."""

from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from utils.job_finder.types import NormalizedJob


@runtime_checkable
class JobBoardProvider(Protocol):
    """ATS / careers board provider."""

    id: str

    def detect(self, url: str) -> bool:
        """Return True if this provider can handle the URL."""

    async def fetch(
        self,
        url: str,
        *,
        company_name: Optional[str] = None,
    ) -> List[NormalizedJob]:
        """Fetch and normalize open jobs for the board URL."""
