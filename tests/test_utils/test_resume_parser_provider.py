"""Assert resume parser forwards llm_provider to generate()."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.resume_parser import parse_resume


@pytest.mark.asyncio
async def test_parse_resume_passes_provider_to_generate() -> None:
    mock_client = MagicMock()
    mock_client.generate = AsyncMock(
        return_value={
            "response": '{"full_name":"Ada","email":"a@b.com","skills":[]}',
            "done": True,
        }
    )
    with patch(
        "utils.resume_parser.get_llm_client", AsyncMock(return_value=mock_client)
    ), patch(
        "utils.resume_parser.parse_json_from_llm_response",
        return_value={"full_name": "Ada", "email": "a@b.com", "skills": []},
    ), patch(
        "utils.resume_parser._clean_parsed_data",
        side_effect=lambda d: d,
    ):
        await parse_resume(
            "x" * 80,
            user_api_key="sk-test",
            llm_provider="openai",
        )

    kwargs = mock_client.generate.await_args.kwargs
    assert kwargs.get("provider") == "openai"
    assert kwargs.get("user_api_key") == "sk-test"
