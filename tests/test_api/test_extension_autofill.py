"""
Integration tests for extension autofill map endpoint.

POST /api/v1/extension/autofill/map
POST /api/extension/autofill/map (legacy prefix)
"""

import uuid

import jwt
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import update

from config.settings import get_security_settings
from main import app
from models.database import User, UserProfile
from tests.test_api.conftest import _NullSessionLocal
from utils.auth import get_current_user, get_current_user_with_complete_profile
from utils.cache import RateLimitResult
from utils.llm_client import GeminiError

BASE = "/api/v1/extension"
LEGACY_BASE = "/api/extension"


def _single_field_body(**overrides):
    base = {
        "page_url": "https://careers.example.com/apply",
        "fields": [
            {
                "field_uid": "0",
                "tag": "input",
                "input_type": "text",
                "label_text": "First name",
            }
        ],
    }
    base.update(overrides)
    return base


async def _ensure_profile_for_token(
    authed_client_with_user,
    summary: str = "Autofill test profile.",
    *,
    full_name: str | None = None,
    **profile_kwargs,
) -> uuid.UUID:
    token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
    sec = get_security_settings()
    payload = jwt.decode(
        token,
        sec.jwt_config["secret_key"],
        algorithms=[sec.jwt_config["algorithm"]],
    )
    uid = uuid.UUID(payload["sub"])
    async with _NullSessionLocal() as session:
        user_vals: dict = {"profile_completed": True}
        if full_name is not None:
            user_vals["full_name"] = full_name
        await session.execute(update(User).where(User.id == uid).values(**user_vals))
        session.add(
            UserProfile(
                id=uuid.uuid4(),
                user_id=uid,
                professional_title="Engineer",
                years_experience=5,
                summary=summary,
                city=profile_kwargs.pop("city", "Austin"),
                state=profile_kwargs.pop("state", "TX"),
                country=profile_kwargs.pop("country", "US"),
                **profile_kwargs,
            )
        )
        await session.commit()
    return uid


def _complete_user_override(uid: uuid.UUID, payload: dict):
    async def _mock_complete_user():
        return {
            "id": str(uid),
            "_id": str(uid),
            "email": payload.get("email", "u@example.com"),
            "full_name": "Autofill Test User",
            "auth_method": "local",
            "is_admin": False,
            "profile_completed": True,
            "profile_completion_percentage": 100,
            "has_google_linked": False,
            "has_password": True,
        }

    return _mock_complete_user


class TestExtensionAutofillMap:
    """POST /extension/autofill/map"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.post(f"{BASE}/autofill/map", json=_single_field_body())
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_invalid_page_url_422(self, authed_client):
        body = {
            "page_url": "not-a-url",
            "fields": [
                {
                    "field_uid": "0",
                    "tag": "input",
                    "input_type": "text",
                    "label_text": "Email",
                }
            ],
        }
        resp = await authed_client.post(f"{BASE}/autofill/map", json=body)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_field_uid_must_be_digits_422(self, authed_client):
        body = _single_field_body()
        body["fields"][0]["field_uid"] = "abc"
        resp = await authed_client.post(f"{BASE}/autofill/map", json=body)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_duplicate_field_uid_422(self, authed_client):
        body = {
            "page_url": "https://example.com/apply",
            "fields": [
                {
                    "field_uid": "0",
                    "tag": "input",
                    "input_type": "text",
                    "label_text": "A",
                },
                {
                    "field_uid": "0",
                    "tag": "input",
                    "input_type": "text",
                    "label_text": "B",
                },
            ],
        }
        resp = await authed_client.post(f"{BASE}/autofill/map", json=body)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_more_than_80_fields_422(self, authed_client):
        fields = [
            {
                "field_uid": str(i),
                "tag": "input",
                "input_type": "text",
                "label_text": f"f{i}",
            }
            for i in range(81)
        ]
        resp = await authed_client.post(
            f"{BASE}/autofill/map",
            json={"page_url": "https://example.com/a", "fields": fields},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_extras_more_than_16_keys_422(self, authed_client):
        extras = {f"k{i}": "v" for i in range(17)}
        resp = await authed_client.post(
            f"{BASE}/autofill/map",
            json=_single_field_body(extras=extras),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_rate_limit_429_and_retry_after(self, authed_client):
        blocked = RateLimitResult(allowed=False, limit=15, remaining=0, reset_seconds=120)
        with patch("api.extension_autofill.check_rate_limit_with_headers", AsyncMock(return_value=blocked)):
            resp = await authed_client.post(f"{BASE}/autofill/map", json=_single_field_body())
        assert resp.status_code == 429
        data = resp.json()
        assert data.get("error_code") == "RATE_4001"
        assert resp.headers.get("Retry-After") == "120"

    @pytest.mark.asyncio
    async def test_no_api_key_CFG_6001(self, authed_client):
        with (
            patch("api.extension_autofill._get_user_api_key", AsyncMock(return_value=None)),
            patch("api.extension_autofill._server_has_llm", return_value=False),
        ):
            resp = await authed_client.post(f"{BASE}/autofill/map", json=_single_field_body())
        assert resp.status_code == 422
        assert resp.json().get("error_code") == "CFG_6001"

    @pytest.mark.asyncio
    async def test_user_not_found_404(self, authed_client):
        """JWT user id has no DB row — rare after account deletion."""
        with (
            patch("api.extension_autofill._get_user_api_key", AsyncMock(return_value=None)),
            patch("api.extension_autofill._server_has_llm", return_value=True),
            patch("api.extension_autofill.get_cached_tool_result", AsyncMock(return_value=None)),
        ):
            resp = await authed_client.post(f"{BASE}/autofill/map", json=_single_field_body())
        assert resp.status_code == 404
        assert resp.json().get("error_code") == "RES_3001"

    @pytest.mark.asyncio
    async def test_legacy_prefix_same_behavior_422(self, authed_client):
        body = {"page_url": "bad", "fields": [{"field_uid": "0", "tag": "input", "input_type": "text", "label_text": "x"}]}
        resp = await authed_client.post(f"{LEGACY_BASE}/autofill/map", json=body)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_cache_hit_filters_unknown_field_uid(self, authed_client_with_user):
        """Stale cache entries for unknown field_uids must not be returned."""
        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token,
            sec.jwt_config["secret_key"],
            algorithms=[sec.jwt_config["algorithm"]],
        )
        uid = uuid.UUID(payload["sub"])

        async with _NullSessionLocal() as session:
            await session.execute(update(User).where(User.id == uid).values(profile_completed=True))
            session.add(
                UserProfile(
                    id=uuid.uuid4(),
                    user_id=uid,
                    professional_title="Engineer",
                    years_experience=3,
                    summary="Cache test.",
                    city="X",
                    state="Y",
                    country="Z",
                )
            )
            await session.commit()

        mock_user = _complete_user_override(uid, payload)

        app.dependency_overrides[get_current_user] = mock_user
        app.dependency_overrides[get_current_user_with_complete_profile] = mock_user

        stale_cache = {
            "assignments": [
                {"field_uid": "0", "value": "ok", "label_text": "First"},
                {"field_uid": "99", "value": "leak", "label_text": "Ghost"},
            ],
            "skipped": [{"field_uid": "99", "reason": "nope"}],
            "generated_at": "2026-01-01T00:00:00+00:00",
        }

        try:
            with (
                patch("api.extension_autofill.get_cached_tool_result", AsyncMock(return_value=stale_cache)),
                patch("api.extension_autofill.get_gemini_client", AsyncMock()),
                patch("api.extension_autofill._get_user_api_key", AsyncMock(return_value=None)),
                patch("api.extension_autofill._server_has_llm", return_value=True),
            ):
                resp = await authed_client_with_user.post(f"{BASE}/autofill/map", json=_single_field_body())
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_current_user_with_complete_profile, None)

        assert resp.status_code == 200
        data = resp.json()
        uids = [a["field_uid"] for a in data["assignments"]]
        assert "0" in uids
        assert "99" not in uids
        assert all(s.get("field_uid") != "99" for s in data.get("skipped", []))

    @pytest.mark.asyncio
    async def test_map_returns_assignments(self, authed_client_with_user):
        uid = await _ensure_profile_for_token(authed_client_with_user)
        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token,
            sec.jwt_config["secret_key"],
            algorithms=[sec.jwt_config["algorithm"]],
        )

        mock_user = _complete_user_override(uid, payload)
        app.dependency_overrides[get_current_user] = mock_user
        app.dependency_overrides[get_current_user_with_complete_profile] = mock_user

        mock_client = MagicMock()
        mock_client.generate = AsyncMock(
            return_value={
                "response": '{"assignments":[{"field_uid":"0","value":"Autofill Test User"}],'
                '"skipped":[]}',
                "done": True,
            }
        )

        try:
            with (
                patch("api.extension_autofill.get_cached_tool_result", AsyncMock(return_value=None)),
                patch("api.extension_autofill.cache_tool_result", AsyncMock(return_value=True)),
                patch("api.extension_autofill.get_gemini_client", AsyncMock(return_value=mock_client)),
                patch("api.extension_autofill._get_user_api_key", AsyncMock(return_value=None)),
                patch("api.extension_autofill._server_has_llm", return_value=True),
            ):
                resp = await authed_client_with_user.post(f"{BASE}/autofill/map", json=_single_field_body(extras={}))
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_current_user_with_complete_profile, None)

        assert resp.status_code == 200
        data = resp.json()
        assert "assignments" in data
        assert len(data["assignments"]) >= 1
        assert data["assignments"][0]["field_uid"] == "0"
        assert "warnings" in data
        mock_client.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_gemini_error_returns_503(self, authed_client_with_user):
        uid = await _ensure_profile_for_token(authed_client_with_user, summary="Gemini error path.")
        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token,
            sec.jwt_config["secret_key"],
            algorithms=[sec.jwt_config["algorithm"]],
        )

        mock_user = _complete_user_override(uid, payload)
        app.dependency_overrides[get_current_user] = mock_user
        app.dependency_overrides[get_current_user_with_complete_profile] = mock_user

        mock_client = MagicMock()
        mock_client.generate = AsyncMock(side_effect=GeminiError("upstream failure", status_code=503))

        try:
            with (
                patch("api.extension_autofill.get_cached_tool_result", AsyncMock(return_value=None)),
                patch("api.extension_autofill.get_gemini_client", AsyncMock(return_value=mock_client)),
                patch("api.extension_autofill._get_user_api_key", AsyncMock(return_value=None)),
                patch("api.extension_autofill._server_has_llm", return_value=True),
            ):
                resp = await authed_client_with_user.post(f"{BASE}/autofill/map", json=_single_field_body())
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_current_user_with_complete_profile, None)

        assert resp.status_code == 503
        assert resp.json().get("error_code") == "EXT_5002"

    @pytest.mark.asyncio
    async def test_unparseable_llm_response_503(self, authed_client_with_user):
        uid = await _ensure_profile_for_token(authed_client_with_user, summary="Parse fail path.")
        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token,
            sec.jwt_config["secret_key"],
            algorithms=[sec.jwt_config["algorithm"]],
        )

        mock_user = _complete_user_override(uid, payload)
        app.dependency_overrides[get_current_user] = mock_user
        app.dependency_overrides[get_current_user_with_complete_profile] = mock_user

        mock_client = MagicMock()
        mock_client.generate = AsyncMock(return_value={"response": "NOT JSON {{{", "done": True})

        try:
            with (
                patch("api.extension_autofill.get_cached_tool_result", AsyncMock(return_value=None)),
                patch("api.extension_autofill.get_gemini_client", AsyncMock(return_value=mock_client)),
                patch("api.extension_autofill._get_user_api_key", AsyncMock(return_value=None)),
                patch("api.extension_autofill._server_has_llm", return_value=True),
            ):
                resp = await authed_client_with_user.post(f"{BASE}/autofill/map", json=_single_field_body())
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_current_user_with_complete_profile, None)

        assert resp.status_code == 503
        assert resp.json().get("error_code") == "EXT_5002"

    @pytest.mark.asyncio
    async def test_assignment_truncated_to_field_max_length(self, authed_client_with_user):
        uid = await _ensure_profile_for_token(authed_client_with_user, summary="Max length truncation.")
        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token,
            sec.jwt_config["secret_key"],
            algorithms=[sec.jwt_config["algorithm"]],
        )

        mock_user = _complete_user_override(uid, payload)
        app.dependency_overrides[get_current_user] = mock_user
        app.dependency_overrides[get_current_user_with_complete_profile] = mock_user

        mock_client = MagicMock()
        mock_client.generate = AsyncMock(
            return_value={
                "response": '{"assignments":[{"field_uid":"0","value":"TOOLONG"}],'
                '"skipped":[]}',
                "done": True,
            }
        )

        body = {
            "page_url": "https://careers.example.com/apply",
            "fields": [
                {
                    "field_uid": "0",
                    "tag": "input",
                    "input_type": "text",
                    "label_text": "Code",
                    "max_length": 3,
                }
            ],
        }

        try:
            with (
                patch("api.extension_autofill.get_cached_tool_result", AsyncMock(return_value=None)),
                patch("api.extension_autofill.cache_tool_result", AsyncMock(return_value=True)),
                patch("api.extension_autofill.get_gemini_client", AsyncMock(return_value=mock_client)),
                patch("api.extension_autofill._get_user_api_key", AsyncMock(return_value=None)),
                patch("api.extension_autofill._server_has_llm", return_value=True),
            ):
                resp = await authed_client_with_user.post(f"{BASE}/autofill/map", json=body)
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_current_user_with_complete_profile, None)

        assert resp.status_code == 200
        assert resp.json()["assignments"][0]["value"] == "TOO"

    @pytest.mark.asyncio
    async def test_llm_skipped_unknown_field_uid_dropped(self, authed_client_with_user):
        uid = await _ensure_profile_for_token(authed_client_with_user, summary="Skipped filter.")
        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token,
            sec.jwt_config["secret_key"],
            algorithms=[sec.jwt_config["algorithm"]],
        )

        mock_user = _complete_user_override(uid, payload)
        app.dependency_overrides[get_current_user] = mock_user
        app.dependency_overrides[get_current_user_with_complete_profile] = mock_user

        mock_client = MagicMock()
        mock_client.generate = AsyncMock(
            return_value={
                "response": '{"assignments":[],"skipped":['
                '{"field_uid":"0","reason":"skip a"},'
                '{"field_uid":"99","reason":"skip ghost"}'
                "]}",
                "done": True,
            }
        )

        body = {
            "page_url": "https://careers.example.com/apply",
            "fields": [
                {
                    "field_uid": "0",
                    "tag": "input",
                    "input_type": "text",
                    "label_text": "Referral code (optional)",
                }
            ],
        }

        try:
            with (
                patch("api.extension_autofill.get_cached_tool_result", AsyncMock(return_value=None)),
                patch("api.extension_autofill.cache_tool_result", AsyncMock(return_value=True)),
                patch("api.extension_autofill.get_gemini_client", AsyncMock(return_value=mock_client)),
                patch("api.extension_autofill._get_user_api_key", AsyncMock(return_value=None)),
                patch("api.extension_autofill._server_has_llm", return_value=True),
            ):
                resp = await authed_client_with_user.post(f"{BASE}/autofill/map", json=body)
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_current_user_with_complete_profile, None)

        assert resp.status_code == 200
        skipped = resp.json().get("skipped") or []
        uids = [s["field_uid"] for s in skipped]
        assert "0" in uids
        assert "99" not in uids


class TestExtensionAutofillHelpers:
    """Pure helper coverage (importable without HTTP)."""

    def test_validate_assignments_ignores_unknown_uid(self):
        from api.extension_autofill import AutofillFieldIn, _validate_assignments

        fields = {
            "0": AutofillFieldIn(field_uid="0", tag="input", input_type="text", label_text="A"),
        }
        raw = [
            {"field_uid": "0", "value": "ok"},
            {"field_uid": "7", "value": "nope"},
        ]
        out = _validate_assignments(raw, fields)
        assert len(out) == 1
        assert out[0].field_uid == "0"

    def test_validate_assignments_decodes_html_entities(self):
        from api.extension_autofill import AutofillFieldIn, _validate_assignments

        fields = {
            "0": AutofillFieldIn(field_uid="0", tag="textarea", label_text="Why join"),
        }
        raw = [{"field_uid": "0", "value": "Roboflow&#x27;s mission"}]
        out = _validate_assignments(raw, fields)
        assert out[0].value == "Roboflow's mission"


class TestExtensionAutofillDeterministicRules:
    """Profile-backed rules applied before returning assignments."""

    def _field(self, uid: str, **kwargs):
        from api.extension_autofill import AutofillFieldIn

        base = {
            "field_uid": uid,
            "tag": "input",
            "input_type": "text",
            "label_text": "",
        }
        base.update(kwargs)
        return AutofillFieldIn(**base)

    def _bundle(self, **profile_overrides):
        prof = {
            "country": "United States",
            "city": "Brooklyn",
            "state": "NY",
            "willing_to_relocate": True,
            "requires_visa_sponsorship": False,
            "work_authorization": "us_citizen",
            "desired_company_sizes": ["startup", "medium"],
        }
        prof.update(profile_overrides)
        return {
            "email": "eliornataflackritz@gmail.com",
            "full_name": "Elior Nataf Lackritz",
            "profile": prof,
        }

    def test_full_name_verbatim_on_name_field(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field("0", label_text="Name*")
        assert deterministic_value_for_field(f, self._bundle()) == "Elior Nataf Lackritz"

    def test_us_based_yes_from_country(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "1",
            input_type="yes_no_buttons",
            tag="div",
            label_text="Are you currently based in the United States?*",
            options=[{"value": "Yes", "text": "Yes"}, {"value": "No", "text": "No"}],
        )
        assert deterministic_value_for_field(f, self._bundle()) == "Yes"

    def test_last_name_includes_all_family_tokens(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field("301", input_type="text", label_text="Last Name*")
        bundle = {
            "email": "e@e.com",
            "full_name": "Elior Nataf Lackritz",
            "profile": {},
        }
        assert deterministic_value_for_field(f, bundle) == "Nataf Lackritz"

    def test_kalepa_visa_sponsorship_combobox_no_options(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "302",
            input_type="combobox",
            tag="input",
            label_text="Will you now or at any time in the future require visa sponsorship? *",
            options=None,
        )
        assert (
            deterministic_value_for_field(
                f,
                self._bundle(
                    requires_visa_sponsorship=False,
                    work_authorization="has_work_authorization",
                ),
            )
            == "No"
        )

    def test_oscar_greenhouse_sponsorship_no_when_not_required(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "304",
            input_type="combobox",
            tag="input",
            label_text=(
                "Do you now, or will you in the future, require sponsorship for employment "
                "visa status (e.g., H-1B visa status, etc.) to work legally for Oscar "
                "in the United States?*"
            ),
            options=[{"value": "Yes", "text": "Yes"}, {"value": "No", "text": "No"}],
        )
        assert (
            deterministic_value_for_field(
                f,
                self._bundle(
                    requires_visa_sponsorship=False,
                    work_authorization="has_work_authorization",
                ),
            )
            == "No"
        )

    def test_probook_require_sponsorship_to_work_us(self):
        """Ashby Probook — 'sponsorship to work' without the word visa in the label."""
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "303",
            input_type="yes_no_buttons",
            tag="div",
            label_text=(
                "Will you now or in the future require sponsorship to work in the US?"
            ),
            options=[{"value": "Yes", "text": "Yes"}, {"value": "No", "text": "No"}],
        )
        assert (
            deterministic_value_for_field(
                f,
                self._bundle(
                    requires_visa_sponsorship=False,
                    work_authorization="has_work_authorization",
                ),
            )
            == "No"
        )

    def test_sponsorship_from_profile_flag(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "2",
            input_type="yes_no_buttons",
            tag="div",
            label_text="Do you require employment sponsorship to work in the country where this job is located?*",
            options=[{"value": "Yes", "text": "Yes"}, {"value": "No", "text": "No"}],
        )
        assert deterministic_value_for_field(f, self._bundle()) == "No"
        assert (
            deterministic_value_for_field(
                f,
                self._bundle(requires_visa_sponsorship=True),
            )
            == "Yes"
        )

    def test_h1b_sponsorship_combobox(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "99",
            input_type="combobox",
            tag="input",
            label_text="Would you require a new H-1B sponsorship to work with us?*",
            options=[{"value": "Yes", "text": "Yes"}, {"value": "No", "text": "No"}],
        )
        assert deterministic_value_for_field(f, self._bundle()) == "No"
        assert (
            deterministic_value_for_field(
                f,
                self._bundle(requires_visa_sponsorship=True),
            )
            == "Yes"
        )

    def test_years_experience_range_bucket(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "100",
            input_type="combobox",
            tag="input",
            label_text="Years of Industry Experience",
            options=[
                {"value": "a", "text": "3-5"},
                {"value": "b", "text": "5-7"},
                {"value": "c", "text": "8-10"},
            ],
        )
        assert deterministic_value_for_field(f, self._bundle(years_experience=4)) == "3-5"

    def test_years_experience_nearest_bucket_when_no_exact_range(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "103",
            input_type="combobox",
            tag="input",
            label_text="Years of Industry Experience",
            options=[
                {"value": "b", "text": "5-7"},
                {"value": "c", "text": "8-10"},
                {"value": "d", "text": "11+"},
            ],
        )
        assert deterministic_value_for_field(f, self._bundle(years_experience=4)) == "5-7"

    def test_nyc_tri_state_commute_yes_when_hoboken(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "401",
            input_type="radio",
            tag="input",
            label_text=(
                "This position is based in NYC. Are you located in the tri-state area "
                "and able to commute into the NYC office 2x a week? *"
            ),
            options=[{"value": "yes", "text": "Yes"}, {"value": "no", "text": "No"}],
        )
        assert (
            deterministic_value_for_field(
                f,
                self._bundle(city="Hoboken", state="NJ", willing_to_relocate=False),
            )
            == "Yes"
        )

    def test_central_office_onsite_nyc_without_options(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "101",
            input_type="combobox",
            tag="input",
            label_text="Are you open to working 4 days onsite in one of our central offices?*",
            options=None,
        )
        assert deterministic_value_for_field(f, self._bundle()) == "NYC"

    def test_central_office_onsite_office_picker(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "104",
            input_type="combobox",
            tag="input",
            label_text="Are you open to working 4 days onsite in one of our central offices?*",
            options=[
                {"value": "nyc", "text": "NYC"},
                {"value": "sf", "text": "SF"},
                {"value": "ldn", "text": "London"},
                {"value": "rem", "text": "Remote only"},
            ],
        )
        assert deterministic_value_for_field(f, self._bundle()) == "NYC"

    def test_central_office_relocation_commuting_distance(self):
        from api.extension_autofill import AutofillSelectOption
        from api.extension_autofill_rules import deterministic_value_for_field

        opts = [
            AutofillSelectOption(
                value="a",
                text="Yes, and I currently live in the NYC Metropolitan Area.",
            ),
            AutofillSelectOption(
                value="b",
                text="Yes, and while I do not currently live in the NYC Metropolitan Area, I am open to relocation.",
            ),
            AutofillSelectOption(
                value="c",
                text="No, I cannot work in-office.",
            ),
        ]
        f = self._field(
            "3",
            input_type="radio",
            tag="input",
            label_text="Are you able to work in-person in New York, NY?*",
            options=opts,
        )
        val = deterministic_value_for_field(f, self._bundle())
        assert val is not None
        assert "currently live" in val.lower()

    def test_startup_yes_when_startup_preferred(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "4",
            input_type="yes_no_buttons",
            tag="div",
            label_text="Are you prepared to work at a startup?*",
            options=[{"value": "Yes", "text": "Yes"}, {"value": "No", "text": "No"}],
        )
        assert deterministic_value_for_field(f, self._bundle()) == "Yes"
        assert (
            deterministic_value_for_field(
                f,
                self._bundle(desired_company_sizes=["Startup (1-10 employees)"]),
            )
            == "Yes"
        )

    def test_startup_from_ashby_helper_text_label(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "5",
            input_type="yes_no_buttons",
            tag="div",
            label_text=(
                "Giga is trying to build a generational company, which is extremely difficult. "
                "We work long hours and have a strong performance culture."
            ),
            options=[{"value": "Yes", "text": "Yes"}, {"value": "No", "text": "No"}],
        )
        assert deterministic_value_for_field(f, self._bundle()) == "Yes"

    def test_merge_deterministic_overrides_llm_name(self):
        from api.extension_autofill import AutofillFieldIn, _finalize_autofill_response

        fields = [
            AutofillFieldIn(field_uid="0", tag="input", input_type="text", label_text="Name*"),
        ]
        fields_by_uid = {f.field_uid: f for f in fields}
        llm_raw = [{"field_uid": "0", "value": "Elior Lackritz"}]
        assignments, skipped = _finalize_autofill_response(
            llm_raw,
            [],
            fields_by_uid,
            self._bundle(),
            fields,
        )
        assert len(assignments) == 1
        assert assignments[0].value == "Elior Nataf Lackritz"
        assert skipped == []

    def test_first_last_middle_name_split(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        bundle = self._bundle()
        first = self._field("10", label_text="First name*")
        last = self._field("11", label_text="Last name*")
        middle = self._field("12", label_text="Middle name")
        all_name_fields = [first, last, middle]
        assert deterministic_value_for_field(first, bundle, all_fields=all_name_fields) == "Elior"
        assert deterministic_value_for_field(last, bundle, all_fields=all_name_fields) == "Lackritz"
        assert deterministic_value_for_field(middle, bundle, all_fields=all_name_fields) == "Nataf"

    def test_email_from_profile_bundle(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field("13", input_type="email", label_text="Email*")
        assert deterministic_value_for_field(f, self._bundle()) == "eliornataflackritz@gmail.com"

    def test_location_city_from_profile(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "320",
            tag="input",
            input_type="text",
            label_text="Location (City)",
        )
        assert (
            deterministic_value_for_field(
                f,
                self._bundle(city="Hoboken", state="NJ"),
            )
            == "Hoboken, NJ"
        )

    def test_ashby_location_label_from_profile(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "322",
            tag="input",
            input_type="combobox",
            label_text="Location",
        )
        assert (
            deterministic_value_for_field(
                f,
                self._bundle(city="Hoboken", state="NJ"),
            )
            == "Hoboken, NJ"
        )

    def test_ashby_location_from_systemfield_name_attr(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "324",
            tag="input",
            input_type="combobox",
            label_text="Start typing...",
            placeholder="Start typing...",
            name_attr="_systemfield_location",
        )
        assert (
            deterministic_value_for_field(
                f,
                self._bundle(city="Hoboken", state="NJ"),
            )
            == "Hoboken, NJ"
        )

    def test_sentilink_sponsor_for_visa_wording(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "323",
            input_type="yes_no_buttons",
            tag="div",
            label_text=(
                "Will you now or in the future require SentiLink to sponsor you "
                "for an employment visa (e.g.H-1B, TN, E-3, O-1, etc)?"
            ),
            options=[{"value": "Yes", "text": "Yes"}, {"value": "No", "text": "No"}],
        )
        assert deterministic_value_for_field(f, self._bundle()) == "No"
        assert (
            deterministic_value_for_field(
                f,
                self._bundle(requires_visa_sponsorship=True),
            )
            == "Yes"
        )

    def test_relocation_screening_not_city_field(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "321",
            input_type="combobox",
            label_text="Are you willing to relocate to our New York office?*",
            options=[{"value": "yes", "text": "Yes"}],
        )
        assert deterministic_value_for_field(
            f, self._bundle(city="Hoboken", state="NJ", willing_to_relocate=True)
        ) != "Hoboken, NJ"

    def test_country_combobox_united_states(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field("15", input_type="combobox", label_text="Country")
        assert deterministic_value_for_field(f, self._bundle(country="US")) == "United States"

    def test_website_prefers_portfolio_over_github(self):
        from api.extension_autofill_rules import build_deterministic_raw_assignments

        fields = [
            self._field("16", label_text="Website — Website"),
        ]
        out = build_deterministic_raw_assignments(
            fields,
            self._bundle(
                portfolio_url="https://example.dev",
                github_url="https://github.com/eliornl",
            ),
        )
        assert out == [
            {
                "field_uid": "16",
                "value": "https://example.dev",
                "label_text": "Website — Website",
                "duplicate_label_index": 0,
            }
        ]

    def test_website_falls_back_to_github_without_github_field(self):
        from api.extension_autofill_rules import build_deterministic_raw_assignments

        fields = [self._field("17", label_text="Website — Website")]
        out = build_deterministic_raw_assignments(
            fields,
            self._bundle(portfolio_url="", github_url="https://github.com/eliornl"),
        )
        assert out == [
            {
                "field_uid": "17",
                "value": "https://github.com/eliornl",
                "label_text": "Website — Website",
                "duplicate_label_index": 0,
            }
        ]

    def test_website_uses_github_when_form_has_github_username_field(self):
        from api.extension_autofill_rules import build_deterministic_raw_assignments

        fields = [
            self._field("330", label_text="Website"),
            self._field("331", label_text="GitHub Username*"),
        ]
        out = build_deterministic_raw_assignments(
            fields,
            self._bundle(portfolio_url="", github_url="https://github.com/eliornl"),
        )
        by_uid = {x["field_uid"]: x["value"] for x in out}
        assert by_uid["330"] == "https://github.com/eliornl"
        assert by_uid["331"] == "eliornl"

    def test_github_username_from_url(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field("332", input_type="text", label_text="GitHub Username*")
        assert (
            deterministic_value_for_field(
                f,
                self._bundle(github_url="https://github.com/eliornl"),
            )
            == "eliornl"
        )

    def test_acknowledge_statement_yes(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "18",
            input_type="combobox",
            label_text="Acknowledge, confirm, and agree to the following statements. *",
        )
        assert deterministic_value_for_field(f, self._bundle()) == "Yes"

    def test_oscar_work_location_acknowledgement_combobox(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        yes_opt = "Yes, I acknowledge the work location expectations for this role."
        f = self._field(
            "305",
            input_type="combobox",
            label_text=(
                "Do you acknowledge the work location expectations listed on this job posting?*"
            ),
            options=[{"value": yes_opt, "text": yes_opt}, {"value": "No", "text": "No"}],
        )
        assert deterministic_value_for_field(f, self._bundle()) == yes_opt

    def test_inspiren_data_consent_checkbox_checked(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "310",
            tag="input",
            input_type="checkbox",
            label_text=(
                "By checking this box, I agree to allow Inspiren to store and process my data "
                "for the purpose of considering my eligibility regarding my current application "
                "for employment.*"
            ),
        )
        assert deterministic_value_for_field(f, self._bundle()) == "checked"

    def test_future_opportunities_consent_checkbox_checked(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "311",
            tag="input",
            input_type="checkbox",
            label_text=(
                "By checking this box, I agree to allow Inspiren to retain my data for future "
                "opportunities for employment for up to 120 days after the conclusion of "
                "consideration of my current application for employment."
            ),
        )
        assert deterministic_value_for_field(f, self._bundle()) == "checked"

    def test_marketing_checkbox_not_auto_checked(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "312",
            tag="input",
            input_type="checkbox",
            label_text="Subscribe to our newsletter for job search tips",
        )
        assert deterministic_value_for_field(f, self._bundle()) is None

    def test_five_plus_years_yes_no_combobox(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "200",
            input_type="combobox",
            label_text="Do you have 5+ years of experience?*",
            options=[
                {"value": "yes", "text": "Yes"},
                {"value": "no", "text": "No"},
            ],
        )
        assert deterministic_value_for_field(f, self._bundle(years_experience=4)) == "Yes"
        assert deterministic_value_for_field(f, self._bundle(years_experience=3)) == "No"
        assert deterministic_value_for_field(f, self._bundle(years_experience=5)) == "Yes"

    def test_salary_expectations_from_profile_range(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "201",
            input_type="text",
            label_text="What are your salary expectations? (in $)*",
        )
        assert (
            deterministic_value_for_field(
                f,
                self._bundle(desired_salary_range={"min": 150000, "max": 200000}),
            )
            == "150000-200000"
        )

    def test_salary_expectations_greenhouse_textarea(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "203",
            tag="textarea",
            input_type=None,
            label_text="What are your salary expectations? (in $)*",
        )
        assert (
            deterministic_value_for_field(
                f,
                self._bundle(desired_salary_range={"min": 200000, "max": 220000}),
            )
            == "200000-220000"
        )

    def test_start_timeline_default_two_weeks(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "205",
            tag="textarea",
            input_type=None,
            label_text="How quickly are you looking to start a new role? *",
        )
        assert (
            deterministic_value_for_field(f, self._bundle())
            == "I can start a new role in 2 weeks."
        )

    def test_five_plus_years_yes_no_without_scraped_options(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "204",
            input_type="combobox",
            tag="input",
            label_text="Do you have 5+ years of experience?*",
            options=None,
        )
        assert deterministic_value_for_field(f, self._bundle(years_experience=4)) == "Yes"
        assert deterministic_value_for_field(f, self._bundle(years_experience=3)) == "No"

    def test_salary_expectations_skipped_when_profile_empty(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "202",
            input_type="text",
            label_text="What are your salary expectations? (in $)*",
        )
        assert deterministic_value_for_field(f, self._bundle()) is None

    def test_years_experience_fallback_without_options(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "105",
            input_type="combobox",
            tag="input",
            label_text="Years of Industry Experience",
            options=None,
        )
        assert deterministic_value_for_field(f, self._bundle(years_experience=4)) == "5-7"

    def test_degree_llb_maps_to_bachelors_on_greenhouse(self):
        from api.extension_autofill_rules import build_deterministic_raw_assignments

        fields = [
            self._field(
                "106",
                input_type="combobox",
                label_text="Degree",
                duplicate_label_index=0,
                options=[
                    {"value": "bs", "text": "Bachelor's Degree"},
                    {"value": "jd", "text": "Juris Doctor (J.D.)"},
                    {"value": "ba", "text": "Bachelor of Arts (BA)"},
                ],
            ),
        ]
        out = build_deterministic_raw_assignments(
            fields,
            self._bundle(education=[{"degree": "LLB", "field_of_study": "Law"}]),
        )
        assert out[0]["value"] == "Bachelor's Degree"

    def test_degree_llb_without_generic_bachelor_uses_jd(self):
        from api.extension_autofill_rules import build_deterministic_raw_assignments

        fields = [
            self._field(
                "107",
                input_type="combobox",
                label_text="Degree",
                duplicate_label_index=0,
                options=[
                    {"value": "jd", "text": "Juris Doctor (J.D.)"},
                    {"value": "ba", "text": "Bachelor of Arts (BA)"},
                ],
            ),
        ]
        out = build_deterministic_raw_assignments(
            fields,
            self._bundle(education=[{"degree": "LLB", "field_of_study": "Law"}]),
        )
        assert out[0]["value"] == "Juris Doctor (J.D.)"

    def test_degree_bachelor_of_arts_alias(self):
        from api.extension_autofill_rules import _align_degree_to_form_options

        assert _align_degree_to_form_options("BA", []) == "Bachelor's Degree"
        assert _align_degree_to_form_options("LLB", []) == "Bachelor's Degree"

    def test_degree_greenhouse_generic_options(self):
        from api.extension_autofill_rules import _align_degree_to_form_options
        from utils.degree_aliases import pick_degree_from_options

        greenhouse = [
            "Associate's Degree",
            "Bachelor's Degree",
            "Doctor of Medicine (M.D.)",
            "Doctor of Philosophy (Ph.D.)",
            "Engineer's Degree",
            "High School",
            "Juris Doctor (J.D.)",
            "Master of Business Administration (M.B.A.)",
        ]
        assert pick_degree_from_options("BA", greenhouse) == "Bachelor's Degree"
        assert pick_degree_from_options("LLB", greenhouse) == "Bachelor's Degree"
        assert pick_degree_from_options("Law", greenhouse) == "Bachelor's Degree"
        assert pick_degree_from_options("LLB", greenhouse + ["Bachelor's Degree"]) == "Bachelor's Degree"
        assert _align_degree_to_form_options("Bachelor of Arts (BA)", greenhouse) == "Bachelor's Degree"

    def test_degree_alias_table_covers_common_abbreviations(self):
        from api.extension_autofill_rules import _align_degree_to_form_options
        from utils.degree_aliases import classify_degree, pick_degree_from_options

        options = [
            "Associate's Degree",
            "Bachelor of Arts (BA)",
            "Bachelor of Science (BS)",
            "Bachelor's Degree",
            "Master of Arts (MA)",
            "Master of Business Administration (M.B.A.)",
            "Master of Science (MS)",
            "Master's Degree",
            "Juris Doctor (J.D.)",
            "Doctor of Philosophy (Ph.D.)",
        ]

        assert classify_degree("BSc").key == "bs"
        assert classify_degree("MSc").key == "ms"
        assert classify_degree("MBA").key == "mba"
        assert classify_degree("Ph.D.").key == "phd"
        assert classify_degree("A.A.S.").key == "associate"
        assert pick_degree_from_options("BSc", options) == "Bachelor of Science (BS)"
        assert pick_degree_from_options("MBA", options) == "Master of Business Administration (M.B.A.)"
        assert pick_degree_from_options("MA", options) == "Master of Arts (MA)"
        assert pick_degree_from_options("Bachelor's Degree", options) == "Bachelor's Degree"
        assert _align_degree_to_form_options("MSc", []) == "Master of Science (MS)"
        assert _align_degree_to_form_options("Bachelor's", []) == "Bachelor's Degree"

    def test_education_degree_and_discipline_by_index(self):
        from api.extension_autofill_rules import build_deterministic_raw_assignments

        fields = [
            self._field("19", input_type="combobox", label_text="Degree", duplicate_label_index=0),
            self._field("20", input_type="combobox", label_text="Discipline", duplicate_label_index=0),
            self._field("21", input_type="combobox", label_text="Degree", duplicate_label_index=1),
            self._field("22", input_type="combobox", label_text="Discipline", duplicate_label_index=1),
        ]
        out = build_deterministic_raw_assignments(
            fields,
            self._bundle(
                education=[
                    {"degree": "Bachelor of Arts (BA)", "field_of_study": "Economics"},
                    {"degree": "Master of Science (MS)", "field_of_study": "Computer Science"},
                ]
            ),
        )
        by_uid = {item["field_uid"]: item["value"] for item in out}
        assert by_uid["19"] == "Bachelor's Degree"
        assert by_uid["20"] == "Economics"
        assert by_uid["21"] == "Master of Science (MS)"
        assert by_uid["22"] == "Computer Science"

    def test_central_office_relocation_local_metro_without_options(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "23",
            input_type="combobox",
            label_text=(
                "If you are currently not local to one of our central offices, "
                "are you willing to relocate?*"
            ),
        )
        val = deterministic_value_for_field(
            f,
            self._bundle(city="Brooklyn", state="NY", willing_to_relocate=True),
        )
        assert val == "N/A - Within Commuting Distance"

    def test_central_office_relocation_willing_without_options(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "24",
            input_type="combobox",
            label_text=(
                "If you are currently not local to one of our central offices, "
                "are you willing to relocate?*"
            ),
        )
        val = deterministic_value_for_field(
            f,
            self._bundle(city="Austin", state="TX", willing_to_relocate=True),
        )
        assert val == "Yes"

    def test_nyc_relocation_when_not_in_metro(self):
        from api.extension_autofill import AutofillSelectOption
        from api.extension_autofill_rules import deterministic_value_for_field

        opts = [
            AutofillSelectOption(
                value="a",
                text="Yes, and I currently live in the NYC Metropolitan Area.",
            ),
            AutofillSelectOption(
                value="b",
                text="Yes, and while I do not currently live in the NYC Metropolitan Area, I am open to relocation.",
            ),
            AutofillSelectOption(
                value="c",
                text="No, I cannot work in-office.",
            ),
        ]
        f = self._field(
            "14",
            input_type="radio",
            tag="input",
            label_text="Are you able to work in-person in New York, NY?*",
            options=opts,
        )
        val = deterministic_value_for_field(
            f,
            self._bundle(city="Austin", state="TX", willing_to_relocate=True),
        )
        assert val is not None
        assert "relocation" in val.lower()

    def test_missing_required_warnings(self):
        from api.extension_autofill import AutofillAssignmentOut, AutofillFieldIn, _missing_required_warnings

        fields = [
            AutofillFieldIn(
                field_uid="0",
                tag="input",
                input_type="text",
                label_text="Name*",
                required=True,
            ),
            AutofillFieldIn(
                field_uid="1",
                tag="div",
                input_type="yes_no_buttons",
                label_text="Are you currently based in the United States?*",
                required=True,
            ),
        ]
        assignments = [AutofillAssignmentOut(field_uid="0", value="Elior Nataf Lackritz", label_text="Name*")]
        warnings = _missing_required_warnings(fields, assignments)
        assert len(warnings) == 1
        assert "1 required field" in warnings[0]
        assert "United States" in warnings[0]

    def test_merge_overlay_wins_on_conflict(self):
        from api.extension_autofill_rules import merge_assignment_dicts

        merged = merge_assignment_dicts(
            [{"field_uid": "0", "value": "LLM"}],
            [{"field_uid": "0", "value": "RULE"}],
        )
        assert len(merged) == 1
        assert merged[0]["value"] == "RULE"


class TestExtensionAutofillDeterministicEndpoint:
    """HTTP path: deterministic rules apply even when LLM returns empty or wrong values."""

    def _giga_like_body(self):
        return {
            "page_url": "https://jobs.example.com/giga/apply",
            "fields": [
                {
                    "field_uid": "0",
                    "tag": "input",
                    "input_type": "text",
                    "label_text": "Name*",
                    "required": True,
                },
                {
                    "field_uid": "1",
                    "tag": "div",
                    "input_type": "yes_no_buttons",
                    "label_text": "Are you currently based in the United States?*",
                    "required": True,
                    "options": [{"value": "Yes", "text": "Yes"}, {"value": "No", "text": "No"}],
                },
                {
                    "field_uid": "2",
                    "tag": "div",
                    "input_type": "yes_no_buttons",
                    "label_text": "Do you require employment sponsorship to work in the country where this job is located?*",
                    "required": True,
                    "options": [{"value": "Yes", "text": "Yes"}, {"value": "No", "text": "No"}],
                },
                {
                    "field_uid": "3",
                    "tag": "input",
                    "input_type": "radio",
                    "label_text": "Are you able to work in-person in New York, NY?*",
                    "required": True,
                    "options": [
                        {
                            "value": "a",
                            "text": "Yes, and I currently live in the NYC Metropolitan Area.",
                        },
                        {
                            "value": "b",
                            "text": "Yes, and while I do not currently live in the NYC Metropolitan Area, I am open to relocation.",
                        },
                        {"value": "c", "text": "No, I cannot work in-office."},
                    ],
                },
                {
                    "field_uid": "4",
                    "tag": "div",
                    "input_type": "yes_no_buttons",
                    "label_text": "Are you prepared to work at a startup?*",
                    "required": True,
                    "options": [{"value": "Yes", "text": "Yes"}, {"value": "No", "text": "No"}],
                },
            ],
        }

    @pytest.mark.asyncio
    async def test_endpoint_applies_deterministic_screening_when_llm_empty(self, authed_client_with_user):
        uid = await _ensure_profile_for_token(
            authed_client_with_user,
            summary="Hybrid autofill.",
            full_name="Elior Nataf Lackritz",
            city="Brooklyn",
            state="NY",
            country="United States",
            requires_visa_sponsorship=False,
            work_authorization="us_citizen",
            willing_to_relocate=True,
            desired_company_sizes=["startup", "medium"],
        )
        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token,
            sec.jwt_config["secret_key"],
            algorithms=[sec.jwt_config["algorithm"]],
        )
        mock_user = _complete_user_override(uid, payload)
        app.dependency_overrides[get_current_user] = mock_user
        app.dependency_overrides[get_current_user_with_complete_profile] = mock_user

        mock_client = MagicMock()
        mock_client.generate = AsyncMock(
            return_value={"response": '{"assignments":[],"skipped":[]}', "done": True}
        )

        try:
            with (
                patch("api.extension_autofill.get_cached_tool_result", AsyncMock(return_value=None)),
                patch("api.extension_autofill.cache_tool_result", AsyncMock(return_value=True)),
                patch("api.extension_autofill.get_gemini_client", AsyncMock(return_value=mock_client)),
                patch("api.extension_autofill._get_user_api_key", AsyncMock(return_value=None)),
                patch("api.extension_autofill._server_has_llm", return_value=True),
            ):
                resp = await authed_client_with_user.post(
                    f"{BASE}/autofill/map",
                    json=self._giga_like_body(),
                )
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_current_user_with_complete_profile, None)

        assert resp.status_code == 200
        by_uid = {a["field_uid"]: a["value"] for a in resp.json()["assignments"]}
        assert by_uid["0"] == "Elior Nataf Lackritz"
        assert by_uid["1"] == "Yes"
        assert by_uid["2"] == "No"
        assert "currently live" in by_uid["3"].lower()
        assert by_uid["4"] == "Yes"

    @pytest.mark.asyncio
    async def test_cache_hit_overrides_stale_llm_name(self, authed_client_with_user):
        uid = await _ensure_profile_for_token(
            authed_client_with_user,
            full_name="Elior Nataf Lackritz",
        )
        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token,
            sec.jwt_config["secret_key"],
            algorithms=[sec.jwt_config["algorithm"]],
        )
        mock_user = _complete_user_override(uid, payload)
        app.dependency_overrides[get_current_user] = mock_user
        app.dependency_overrides[get_current_user_with_complete_profile] = mock_user

        stale_cache = {
            "assignments": [{"field_uid": "0", "value": "Elior Lackritz"}],
            "skipped": [],
            "generated_at": "2026-01-01T00:00:00+00:00",
        }

        try:
            with (
                patch("api.extension_autofill.get_cached_tool_result", AsyncMock(return_value=stale_cache)),
                patch("api.extension_autofill.get_gemini_client", AsyncMock()),
                patch("api.extension_autofill._get_user_api_key", AsyncMock(return_value=None)),
                patch("api.extension_autofill._server_has_llm", return_value=True),
            ):
                resp = await authed_client_with_user.post(
                    f"{BASE}/autofill/map",
                    json=_single_field_body(
                        fields=[
                            {
                                "field_uid": "0",
                                "tag": "input",
                                "input_type": "text",
                                "label_text": "Name*",
                            }
                        ]
                    ),
                )
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_current_user_with_complete_profile, None)

        assert resp.status_code == 200
        assert resp.json()["assignments"][0]["value"] == "Elior Nataf Lackritz"


class TestExtensionAutofillHelperFunctions:
    """Pure helpers and profile bundle loading."""

    @pytest.mark.asyncio
    async def test_load_profile_bundle_truncates_summary_and_resume(
        self, authed_client_with_user,
    ):
        from api.extension_autofill import _load_profile_bundle
        from models.database import User, UserResumeAsset

        uid = await _ensure_profile_for_token(
            authed_client_with_user,
            summary="x" * 3000,
            work_experience=[{"title": f"Role {i}"} for i in range(20)],
        )
        async with _NullSessionLocal() as session:
            user_row = await session.get(User, uid)
            session.add(
                UserResumeAsset(
                    id=uuid.uuid4(),
                    user_id=uid,
                    original_filename="resume.pdf",
                    mime_type="application/pdf",
                    byte_size=1234,
                    storage_relative_path="users/resume.pdf",
                )
            )
            await session.commit()

        async with _NullSessionLocal() as session:
            user_row = await session.get(User, uid)
            bundle, prof_sig = await _load_profile_bundle(session, uid, user_row)
        assert bundle["resume_file"]["has_file"] is True
        assert len(bundle["profile"]["summary"]) <= 2501
        assert len(bundle["profile"]["work_experience"]) == 12
        assert prof_sig

    def test_sanitize_extras_and_build_prompt(self):
        from api.extension_autofill import _build_user_prompt, _sanitize_extras

        extras = _sanitize_extras({" source ": "value"})
        assert "source" in extras
        prompt = _build_user_prompt(
            [{"field_uid": "0", "label_text": "Name"}],
            {"full_name": "Jane"},
            extras,
            "https://example.com/apply",
        )
        assert "PROFILE_JSON" in prompt
        assert "Jane" in prompt

    def test_get_user_uuid_from_uuid_object(self):
        from api.extension_autofill import _get_user_uuid

        uid = uuid.uuid4()
        assert _get_user_uuid({"_id": uid}) == uid

    @pytest.mark.asyncio
    async def test_map_internal_error_on_unexpected_exception(self, authed_client_with_user):
        uid = await _ensure_profile_for_token(authed_client_with_user)
        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token,
            sec.jwt_config["secret_key"],
            algorithms=[sec.jwt_config["algorithm"]],
        )
        mock_user = _complete_user_override(uid, payload)
        app.dependency_overrides[get_current_user] = mock_user
        app.dependency_overrides[get_current_user_with_complete_profile] = mock_user

        try:
            with (
                patch("api.extension_autofill.get_cached_tool_result", AsyncMock(return_value=None)),
                patch("api.extension_autofill.get_gemini_client", AsyncMock(side_effect=RuntimeError("boom"))),
                patch("api.extension_autofill._get_user_api_key", AsyncMock(return_value=None)),
                patch("api.extension_autofill._server_has_llm", return_value=True),
            ):
                resp = await authed_client_with_user.post(
                    f"{BASE}/autofill/map",
                    json=_single_field_body(),
                )
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_current_user_with_complete_profile, None)

        assert resp.status_code == 500
        assert resp.json().get("error_code") == "INT_9001"


class TestExtensionAutofillRulesExtended:
    """Additional deterministic rule branches."""

    def _field(self, uid: str, **kwargs):
        from api.extension_autofill import AutofillFieldIn

        base = {
            "field_uid": uid,
            "tag": "input",
            "input_type": "text",
            "label_text": "",
        }
        base.update(kwargs)
        return AutofillFieldIn(**base)

    def test_single_token_name_splits(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field("0", label_text="First name*")
        bundle = {"full_name": "Madonna", "profile": {}}
        assert deterministic_value_for_field(f, bundle) == "Madonna"

    def test_nyc_commute_no_when_not_relocating(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "1",
            input_type="yes_no_buttons",
            tag="div",
            label_text="This position is based in NYC. Are you located in the tri-state area and able to commute?",
            options=[{"value": "Yes", "text": "Yes"}, {"value": "No", "text": "No"}],
        )
        bundle = {
            "full_name": "Jane Doe",
            "profile": {"city": "Austin", "state": "TX", "willing_to_relocate": False},
        }
        assert deterministic_value_for_field(f, bundle) == "No"

    def test_central_office_relocation_not_willing(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "2",
            input_type="combobox",
            label_text="If you are currently not local to one of our central offices, are you willing to relocate?*",
            options=[{"value": "yes", "text": "Yes"}, {"value": "no", "text": "No"}],
        )
        bundle = {
            "full_name": "Jane Doe",
            "profile": {"city": "Austin", "state": "TX", "willing_to_relocate": False},
        }
        assert deterministic_value_for_field(f, bundle) == "No"

    def test_years_experience_exact_match_option(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "3",
            input_type="combobox",
            label_text="Years of experience",
            options=[{"value": "a", "text": "3"}, {"value": "b", "text": "5"}],
        )
        bundle = {"full_name": "Jane", "profile": {"years_experience": 5}}
        assert deterministic_value_for_field(f, bundle) == "5"

    def test_country_two_letter_code(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field("4", input_type="combobox", label_text="Country")
        bundle = {"full_name": "Jane", "profile": {"country": "us"}}
        assert deterministic_value_for_field(f, bundle) == "United States"

    def test_sponsorship_unknown_when_profile_ambiguous(self):
        from api.extension_autofill_rules import deterministic_value_for_field

        f = self._field(
            "5",
            input_type="combobox",
            label_text="Will you require visa sponsorship?",
            options=None,
        )
        bundle = {"full_name": "Jane", "profile": {}}
        assert deterministic_value_for_field(f, bundle) is None

