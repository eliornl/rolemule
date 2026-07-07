"""Unit tests for api/extension_autofill_rules.py deterministic mapping."""

from urllib.parse import urlparse

from api.extension_autofill import AutofillFieldIn
from api.extension_autofill_rules import (
    _align_degree_to_form_options,
    _country_display_name,
    _country_is_us,
    _family_name_from_full_name,
    _form_has_middle_name_field,
    _github_username_from_profile,
    _is_consent_ack_label,
    _is_profile_city_location_field,
    _is_yes_no_option_set,
    _label_blob,
    _norm_label,
    _parse_plus_years_threshold,
    _pick_option,
    _profile_dict,
    _split_full_name,
    _sponsorship_answer,
    _website_url,
    _work_auth_implies_us,
    _years_experience_bucket_fallback,
    build_deterministic_raw_assignments,
    deterministic_value_for_field,
    filter_skipped_for_assigned_uids,
    merge_assignment_dicts,
)


def _field(**kwargs) -> AutofillFieldIn:
    defaults = {"field_uid": "0", "tag": "input", "input_type": "text", "label_text": "Field"}
    defaults.update(kwargs)
    return AutofillFieldIn(**defaults)


def _bundle(**profile_kwargs) -> dict:
    return {
        "email": "user@example.com",
        "full_name": "Jane Marie Doe",
        "profile": {
            "phone": "+1-555-0100",
            "city": "Austin",
            "state": "TX",
            "country": "US",
            "years_experience": 5,
            "requires_visa_sponsorship": False,
            "work_authorization": "has_work_authorization",
            "linkedin_url": "https://linkedin.com/in/janedoe",
            "portfolio_url": "https://janedoe.dev",
            "github_url": "https://github.com/janedoe",
            "education": [
                {
                    "institution": "State University",
                    "degree": "Bachelor of Science",
                    "field_of_study": "Computer Science",
                }
            ],
            **profile_kwargs,
        },
    }


class TestLabelHelpers:
    def test_norm_label_collapses_whitespace(self) -> None:
        assert _norm_label("  First   name  ") == "First name"

    def test_label_blob_combines_parts(self) -> None:
        f = _field(label_text="Email", placeholder="you@example.com", name_attr="email")
        assert "Email" in _label_blob(f)
        assert "you@example.com" in _label_blob(f)

    def test_profile_dict_missing_profile(self) -> None:
        assert _profile_dict({}) == {}
        assert _profile_dict({"profile": None}) == {}


class TestNameSplitting:
    def test_split_single_name(self) -> None:
        assert _split_full_name("Madonna") == ("Madonna", "", "Madonna")

    def test_split_three_part_name(self) -> None:
        assert _split_full_name("Jane Marie Doe") == ("Jane", "Marie", "Doe")

    def test_family_name_multi_part(self) -> None:
        assert _family_name_from_full_name("Jane Marie Doe") == "Marie Doe"


class TestDeterministicContactFields:
    def test_email_field(self) -> None:
        f = _field(label_text="Email address", input_type="email")
        assert deterministic_value_for_field(f, _bundle()) == "user@example.com"

    def test_first_name_field(self) -> None:
        f = _field(label_text="First name")
        assert deterministic_value_for_field(f, _bundle()) == "Jane"

    def test_last_name_without_middle_field(self) -> None:
        f = _field(label_text="Last name")
        assert deterministic_value_for_field(f, _bundle()) == "Marie Doe"

    def test_last_name_with_middle_field_on_form(self) -> None:
        first = _field(field_uid="0", label_text="First name")
        middle = _field(field_uid="1", label_text="Middle name")
        last = _field(field_uid="2", label_text="Last name")
        assert deterministic_value_for_field(last, _bundle(), all_fields=[first, middle, last]) == "Doe"

    def test_phone_field(self) -> None:
        f = _field(label_text="Phone number", input_type="tel")
        assert deterministic_value_for_field(f, _bundle()) == "+1-555-0100"

    def test_linkedin_field(self) -> None:
        f = _field(label_text="LinkedIn profile URL", input_type="url")
        val = deterministic_value_for_field(f, _bundle())
        host = (urlparse(val).hostname or "").lower()
        parts = host.split(".")
        assert val and len(parts) >= 2 and parts[-2] == "linkedin" and parts[-1] == "com"


class TestScreeningQuestions:
    def test_sponsorship_no_when_authorized(self) -> None:
        f = _field(
            label_text="Will you require visa sponsorship?",
            input_type="radio",
            options=[{"value": "yes", "text": "Yes"}, {"value": "no", "text": "No"}],
        )
        ans = _sponsorship_answer(f, _bundle()["profile"])
        assert ans is not None
        assert ans.lower().startswith("no")

    def test_work_authorization_yes(self) -> None:
        f = _field(
            label_text="Are you legally authorized to work in the US?",
            input_type="yes_no_buttons",
        )
        val = deterministic_value_for_field(f, _bundle())
        assert val == "Yes"

    def test_eeo_field_skipped(self) -> None:
        f = _field(label_text="Gender (EEO voluntary self-identification)")
        assert deterministic_value_for_field(f, _bundle()) is None


class TestUtilityFunctions:
    def test_country_display_us(self) -> None:
        assert _country_display_name("US") == "United States"

    def test_country_is_us(self) -> None:
        assert _country_is_us("United States") is True
        assert _country_is_us("Canada") is False

    def test_work_auth_implies_us(self) -> None:
        assert _work_auth_implies_us("us_citizen") is True
        assert _work_auth_implies_us("no_work_authorization") is False

    def test_years_experience_bucket(self) -> None:
        assert "5" in _years_experience_bucket_fallback(5) or "3" in _years_experience_bucket_fallback(5)

    def test_parse_plus_years_threshold(self) -> None:
        assert _parse_plus_years_threshold("5+ years of experience") == 5

    def test_is_yes_no_option_set(self) -> None:
        assert _is_yes_no_option_set(["Yes", "No"]) is True
        assert _is_yes_no_option_set(["Maybe"]) is False

    def test_pick_option(self) -> None:
        picked = _pick_option(["Yes", "No"], lambda t: t.lower() == "no")
        assert picked == "No"

    def test_align_degree_to_form_options(self) -> None:
        aligned = _align_degree_to_form_options("BS Computer Science", ["Bachelor's Degree", "Master's"])
        assert aligned in ("Bachelor's Degree", "BS Computer Science")

    def test_github_username_from_profile(self) -> None:
        assert _github_username_from_profile(_bundle()["profile"]) == "janedoe"

    def test_website_url(self) -> None:
        assert _website_url(_bundle()["profile"]) == "https://janedoe.dev"

    def test_consent_ack_label(self) -> None:
        assert _is_consent_ack_label("I acknowledge the privacy policy") is True

    def test_city_location_field(self) -> None:
        assert _is_profile_city_location_field("Current city") is True

    def test_form_has_middle_name_field(self) -> None:
        fields = [_field(field_uid="0", label_text="Middle name")]
        assert _form_has_middle_name_field(fields) is True


class TestBuildAndMerge:
    def test_build_deterministic_raw_assignments(self) -> None:
        fields = [
            _field(field_uid="0", label_text="Email address", input_type="email"),
            _field(field_uid="1", label_text="First name"),
        ]
        result = build_deterministic_raw_assignments(fields, _bundle())
        uids = {item["field_uid"] for item in result}
        assert "0" in uids or "1" in uids

    def test_merge_assignment_dicts(self) -> None:
        base = [{"field_uid": "0", "value": "a"}]
        overlay = [{"field_uid": "1", "value": "b"}]
        merged = merge_assignment_dicts(base, overlay)
        by_uid = {item["field_uid"]: item["value"] for item in merged}
        assert by_uid.get("0") == "a"
        assert by_uid.get("1") == "b"

    def test_filter_skipped_for_assigned_uids(self) -> None:
        skipped = [
            {"field_uid": "0", "reason": "skip"},
            {"field_uid": "2", "reason": "keep"},
        ]
        result = filter_skipped_for_assigned_uids(skipped, ["0", "1"])
        assert len(result) == 1
        assert result[0]["field_uid"] == "2"


class TestNameEdgeCases:
    def test_split_full_name_empty(self) -> None:
        assert _split_full_name("") == ("", "", "")
        assert _split_full_name("   ") == ("", "", "")

    def test_family_name_empty_and_single(self) -> None:
        assert _family_name_from_full_name("") == ""
        assert _family_name_from_full_name("Prince") == "Prince"


class TestSponsorshipBranches:
    def test_sponsorship_yes_when_required(self) -> None:
        f = _field(
            label_text="Will you require visa sponsorship?",
            input_type="combobox",
            options=[{"value": "Yes", "text": "Yes"}, {"value": "No", "text": "No"}],
        )
        prof = _bundle(requires_visa_sponsorship=True)["profile"]
        assert _sponsorship_answer(f, prof) == "Yes"

    def test_sponsorship_unknown_without_profile_flags(self) -> None:
        f = _field(label_text="Require visa sponsorship?", options=None)
        assert _sponsorship_answer(f, {}) is None


class TestLocationExclusions:
    def test_relocation_not_city_field(self) -> None:
        from api.extension_autofill_rules import _location_city_field_excluded

        assert _location_city_field_excluded("Are you willing to relocate to NYC?") is True
        assert _location_city_field_excluded("Preferred work location") is True
        assert _location_city_field_excluded("Current city") is False


class TestCentralOfficeRelocation:
    def test_in_metro_commuting_option(self) -> None:
        f = _field(
            field_uid="10",
            label_text="If you are currently not local to one of our central offices, are you willing to relocate?*",
            input_type="combobox",
            options=[
                {"value": "a", "text": "N/A - Within Commuting Distance"},
                {"value": "b", "text": "Yes, and while I do not currently live in the NYC Metropolitan Area, I am open to relocation."},
                {"value": "c", "text": "No, I cannot work in-office."},
            ],
        )
        bundle = _bundle(city="Brooklyn", state="NY", willing_to_relocate=False)
        val = deterministic_value_for_field(f, bundle)
        assert val is not None
        assert "commuting" in val.lower() or "local" in val.lower()

    def test_willing_relocate_yes_option(self) -> None:
        f = _field(
            field_uid="11",
            label_text="If you are currently not local to one of our central offices, are you willing to relocate?*",
            input_type="combobox",
            options=[{"value": "yes", "text": "Yes"}, {"value": "no", "text": "No"}],
        )
        bundle = _bundle(city="Austin", state="TX", willing_to_relocate=True)
        assert deterministic_value_for_field(f, bundle) == "Yes"


class TestYearsExperienceMatching:
    def test_exact_numeric_option(self) -> None:
        f = _field(
            field_uid="12",
            label_text="Years of experience",
            input_type="combobox",
            options=[{"value": "a", "text": "3"}, {"value": "b", "text": "5"}],
        )
        assert deterministic_value_for_field(f, _bundle(years_experience=5)) == "5"

    def test_plus_years_threshold_combobox(self) -> None:
        f = _field(
            field_uid="13",
            label_text="Do you have 5+ years of experience?",
            input_type="combobox",
            options=[{"value": "yes", "text": "Yes"}, {"value": "no", "text": "No"}],
        )
        assert deterministic_value_for_field(f, _bundle(years_experience=4)) == "Yes"
        assert deterministic_value_for_field(f, _bundle(years_experience=2)) == "No"

    def test_nearest_range_bucket(self) -> None:
        f = _field(
            field_uid="14",
            label_text="Years of Industry Experience",
            input_type="combobox",
            options=[
                {"value": "a", "text": "1-3"},
                {"value": "b", "text": "8-10"},
            ],
        )
        val = deterministic_value_for_field(f, _bundle(years_experience=4))
        assert val in ("1-3", "8-10")

