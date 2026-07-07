"""Tests for utils/application_dedupe.py (expanded)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from utils.application_dedupe import (
    _effective_title_company,
    find_conflicting_job_application,
    normalize_title_company_key,
)


def test_normalize_title_company_key_both_required() -> None:
    assert normalize_title_company_key("", "Co") is None
    assert normalize_title_company_key("Title", "") is None


def test_normalize_title_company_key_collapses_whitespace() -> None:
    key = normalize_title_company_key("  Senior   Engineer  ", "  Acme  Inc  ")
    assert key == ("senior engineer", "acme inc")


def test_normalize_title_company_key_whitespace_only() -> None:
    assert normalize_title_company_key("   ", "Acme") is None
    assert normalize_title_company_key("Title", "   ") is None


def test_effective_title_company_fallback_to_job_analysis() -> None:
    class _App:
        job_title = None
        company_name = None

    class _Ws:
        job_analysis = {"job_title": "Engineer", "company_name": "North Island Ventures"}

    assert _effective_title_company(_App(), _Ws()) == ("Engineer", "North Island Ventures")


def test_effective_title_company_non_string_analysis_values() -> None:
    class _App:
        job_title = None
        company_name = None

    class _Ws:
        job_analysis = {"job_title": 123, "company_name": ["bad"]}

    assert _effective_title_company(_App(), _Ws()) == (None, None)


def test_effective_title_company_prefers_columns() -> None:
    class _App:
        job_title = "Col Title"
        company_name = "Col Co"

    class _Ws:
        job_analysis = {"job_title": "Json Title", "company_name": "Json Co"}

    assert _effective_title_company(_App(), _Ws()) == ("Col Title", "Col Co")


@pytest.mark.asyncio
async def test_find_conflicting_job_application_none_when_incomplete_key() -> None:
    db = AsyncMock()
    result = await find_conflicting_job_application(
        db, uuid.uuid4(), "sess-1", None, "Acme"
    )
    assert result is None
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_find_conflicting_job_application_finds_match() -> None:
    user_id = uuid.uuid4()
    other_app = MagicMock()
    other_app.job_title = "Engineer"
    other_app.company_name = "Acme Inc"

    class _Ws:
        job_analysis = {}

    mock_result = MagicMock()
    mock_result.all.return_value = [(other_app, _Ws())]

    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)

    found = await find_conflicting_job_application(
        db,
        user_id,
        "current-session",
        "  engineer  ",
        "acme   inc",
    )
    assert found is other_app


@pytest.mark.asyncio
async def test_find_conflicting_job_application_no_match() -> None:
    user_id = uuid.uuid4()
    other_app = MagicMock()
    other_app.job_title = "Designer"
    other_app.company_name = "Other Co"

    class _Ws:
        job_analysis = {}

    mock_result = MagicMock()
    mock_result.all.return_value = [(other_app, _Ws())]

    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)

    found = await find_conflicting_job_application(
        db, user_id, "sess", "Engineer", "Acme Inc"
    )
    assert found is None
