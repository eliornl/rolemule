"""CV HTML export must pass provider= into generate()."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.cv_optimizer import _generate_cv_html_from_markdown


@pytest.mark.asyncio
async def test_cv_html_generate_passes_provider() -> None:
    mock_client = MagicMock()
    mock_client.generate = AsyncMock(
        return_value={
            "response": "<!DOCTYPE html><html><body>cv</body></html>",
            "done": True,
        }
    )
    with patch(
        "utils.llm_client.get_llm_client", AsyncMock(return_value=mock_client)
    ), patch(
        "api.cv_optimizer.normalize_cv_export_html",
        side_effect=lambda html: html,
    ):
        html = await _generate_cv_html_from_markdown(
            "# Resume\n\nExperience",
            user_api_key="sk-ant-test",
            preferred_model=None,
            llm_provider="anthropic",
        )

    assert "html" in html.lower()
    kwargs = mock_client.generate.await_args.kwargs
    assert kwargs.get("provider") == "anthropic"
