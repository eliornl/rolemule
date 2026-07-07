"""Table-driven tests for relocation / office / screening autofill rules."""

from api.extension_autofill import AutofillFieldIn
from api.extension_autofill_rules import (
    _central_office_relocation_answer,
    _in_office_answer,
    _is_profile_city_location_field,
    _location_city_field_excluded,
    _startup_answer,
    _tri_state_commute_yes_no_answer,
    build_deterministic_raw_assignments,
    deterministic_value_for_field,
    filter_skipped_for_assigned_uids,
    merge_assignment_dicts,
)


def _field(**kwargs) -> AutofillFieldIn:
    defaults = {"field_uid": "0", "tag": "input", "input_type": "combobox", "label_text": "Field"}
    defaults.update(kwargs)
    return AutofillFieldIn(**defaults)


def _prof(**kwargs) -> dict:
    base = {
        "city": "Brooklyn",
        "state": "NY",
        "country": "US",
        "willing_to_relocate": False,
        "work_authorization": "has_work_authorization",
        "requires_visa_sponsorship": False,
    }
    base.update(kwargs)
    return base


class TestLocationFieldExclusion:
    def test_country_field_excluded(self) -> None:
        assert _location_city_field_excluded("Country of residence") is True

    def test_state_only_excluded_without_city(self) -> None:
        assert _location_city_field_excluded("State / Province") is True

    def test_relocation_excluded(self) -> None:
        assert _location_city_field_excluded("Willing to relocation?") is True

    def test_office_location_excluded(self) -> None:
        assert _location_city_field_excluded("Office location preference") is True

    def test_profile_city_location_included(self) -> None:
        assert _is_profile_city_location_field("Location (City)") is True
        assert _location_city_field_excluded("Location (City)") is False


class TestTriStateCommute:
    def test_nyc_metro_yes(self) -> None:
        f = _field(label_text="Are you located in the NYC area?")
        assert _tri_state_commute_yes_no_answer(f, _prof(city="Brooklyn", state="NY")) == "Yes"

    def test_willing_to_relocate_yes(self) -> None:
        f = _field(label_text="Can you commute to NYC?")
        assert _tri_state_commute_yes_no_answer(f, _prof(city="Austin", state="TX", willing_to_relocate=True)) == "Yes"

    def test_other_city_no(self) -> None:
        f = _field(label_text="NYC metropolitan area commute")
        assert _tri_state_commute_yes_no_answer(f, _prof(city="Chicago", state="IL")) == "No"

    def test_no_city_returns_none(self) -> None:
        f = _field(label_text="NYC area commute")
        assert _tri_state_commute_yes_no_answer(f, _prof(city="", state="")) is None


class TestCentralOfficeRelocation:
    _LABEL = "If you are not local to a central office, are you willing to relocate?"

    def test_metro_commuting_option(self) -> None:
        f = _field(
            label_text=self._LABEL,
            options=[
                {"value": "a", "text": "N/A - Within Commuting Distance"},
                {"value": "b", "text": "Yes"},
            ],
        )
        val = _central_office_relocation_answer(f, _prof(city="Brooklyn", state="NY"))
        assert val == "N/A - Within Commuting Distance"

    def test_metro_currently_local_option(self) -> None:
        f = _field(
            label_text=self._LABEL,
            options=[
                {"value": "a", "text": "Currently local to metropolitan area"},
                {"value": "b", "text": "Yes"},
            ],
        )
        val = _central_office_relocation_answer(f, _prof(city="Brooklyn", state="NY"))
        assert val == "Currently local to metropolitan area"

    def test_willing_relocate_yes_option(self) -> None:
        f = _field(
            label_text=self._LABEL,
            options=[{"value": "y", "text": "Yes"}, {"value": "n", "text": "No"}],
        )
        val = _central_office_relocation_answer(
            f, _prof(city="Denver", state="CO", willing_to_relocate=True)
        )
        assert val == "Yes"

    def test_willing_relocate_relocation_wording(self) -> None:
        f = _field(
            label_text=self._LABEL,
            options=[
                {"value": "r", "text": "Open to relocation"},
                {"value": "n", "text": "Not willing to relocate"},
            ],
        )
        val = _central_office_relocation_answer(
            f, _prof(city="Denver", state="CO", willing_to_relocate=True)
        )
        assert val == "Open to relocation"

    def test_not_willing_no_option(self) -> None:
        f = _field(
            label_text=self._LABEL,
            options=[
                {"value": "n", "text": "Not willing to relocate"},
                {"value": "y", "text": "Yes"},
            ],
        )
        val = _central_office_relocation_answer(f, _prof(city="Denver", state="CO"))
        assert val == "Not willing to relocate"

    def test_fallback_no_options_metro(self) -> None:
        f = _field(label_text=self._LABEL)
        assert _central_office_relocation_answer(f, _prof(city="Brooklyn", state="NY")) == (
            "N/A - Within Commuting Distance"
        )

    def test_fallback_no_options_willing(self) -> None:
        f = _field(label_text=self._LABEL)
        assert _central_office_relocation_answer(
            f, _prof(city="", state="", willing_to_relocate=True)
        ) == "Yes"


class TestInOfficeAnswer:
    _CENTRAL_LABEL = "Are you open to working 3 days onsite at our central office?"

    def test_central_office_nyc_code_pick(self) -> None:
        f = _field(
            label_text=self._CENTRAL_LABEL,
            options=[{"value": "nyc", "text": "NYC Office"}, {"value": "sf", "text": "SF Office"}],
        )
        val = _in_office_answer(f, _prof(city="Brooklyn", state="NY"))
        assert val == "NYC Office"

    def test_central_office_yes_without_office_codes(self) -> None:
        f = _field(
            label_text=self._CENTRAL_LABEL,
            options=[{"value": "y", "text": "Yes"}, {"value": "n", "text": "No"}],
        )
        val = _in_office_answer(f, _prof(city="Brooklyn", state="NY"))
        assert val == "Yes"

    def test_central_office_no_options_metro(self) -> None:
        f = _field(label_text=self._CENTRAL_LABEL)
        assert _in_office_answer(f, _prof(city="Brooklyn", state="NY")) == "NYC"

    def test_in_office_willing_relocation(self) -> None:
        f = _field(
            label_text="Are you open to working 3 days onsite?",
            options=[
                {"value": "r", "text": "Open to relocation"},
                {"value": "c", "text": "Cannot relocate"},
            ],
        )
        val = _in_office_answer(f, _prof(city="Austin", state="TX", willing_to_relocate=True))
        assert val == "Open to relocation"

    def test_in_office_cannot_relocate(self) -> None:
        f = _field(
            label_text="Are you open to working 3 days onsite?",
            options=[
                {"value": "c", "text": "Cannot relocate to office"},
                {"value": "y", "text": "Yes"},
            ],
        )
        val = _in_office_answer(f, _prof(city="Austin", state="TX"))
        assert val == "Cannot relocate to office"

    def test_nyc_commute_currently_local(self) -> None:
        f = _field(
            label_text="Do you currently live in the NYC metropolitan area?",
            options=[
                {"value": "l", "text": "Currently local to NYC"},
                {"value": "n", "text": "No"},
            ],
        )
        val = _in_office_answer(f, _prof(city="Brooklyn", state="NY"))
        assert val == "Currently local to NYC"


class TestStartupAnswer:
    def test_startup_preference_yes(self) -> None:
        assert _startup_answer({"desired_company_sizes": ["Startup (1-50)"]}) == "Yes"

    def test_enterprise_only_no(self) -> None:
        assert _startup_answer({"desired_company_sizes": ["Enterprise (1000+)"]}) == "No"

    def test_default_yes_when_mixed(self) -> None:
        assert _startup_answer({"desired_company_sizes": ["Mid-size (51-200)"]}) == "Yes"

    def test_invalid_sizes_type(self) -> None:
        assert _startup_answer({"desired_company_sizes": "startup"}) is None


class TestScreeningDeterministic:
    def test_work_authorization_yes(self) -> None:
        f = _field(label_text="Are you authorized to work in the US?", input_type="radio")
        val = deterministic_value_for_field(f, {"profile": _prof()})
        assert val == "Yes"

    def test_us_based_yes_from_country(self) -> None:
        f = _field(label_text="Are you located in the United States?", input_type="yes_no_buttons")
        val = deterministic_value_for_field(f, {"profile": _prof(country="US")})
        assert val == "Yes"

    def test_us_based_no(self) -> None:
        f = _field(
            label_text="Are you located in the United States?",
            input_type="yes_no_buttons",
        )
        val = deterministic_value_for_field(
            f,
            {
                "profile": _prof(
                    country="CA",
                    work_authorization="no_work_authorization",
                )
            },
        )
        assert val == "No"

    def test_startup_screening(self) -> None:
        f = _field(
            label_text="Are you prepared to work at a startup?",
            input_type="radio",
        )
        val = deterministic_value_for_field(
            f, {"profile": _prof(desired_company_sizes=["Startup (1-50)"])}
        )
        assert val == "Yes"


class TestAssignmentHelpers:
    def test_merge_preserves_overlay_label(self) -> None:
        base = [{"field_uid": "1", "value": "LLM", "label_text": "Email"}]
        overlay = [{"field_uid": "1", "value": "user@example.com"}]
        merged = merge_assignment_dicts(base, overlay)
        assert merged[0]["value"] == "user@example.com"
        assert merged[0]["label_text"] == "Email"

    def test_filter_skipped_drops_assigned_and_non_dict(self) -> None:
        skipped = [
            {"field_uid": "1", "reason": "x"},
            {"field_uid": "2", "reason": "y"},
            "bad",
        ]
        out = filter_skipped_for_assigned_uids(skipped, ["1"])
        assert len(out) == 1
        assert out[0]["field_uid"] == "2"

    def test_build_assignments_website_field(self) -> None:
        f = _field(field_uid="99", label_text="Portfolio website", input_type="text")
        out = build_deterministic_raw_assignments(
            [f],
            {
                "profile": _prof(
                    portfolio_url="https://example.dev",
                    github_url="https://github.com/jane",
                )
            },
        )
        assert any(a["field_uid"] == "99" and "example.dev" in a["value"] for a in out)
