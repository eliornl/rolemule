"""
Direct-handler coverage for remaining api/extension_autofill.py gaps.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.responses import Response

from api.extension_autofill import (
    AutofillFieldIn,
    AutofillMapRequest,
    _build_user_prompt,
    _get_user_api_key,
    _llm_ready,
    _sanitize_extras,
    _sanitize_field_dict,
    _sanitize_form_autofill_value,
    map_form_fields_to_profile,
)
from models.database import AuthMethod, User, UserProfile
from tests.test_api.conftest import _NullSessionLocal
from utils.error_responses import APIError


def _user_dict(uid: uuid.UUID, email: str) -> dict:
    return {
        "id": str(uid),
        "_id": str(uid),
        "email": email,
        "full_name": "Autofill User",
        "profile_completed": True,
    }


async def _seed_user_with_profile() -> tuple[uuid.UUID, str]:
    uid = uuid.uuid4()
    email = f"autofill_{uid.hex[:10]}@example.com"
    async with _NullSessionLocal() as db:
        db.add(
            User(
                id=uid,
                email=email,
                password_hash="$2b$12$placeholder",
                auth_method=AuthMethod.LOCAL.value,
                full_name="Autofill User",
                profile_completed=True,
            )
        )
        from models.database import UserWorkflowPreferences

        db.add(
            UserWorkflowPreferences(
                id=uuid.uuid4(),
                user_id=uid,
                preferred_provider="ollama",
            )
        )
        db.add(
            UserProfile(
                id=uuid.uuid4(),
                user_id=uid,
                professional_title="Engineer",
                years_experience=4,
                summary="Profile summary.",
                city="Austin",
                state="TX",
                country="US",
            )
        )
        await db.commit()
    return uid, email


async def _cleanup(uid: uuid.UUID) -> None:
    from sqlalchemy import delete

    async with _NullSessionLocal() as db:
        await db.execute(delete(UserProfile).where(UserProfile.user_id == uid))
        await db.execute(delete(User).where(User.id == uid))
        await db.commit()


class TestExtensionAutofillDirectHandlers:
    @pytest.mark.asyncio
    async def test_get_user_api_key_decrypts(self) -> None:
        from utils.llm.availability import UserLLMContext

        uid = uuid.uuid4()
        ctx = UserLLMContext(
            provider="gemini",
            user_api_key="sk-test",
            preferred_model=None,
            ready=True,
        )
        async with _NullSessionLocal() as db:
            with patch(
                "utils.llm_context.require_user_llm_context",
                AsyncMock(return_value=(MagicMock(), ctx, None)),
            ):
                key = await _get_user_api_key(db, uid)
        assert key == "sk-test"

    def test_sanitize_field_dict_all_optional_fields(self) -> None:
        field = AutofillFieldIn(
            field_uid="0",
            tag="input",
            input_type="text",
            name_attr="first_name",
            id_attr="first",
            label_text="First name",
            placeholder="Jane",
            aria_label="Given name",
            required=True,
            max_length=50,
            options=[{"value": "a", "text": "Option A"}],
            duplicate_label_index=1,
        )
        out = _sanitize_field_dict(field)
        assert out["name_attr"] == "first_name"
        assert out["placeholder"] == "Jane"
        assert out["options"][0]["text"] == "Option A"
        assert out["duplicate_label_index"] == 1

    def test_autofill_map_request_extras_length_validation(self) -> None:
        with pytest.raises(ValueError, match="extras key too long"):
            AutofillMapRequest(
                page_url="https://example.com/apply",
                fields=[
                    AutofillFieldIn(
                        field_uid="0",
                        tag="input",
                        input_type="text",
                        label_text="Name",
                    )
                ],
                extras={"x" * 65: "v"},
            )
        with pytest.raises(ValueError, match="extras value too long"):
            AutofillMapRequest(
                page_url="https://example.com/apply",
                fields=[
                    AutofillFieldIn(
                        field_uid="0",
                        tag="input",
                        input_type="text",
                        label_text="Name",
                    )
                ],
                extras={"k": "v" * 501},
            )

    @pytest.mark.asyncio
    async def test_map_cache_hit_finalize_direct(self) -> None:
        uid, email = await _seed_user_with_profile()
        try:
            request = AutofillMapRequest(
                page_url="https://careers.example.com/apply",
                fields=[
                    AutofillFieldIn(
                        field_uid="0",
                        tag="input",
                        input_type="text",
                        label_text="Name*",
                        required=True,
                    )
                ],
            )
            stale_cache = {
                "assignments": [
                    {"field_uid": "0", "value": "Autofill User"},
                    {"field_uid": "99", "value": "ghost"},
                ],
                "skipped": [{"field_uid": "99", "reason": "unknown"}],
            }
            response = Response()
            async with _NullSessionLocal() as db:
                from utils.cache import RateLimitResult

                with (
                    patch(
                        "api.extension_autofill.check_rate_limit_with_headers",
                        AsyncMock(
                            return_value=RateLimitResult(
                                allowed=True, limit=15, remaining=14, reset_seconds=3600
                            )
                        ),
                    ),
                    patch("api.extension_autofill._get_user_api_key", AsyncMock(return_value=None)),
                    patch("api.extension_autofill._server_has_llm", return_value=True),
                    patch("api.extension_autofill.get_cached_tool_result", AsyncMock(return_value=stale_cache)),
                ):
                    resp = await map_form_fields_to_profile(
                        request=request,
                        response=response,
                        current_user=_user_dict(uid, email),
                        db=db,
                    )
            assert resp.assignments[0].field_uid == "0"
            assert all(s.get("field_uid") != "99" for s in resp.skipped)
        finally:
            await _cleanup(uid)

    @pytest.mark.asyncio
    async def test_map_internal_error_direct(self) -> None:
        uid, email = await _seed_user_with_profile()
        try:
            request = AutofillMapRequest(
                page_url="https://careers.example.com/apply",
                fields=[
                    AutofillFieldIn(
                        field_uid="0",
                        tag="input",
                        input_type="text",
                        label_text="Name",
                    )
                ],
            )
            response = Response()
            async with _NullSessionLocal() as db:
                from utils.cache import RateLimitResult

                with (
                    patch(
                        "api.extension_autofill.check_rate_limit_with_headers",
                        AsyncMock(
                            return_value=RateLimitResult(
                                allowed=True, limit=15, remaining=14, reset_seconds=3600
                            )
                        ),
                    ),
                    patch("api.extension_autofill._get_user_api_key", AsyncMock(return_value=None)),
                    patch("api.extension_autofill._server_has_llm", return_value=True),
                    patch("api.extension_autofill.get_cached_tool_result", AsyncMock(return_value=None)),
                    patch("api.extension_autofill.get_gemini_client", AsyncMock(side_effect=RuntimeError("boom"))),
                ):
                    with pytest.raises(APIError) as exc:
                        await map_form_fields_to_profile(
                            request=request,
                            response=response,
                            current_user=_user_dict(uid, email),
                            db=db,
                        )
            assert exc.value.status_code == 500
        finally:
            await _cleanup(uid)

    @pytest.mark.asyncio
    async def test_map_llm_path_direct(self) -> None:
        uid, email = await _seed_user_with_profile()
        try:
            request = AutofillMapRequest(
                page_url="https://careers.example.com/apply",
                fields=[
                    AutofillFieldIn(
                        field_uid="0",
                        tag="input",
                        input_type="text",
                        label_text="First name",
                    )
                ],
            )
            response = Response()
            mock_client = MagicMock()
            mock_client.generate = AsyncMock(
                return_value={
                    "response": '{"assignments":[{"field_uid":"0","value":"Autofill User"}],'
                    '"skipped":[]}',
                    "done": True,
                }
            )
            async with _NullSessionLocal() as db:
                from utils.cache import RateLimitResult

                with (
                    patch(
                        "api.extension_autofill.check_rate_limit_with_headers",
                        AsyncMock(
                            return_value=RateLimitResult(
                                allowed=True, limit=15, remaining=14, reset_seconds=3600
                            )
                        ),
                    ),
                    patch("api.extension_autofill._get_user_api_key", AsyncMock(return_value=None)),
                    patch("api.extension_autofill._server_has_llm", return_value=True),
                    patch("api.extension_autofill.get_cached_tool_result", AsyncMock(return_value=None)),
                    patch("api.extension_autofill.cache_tool_result", AsyncMock(return_value=True)),
                    patch("api.extension_autofill.get_gemini_client", AsyncMock(return_value=mock_client)),
                ):
                    resp = await map_form_fields_to_profile(
                        request=request,
                        response=response,
                        current_user=_user_dict(uid, email),
                        db=db,
                    )
            assert resp.assignments[0].value == "Autofill"
        finally:
            await _cleanup(uid)

    def test_autofill_rate_limit_debug_cap(self) -> None:
        from api.extension_autofill import _autofill_rate_limit

        with patch("api.extension_autofill.get_settings") as mock_settings:
            mock_settings.return_value.debug = True
            assert _autofill_rate_limit() == 200

    @pytest.mark.asyncio
    async def test_get_user_api_key_cfg_returns_none(self) -> None:
        uid = uuid.uuid4()
        mock_db = AsyncMock()
        from utils.error_responses import no_api_key_error

        with patch(
            "utils.llm_context.require_user_llm_context",
            AsyncMock(side_effect=no_api_key_error()),
        ):
            assert await _get_user_api_key(mock_db, uid) is None

    @pytest.mark.asyncio
    async def test_get_user_api_key_generic_exception(self) -> None:
        uid = uuid.uuid4()
        mock_db = AsyncMock()
        with patch(
            "utils.llm_context.require_user_llm_context",
            AsyncMock(side_effect=RuntimeError("db fail")),
        ):
            assert await _get_user_api_key(mock_db, uid) is None

    @pytest.mark.asyncio
    async def test_llm_ready_true_with_ollama(self) -> None:
        uid, email = await _seed_user_with_profile()
        try:
            async with _NullSessionLocal() as db:
                assert await _llm_ready(db, uid) is True
        finally:
            await _cleanup(uid)

    def test_sanitize_form_autofill_value_truncates(self) -> None:
        long_val = "x" * 9000
        out = _sanitize_form_autofill_value(long_val)
        assert len(out) == 8000

    def test_sanitize_extras_skips_empty_keys(self) -> None:
        assert _sanitize_extras({"": "value", "ok": "v"}) == {"ok": "v"}

    def test_build_user_prompt_includes_profile(self) -> None:
        fields = [
            _sanitize_field_dict(
                AutofillFieldIn(
                    field_uid="0",
                    tag="input",
                    input_type="email",
                    label_text="Email",
                )
            )
        ]
        bundle = {"email": "u@example.com", "full_name": "User", "profile": {"city": "Austin"}}
        prompt = _build_user_prompt(fields, bundle, {}, "https://example.com/apply")
        assert "PROFILE_JSON" in prompt
        assert "Austin" in prompt

    @pytest.mark.asyncio
    async def test_map_user_not_found(self) -> None:
        uid = uuid.uuid4()
        request = AutofillMapRequest(
            page_url="https://careers.example.com/apply",
            fields=[AutofillFieldIn(field_uid="0", tag="input", input_type="text", label_text="Name")],
        )
        response = Response()
        async with _NullSessionLocal() as db:
            from utils.cache import RateLimitResult

            with (
                patch(
                    "api.extension_autofill.check_rate_limit_with_headers",
                    AsyncMock(
                        return_value=RateLimitResult(
                            allowed=True, limit=15, remaining=14, reset_seconds=3600
                        )
                    ),
                ),
                patch("api.extension_autofill._get_user_api_key", AsyncMock(return_value=None)),
                patch("api.extension_autofill._server_has_llm", return_value=True),
            ):
                with pytest.raises(APIError) as exc:
                    await map_form_fields_to_profile(
                        request=request,
                        response=response,
                        current_user=_user_dict(uid, "ghost@example.com"),
                        db=db,
                    )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_map_cached_response_path(self) -> None:
        uid, email = await _seed_user_with_profile()
        request = AutofillMapRequest(
            page_url="https://careers.example.com/apply",
            fields=[
                AutofillFieldIn(field_uid="0", tag="input", input_type="text", label_text="Referral code"),
                AutofillFieldIn(field_uid="1", tag="input", input_type="text", label_text="Optional note"),
            ],
        )
        response = Response()
        cached = {
            "assignments": [{"field_uid": "0", "value": "REF-123"}],
            "skipped": [{"field_uid": "1", "reason": "already filled"}],
        }
        try:
            async with _NullSessionLocal() as db:
                from utils.cache import RateLimitResult

                with (
                    patch(
                        "api.extension_autofill.check_rate_limit_with_headers",
                        AsyncMock(
                            return_value=RateLimitResult(
                                allowed=True, limit=15, remaining=14, reset_seconds=3600
                            )
                        ),
                    ),
                    patch("api.extension_autofill.get_cached_tool_result", AsyncMock(return_value=cached)),
                ):
                    resp = await map_form_fields_to_profile(
                        request=request,
                        response=response,
                        current_user=_user_dict(uid, email),
                        db=db,
                    )
            assert resp.assignments[0].value == "REF-123"
            assert len(resp.skipped) == 1
        finally:
            await _cleanup(uid)

    @pytest.mark.asyncio
    async def test_map_gemini_error(self) -> None:
        uid, email = await _seed_user_with_profile()
        request = AutofillMapRequest(
            page_url="https://careers.example.com/apply",
            fields=[AutofillFieldIn(field_uid="0", tag="input", input_type="text", label_text="Name")],
        )
        response = Response()
        from utils.llm_client import GeminiError

        try:
            async with _NullSessionLocal() as db:
                from utils.cache import RateLimitResult

                with (
                    patch(
                        "api.extension_autofill.check_rate_limit_with_headers",
                        AsyncMock(
                            return_value=RateLimitResult(
                                allowed=True, limit=15, remaining=14, reset_seconds=3600
                            )
                        ),
                    ),
                    patch("api.extension_autofill.get_cached_tool_result", AsyncMock(return_value=None)),
                    patch(
                        "api.extension_autofill.get_gemini_client",
                        AsyncMock(side_effect=GeminiError("model unavailable")),
                    ),
                ):
                    with pytest.raises(APIError) as exc:
                        await map_form_fields_to_profile(
                            request=request,
                            response=response,
                            current_user=_user_dict(uid, email),
                            db=db,
                        )
            assert exc.value.status_code == 503
        finally:
            await _cleanup(uid)

    @pytest.mark.asyncio
    async def test_map_parse_failure(self) -> None:
        uid, email = await _seed_user_with_profile()
        request = AutofillMapRequest(
            page_url="https://careers.example.com/apply",
            fields=[AutofillFieldIn(field_uid="0", tag="input", input_type="text", label_text="Name")],
        )
        response = Response()
        mock_client = MagicMock()
        mock_client.generate = AsyncMock(return_value={"response": "not json", "done": True})
        try:
            async with _NullSessionLocal() as db:
                from utils.cache import RateLimitResult

                with (
                    patch(
                        "api.extension_autofill.check_rate_limit_with_headers",
                        AsyncMock(
                            return_value=RateLimitResult(
                                allowed=True, limit=15, remaining=14, reset_seconds=3600
                            )
                        ),
                    ),
                    patch("api.extension_autofill.get_cached_tool_result", AsyncMock(return_value=None)),
                    patch("api.extension_autofill.get_gemini_client", AsyncMock(return_value=mock_client)),
                ):
                    with pytest.raises(APIError) as exc:
                        await map_form_fields_to_profile(
                            request=request,
                            response=response,
                            current_user=_user_dict(uid, email),
                            db=db,
                        )
            assert exc.value.status_code == 503
        finally:
            await _cleanup(uid)

    @pytest.mark.asyncio
    async def test_map_unexpected_error(self) -> None:
        uid, email = await _seed_user_with_profile()
        request = AutofillMapRequest(
            page_url="https://careers.example.com/apply",
            fields=[AutofillFieldIn(field_uid="0", tag="input", input_type="text", label_text="Name")],
        )
        response = Response()
        try:
            async with _NullSessionLocal() as db:
                from utils.cache import RateLimitResult

                with (
                    patch(
                        "api.extension_autofill.check_rate_limit_with_headers",
                        AsyncMock(
                            return_value=RateLimitResult(
                                allowed=True, limit=15, remaining=14, reset_seconds=3600
                            )
                        ),
                    ),
                    patch("api.extension_autofill.get_cached_tool_result", AsyncMock(return_value=None)),
                    patch(
                        "api.extension_autofill.get_gemini_client",
                        AsyncMock(side_effect=RuntimeError("boom")),
                    ),
                ):
                    with pytest.raises(APIError) as exc:
                        await map_form_fields_to_profile(
                            request=request,
                            response=response,
                            current_user=_user_dict(uid, email),
                            db=db,
                        )
            assert exc.value.status_code == 500
        finally:
            await _cleanup(uid)
