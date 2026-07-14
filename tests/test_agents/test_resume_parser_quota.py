"""Resume parser surfaces friendly LLM quota errors (not raw SDK dumps)."""

import pytest
from unittest.mock import AsyncMock

from utils.llm_client import _GEMINI_QUOTA_USER_MESSAGE


@pytest.mark.asyncio
async def test_parse_resume_surfaces_friendly_quota_message(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_gemini_client() -> AsyncMock:
        client = AsyncMock()

        async def boom(**kwargs: object) -> None:
            raise RuntimeError(
                "Generate failed: 429 RESOURCE_EXHAUSTED. "
                "{'error': {'message': 'You exceeded your current quota', 'code': 429}}"
            )

        client.generate = boom
        return client

    monkeypatch.setattr("utils.resume_parser.get_llm_client", fake_get_gemini_client)
    from utils.resume_parser import parse_resume

    with pytest.raises(ValueError) as excinfo:
        await parse_resume("x" * 80)
    assert str(excinfo.value) == _GEMINI_QUOTA_USER_MESSAGE
