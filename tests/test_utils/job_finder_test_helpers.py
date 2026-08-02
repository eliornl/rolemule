"""Shared helpers for Job Finder unit tests."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "job_finder"


def load_fixture(name: str) -> Any:
    """Load JSON or text fixture from tests/fixtures/job_finder/."""
    path = FIXTURES_DIR / name
    text = path.read_text(encoding="utf-8")
    if name.endswith(".json"):
        return json.loads(text)
    return text


def patch_public_dns(monkeypatch) -> None:
    """Make SSRF DNS checks resolve to a public IP (async getaddrinfo)."""

    async def _fake_getaddrinfo(host: str, port: int, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port))]

    async def _loop_getaddrinfo(host, port, *args, **kwargs):
        return await _fake_getaddrinfo(host, port, *args, **kwargs)

    class _Loop:
        async def getaddrinfo(self, host, port, *args, **kwargs):
            return await _fake_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(
        "utils.job_finder.http.asyncio.get_running_loop",
        lambda: _Loop(),
    )


def mock_pinned_response(
    payload: Any,
    *,
    status_code: int = 200,
    as_text: bool = False,
) -> AsyncMock:
    """Mock ``_pinned_https_request`` to return status + body bytes."""
    if as_text:
        if isinstance(payload, bytes):
            body = payload
        else:
            body = str(payload).encode("utf-8")
    else:
        body = json.dumps(payload).encode("utf-8")
    return AsyncMock(return_value=(status_code, body))
