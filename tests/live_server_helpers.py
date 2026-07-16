"""Helpers for live-server tests against a running localhost:8000 instance.

These tests are not run in CI. They need either a real ``GEMINI_API_KEY`` for
LLM success paths, or should ``pytest.skip`` when only a format-valid dummy key
is available (``.env`` often has an empty Gemini key).
"""

from __future__ import annotations

import os
from typing import Mapping, MutableMapping, Optional, Union

import httpx
import pytest

from tests.gemini_test_keys import DUMMY_GEMINI_API_KEY

Headers = Union[Mapping[str, str], MutableMapping[str, str]]


def real_gemini_api_key() -> Optional[str]:
    """Return a non-empty ``GEMINI_API_KEY`` from the environment, else None."""
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    return key or None


def skip_unless_real_gemini() -> None:
    """Skip when no real Gemini API key is configured for live LLM calls."""
    if not real_gemini_api_key():
        pytest.skip("No real GEMINI_API_KEY — skipping live LLM success test")


def ensure_llm_ready(
    client: httpx.Client,
    headers: Headers,
    *,
    prefer_real_key: bool = True,
) -> Headers:
    """
    POST a Gemini BYOK key so LLM-gated endpoints are not blocked by CFG_6001.

    Uses ``GEMINI_API_KEY`` when set and ``prefer_real_key`` is True; otherwise
    posts ``DUMMY_GEMINI_API_KEY`` (format-valid only — upstream LLM calls will
    still fail and should be skipped via ``skip_unless_llm_ok``).

    Args:
        client: Sync httpx client pointed at the live server.
        headers: Auth headers for the user under test.
        prefer_real_key: Prefer env ``GEMINI_API_KEY`` when present.

    Returns:
        The same headers mapping (unchanged) for fixture chaining.

    Raises:
        pytest.fail: If the API key POST does not return HTTP 200.
    """
    key = real_gemini_api_key() if prefer_real_key else None
    key = key or DUMMY_GEMINI_API_KEY
    response = client.post(
        "/api/v1/profile/api-key",
        headers=headers,
        json={"api_key": key, "provider": "gemini"},
    )
    if response.status_code != 200:
        pytest.fail(
            f"ensure_llm_ready failed: {response.status_code} {response.text}"
        )
    return headers


def skip_unless_llm_ok(response: httpx.Response) -> None:
    """
    ``pytest.skip`` when the response indicates missing LLM credentials or an
    upstream LLM failure that cannot succeed without a real API key.

    Safe to call after every LLM-backed live request. Does nothing when the
    status is not an error, or when a real ``GEMINI_API_KEY`` is set (so real
    regressions still fail the test).
    """
    if response.status_code < 400:
        return

    try:
        body = response.json()
    except Exception:
        body = {}

    error_code = str(body.get("error_code") or "")
    message = str(
        body.get("message") or body.get("detail") or response.text or ""
    ).lower()

    if error_code == "CFG_6001":
        pytest.skip("No LLM credentials (CFG_6001)")

    # With a real key configured, do not swallow failures — let the assert fail.
    if real_gemini_api_key():
        return

    no_key_markers = (
        "api key",
        "no api key",
        "credentials",
        "cfg_6001",
    )
    llm_fail_markers = (
        "failed to generate",
        "validation failed",
        "invalid api key",
        "authentication",
        "permission denied",
        "unauthorized",
        "quota",
        "resource_exhausted",
        "upstream",
        "llm",
        "gemini",
        "openai",
        "anthropic",
    )

    if any(m in message for m in no_key_markers):
        pytest.skip(f"No LLM credentials ({response.status_code})")

    if response.status_code in (422, 500, 502, 503) and (
        error_code in ("INT_9001", "EXT_5001", "CFG_6001", "VAL_2001")
        or any(m in message for m in llm_fail_markers)
    ):
        # VAL_2001 alone is often request validation — only skip when message
        # looks LLM-related (handled above) or generation failed.
        if error_code == "VAL_2001" and not any(
            m in message for m in (*no_key_markers, *llm_fail_markers)
        ):
            return
        pytest.skip(
            f"No real LLM available ({response.status_code} {error_code}): "
            f"{message[:140]}"
        )
