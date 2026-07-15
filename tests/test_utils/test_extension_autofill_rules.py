"""Unit tests for api/extension_autofill_rules.py deterministic mapping."""

from urllib.parse import urlparse

from api.extension_autofill import AutofillFieldIn
from api.extension_autofill_rules import (
    _align_degree_to_form_options,
    _country_display_name,
    _country_is_us,
    _education_entries,
    _family_name_from_full_name,
    _form_has_middle_name_field,
    _github_username_from_profile,
    _is_consent_ack_label,
    _is_profile_city_location_field,
    _is_yes_no_option_set,
    _label_blob,
    _location_city_answer,
    _location_city_field_excluded,
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
        assert _location_city_field_excluded("Are you willing to relocate to NYC?") is True
        assert _location_city_field_excluded("Preferred work location") is True
        assert _location_city_field_excluded("Current city") is False

    def test_location_city_answer_with_state(self) -> None:
        assert _location_city_answer({"city": "Austin", "state": "TX"}) == "Austin, TX"

    def test_location_city_answer_city_only(self) -> None:
        assert _location_city_answer({"city": "Austin", "state": ""}) == "Austin"

    def test_location_city_answer_missing_city(self) -> None:
        assert _location_city_answer({"city": "", "state": "TX"}) is None

    def test_profile_city_location_field_variants(self) -> None:
        assert _is_profile_city_location_field("Location (City)") is True
        assert _is_profile_city_location_field("How did you hear about us?") is False


class TestEducationAndCountryHelpers:
    def test_education_entries_filters_non_dicts(self) -> None:
        prof = {"education": ["bad", {"institution": "State U"}]}
        assert len(_education_entries(prof)) == 1

    def test_education_entries_non_list(self) -> None:
        assert _education_entries({"education": "bad"}) == []

    def test_country_display_name_code(self) -> None:
        assert _country_display_name("US") == "United States"

    def test_country_display_name_multi_word(self) -> None:
        assert _country_display_name("United Kingdom") == "United Kingdom"

    def test_years_experience_bucket_11_plus(self) -> None:
        assert _years_experience_bucket_fallback(12) == "11+"


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


class TestAdvancedAutofillHelpers:
    def test_sponsorship_work_auth_sets_no_without_flag(self) -> None:
        f = _field(
            label_text="Will you require visa sponsorship?",
            options=[{"value": "yes", "text": "Yes"}, {"value": "no", "text": "No"}],
        )
        prof = {"work_authorization": "has_work_authorization"}
        assert _sponsorship_answer(f, prof) == "No"

    def test_location_exclusion_variants(self) -> None:
        assert _location_city_field_excluded("Location preference") is True
        assert _location_city_field_excluded("Work location") is True
        assert _location_city_field_excluded("Country of residence") is True

    def test_country_display_short_code_maps_to_full_name(self) -> None:
        assert _country_display_name("UK") == "United Kingdom"
        assert _country_display_name("") is None

    def test_salary_expectations_branches(self) -> None:
        from api.extension_autofill_rules import _salary_expectations_answer

        f = _field(label_text="Salary expectations")
        assert _salary_expectations_answer({"desired_salary_range": {"min": 120000, "max": 120000}}, f) == "120000"
        assert _salary_expectations_answer({"desired_salary_range": {"min": 100000, "max": 150000}}, f) == "100000-150000"
        assert _salary_expectations_answer({"desired_salary_range": {"max": 180000}}, f) == "180000"
        assert _salary_expectations_answer({"desired_salary_range": {"min": "bad", "max": "also-bad"}}, f) is None

    def test_education_field_value_kinds(self) -> None:
        from api.extension_autofill_rules import _education_field_value

        prof = _bundle()["profile"]
        degree_f = _field(label_text="Degree")
        assert _education_field_value(degree_f, prof, kind="degree", index=0) == "Bachelor of Science"
        discipline_f = _field(label_text="Discipline")
        assert _education_field_value(discipline_f, prof, kind="discipline", index=0) == "Computer Science"
        school_f = _field(label_text="School")
        assert _education_field_value(school_f, prof, kind="school", index=0) == "State University"
        assert _education_field_value(degree_f, prof, kind="degree", index=5) is None

    def test_github_username_missing_and_invalid_url(self) -> None:
        assert _github_username_from_profile({"github_url": ""}) is None
        assert _github_username_from_profile({"github_url": "https://example.com/user"}) is None

    def test_country_is_us_empty(self) -> None:
        assert _country_is_us(None) is None
        assert _country_is_us("  ") is None

    def test_website_url_falls_back_to_github(self) -> None:
        prof = {"portfolio_url": "", "github_url": "https://github.com/devuser"}
        assert _website_url(prof) == "https://github.com/devuser"

    def test_central_office_relocation_no_options_in_metro(self) -> None:
        from api.extension_autofill_rules import _central_office_relocation_answer

        f = _field(
            label_text="If you are currently not local to one of our central offices, are you willing to relocate?",
            input_type="combobox",
            options=[],
        )
        prof = {"city": "Hoboken", "state": "NJ", "willing_to_relocate": False}
        assert _central_office_relocation_answer(f, prof) == "N/A - Within Commuting Distance"

    def test_tri_state_commute_non_yes_no_options_returns_none(self) -> None:
        from api.extension_autofill_rules import _tri_state_commute_yes_no_answer

        f = _field(
            label_text="Can you commute to our NYC office?",
            input_type="combobox",
            options=[{"value": "a", "text": "Yes, and I currently live in the NYC metro"}],
        )
        assert _tri_state_commute_yes_no_answer(f, _bundle(city="Austin", state="TX")["profile"]) is None

    def test_years_experience_plus_threshold_and_nearest_range(self) -> None:
        f = _field(
            label_text="Do you have 5+ years of experience?",
            input_type="combobox",
            options=[{"value": "yes", "text": "Yes"}, {"value": "no", "text": "No"}],
        )
        assert deterministic_value_for_field(f, _bundle(years_experience=6)) == "Yes"

        range_f = _field(
            label_text="Years of experience",
            input_type="combobox",
            options=[{"value": "a", "text": "1-3"}, {"value": "b", "text": "8-10"}],
        )
        assert deterministic_value_for_field(range_f, _bundle(years_experience=6)) == "8-10"

    def test_years_experience_invalid_value_returns_none(self) -> None:
        f = _field(label_text="Years of experience", input_type="combobox")
        assert deterministic_value_for_field(f, _bundle(years_experience="not-a-number")) is None

    def test_startup_enterprise_only_returns_no(self) -> None:
        from api.extension_autofill_rules import _startup_answer

        assert _startup_answer({"desired_company_sizes": ["enterprise", "1000+"]}) == "No"
        assert _startup_answer({"desired_company_sizes": ["startup"]}) == "Yes"

    def test_middle_name_github_username_salary_start_timeline(self) -> None:
        middle = _field(label_text="Middle name")
        assert deterministic_value_for_field(middle, _bundle()) == "Marie"

        gh_user = _field(label_text="GitHub Username")
        assert deterministic_value_for_field(gh_user, _bundle()) == "janedoe"

        salary = _field(label_text="Salary expectations in USD", input_type="text")
        assert deterministic_value_for_field(salary, _bundle(desired_salary_range={"min": 120000, "max": 150000})) == "120000-150000"

        start = _field(label_text="When can you start?", input_type="textarea")
        assert deterministic_value_for_field(start, _bundle()) == "I can start a new role in 2 weeks."

    def test_consent_checkbox_and_country_field(self) -> None:
        ack = _field(label_text="I acknowledge the privacy policy", input_type="checkbox")
        assert deterministic_value_for_field(ack, _bundle()) == "checked"

        country = _field(label_text="Country", input_type="combobox")
        assert deterministic_value_for_field(country, _bundle(country="US")) == "United States"

    def test_us_based_and_work_auth_no_paths(self) -> None:
        us_no = _field(
            label_text="Are you based in the United States?",
            input_type="radio",
            options=[{"value": "yes", "text": "Yes"}, {"value": "no", "text": "No"}],
        )
        assert deterministic_value_for_field(us_no, _bundle(country="Canada", work_authorization="no_work_authorization")) == "No"

        auth_no = _field(
            label_text="Are you legally authorized to work in the US?",
            input_type="radio",
            options=[{"value": "yes", "text": "Yes"}, {"value": "no", "text": "No"}],
        )
        assert deterministic_value_for_field(auth_no, _bundle(work_authorization="no_work_authorization")) == "No"

    def test_build_assignments_degree_discipline_school(self) -> None:
        fields = [
            _field(field_uid="0", label_text="Degree", input_type="combobox", options=[{"value": "bs", "text": "Bachelor's Degree"}]),
            _field(field_uid="1", label_text="Discipline / Major"),
            _field(field_uid="2", label_text="School / University"),
        ]
        result = build_deterministic_raw_assignments(fields, _bundle())
        by_uid = {item["field_uid"]: item["value"] for item in result}
        assert "0" in by_uid
        assert "1" in by_uid
        assert "2" in by_uid

    def test_merge_preserves_prior_label_text(self) -> None:
        merged = merge_assignment_dicts(
            [{"field_uid": "0", "label_text": "Email address"}],
            [{"field_uid": "0", "value": "user@example.com"}],
        )
        assert merged[0]["label_text"] == "Email address"
        assert merged[0]["value"] == "user@example.com"

    def test_filter_skipped_ignores_non_dict_entries(self) -> None:
        skipped = ["bad", {"field_uid": "1", "reason": "keep"}]
        result = filter_skipped_for_assigned_uids(skipped, ["0"])
        assert len(result) == 1
        assert result[0]["field_uid"] == "1"

    def test_in_office_onsite_central_office(self) -> None:
        f = _field(
            label_text="Are you open to working 3 days onsite at our central office?",
            input_type="combobox",
            options=[
                {"value": "nyc", "text": "NYC Office"},
                {"value": "sf", "text": "San Francisco Office"},
            ],
        )
        val = deterministic_value_for_field(f, _bundle(city="Hoboken", state="NJ"))
        assert val is not None
        assert "NYC" in val or val == "Yes"

    def test_acknowledge_answer_defaults_to_yes(self) -> None:
        from api.extension_autofill_rules import _acknowledge_answer

        f = _field(label_text="I acknowledge", input_type="combobox", options=[])
        assert _acknowledge_answer(f) == "Yes"

    def test_country_display_three_letter_unknown_uppercase(self) -> None:
        assert _country_display_name("XYZ") == "XYZ"

    def test_salary_expectations_min_only(self) -> None:
        from api.extension_autofill_rules import _salary_expectations_answer

        f = _field(label_text="Salary")
        assert _salary_expectations_answer({"desired_salary_range": {"min": 90000}}, f) == "90000"

    def test_education_discipline_missing_returns_none(self) -> None:
        from api.extension_autofill_rules import _education_field_value

        prof = {"education": [{"institution": "MIT", "degree": "BS"}]}
        f = _field(label_text="Discipline")
        assert _education_field_value(f, prof, kind="discipline", index=0) is None

    def test_user_in_nyc_metro_by_state(self) -> None:
        from api.extension_autofill_rules import _user_in_nyc_metro

        assert _user_in_nyc_metro({"city": "Ithaca", "state": "NY"}) is True

    def test_consent_not_marketing_opt_in(self) -> None:
        assert _is_consent_ack_label("Subscribe to marketing emails") is False

    def test_in_office_willing_relocate_long_options(self) -> None:
        f = _field(
            label_text="Can you work in-person in NYC?",
            input_type="combobox",
            options=[
                {"value": "a", "text": "Yes, open to relocation"},
                {"value": "b", "text": "No, cannot work in-office"},
            ],
        )
        val = deterministic_value_for_field(f, _bundle(city="Austin", state="TX", willing_to_relocate=True))
        assert val is not None
        assert "relocat" in val.lower() or val.lower().startswith("yes")

    def test_central_office_not_willing_no_options(self) -> None:
        from api.extension_autofill_rules import _central_office_relocation_answer

        f = _field(
            label_text="If you are currently not local to one of our central offices, are you willing to relocate?",
            input_type="combobox",
            options=[],
        )
        prof = {"city": "Austin", "state": "TX", "willing_to_relocate": False}
        assert _central_office_relocation_answer(f, prof) == "No"

    def test_startup_only_large_enterprise_returns_no(self) -> None:
        from api.extension_autofill_rules import _startup_answer

        assert _startup_answer({"desired_company_sizes": ["Enterprise (1000+)", "Large (500+)"]}) == "No"

    def test_startup_with_startup_preference_returns_yes(self) -> None:
        from api.extension_autofill_rules import _startup_answer

        assert _startup_answer({"desired_company_sizes": ["Early-stage startup"]}) == "Yes"

    def test_in_office_central_office_willing_yes_option(self) -> None:
        f = _field(
            label_text="Are you open to working 3 days onsite at our central office?",
            input_type="combobox",
            options=[{"value": "y", "text": "Yes"}, {"value": "n", "text": "No"}],
        )
        val = deterministic_value_for_field(
            f, _bundle(city="Austin", state="TX", willing_to_relocate=True)
        )
        assert val == "Yes"

    def test_in_office_central_office_in_metro_no_options(self) -> None:
        from api.extension_autofill_rules import _in_office_answer

        f = _field(
            label_text="Are you open to working 3 days onsite at our central office?",
            input_type="text",
        )
        prof = {"city": "Brooklyn", "state": "NY", "willing_to_relocate": False}
        assert _in_office_answer(f, prof) == "NYC"

    def test_sponsorship_needs_yes_with_options(self) -> None:
        f = _field(
            label_text="Will you require visa sponsorship?",
            input_type="radio",
            options=[{"value": "y", "text": "Yes"}, {"value": "n", "text": "No"}],
        )
        val = deterministic_value_for_field(
            f, _bundle(requires_visa_sponsorship=True, work_authorization="needs_sponsorship")
        )
        assert val == "Yes"

    def test_years_experience_plus_threshold(self) -> None:
        f = _field(
            label_text="Years of experience (5+)",
            input_type="combobox",
            options=[
                {"value": "0", "text": "0-2 years"},
                {"value": "1", "text": "3-5 years"},
                {"value": "2", "text": "6+ years"},
            ],
        )
        val = deterministic_value_for_field(f, _bundle(years_experience=6))
        assert val is not None

    def test_align_degree_fuzzy_match(self) -> None:
        aligned = _align_degree_to_form_options(
            "Bachelor of Science",
            ["Associate Degree", "Bachelor's Degree", "Master's Degree"],
        )
        assert "Bachelor" in aligned

    def test_github_and_website_from_profile(self) -> None:
        prof = _profile_dict(_bundle())
        assert _github_username_from_profile(prof) == "janedoe"
        assert _website_url(prof) == "https://janedoe.dev"

    def test_location_city_excluded_for_relocation(self) -> None:
        assert _location_city_field_excluded("Are you willing to relocate?") is True
        assert _is_profile_city_location_field("Location (City)") is True

    def test_country_is_us_and_work_auth(self) -> None:
        assert _country_is_us("US") is True
        assert _work_auth_implies_us("has_work_authorization") is True

    def test_years_experience_bucket_fallback_ranges(self) -> None:
        assert _years_experience_bucket_fallback(5) == "5-7"
        assert _years_experience_bucket_fallback(9) == "8-10"
        assert _years_experience_bucket_fallback(15) == "11+"

    def test_is_yes_no_option_set_detects(self) -> None:
        assert _is_yes_no_option_set(["Yes", "No"]) is True
        assert _is_yes_no_option_set(["Maybe", "Sometimes"]) is False

    def test_parse_plus_years_threshold(self) -> None:
        assert _parse_plus_years_threshold("5+ years experience") == 5
        assert _parse_plus_years_threshold("experience") is None

    def test_pick_option_first_match(self) -> None:
        assert _pick_option(["No", "Yes"], lambda t: t.startswith("yes")) == "Yes"

    def test_education_entries_non_list(self) -> None:
        assert _education_entries({"education": "bad"}) == []

    def test_form_has_middle_name_field(self) -> None:
        fields = [_field(label_text="Middle name")]
        assert _form_has_middle_name_field(fields) is True
        assert _form_has_middle_name_field(None) is False

    def test_central_office_relocation_in_metro_with_commuting_option(self) -> None:
        from api.extension_autofill_rules import _central_office_relocation_answer

        f = _field(
            label_text="If you are currently not local to one of our central offices, are you willing to relocate?",
            input_type="combobox",
            options=[
                {"value": "a", "text": "N/A - Within Commuting Distance"},
                {"value": "b", "text": "Yes, willing to relocate"},
            ],
        )
        prof = {"city": "Hoboken", "state": "NJ", "willing_to_relocate": False}
        assert _central_office_relocation_answer(f, prof) == "N/A - Within Commuting Distance"

    def test_central_office_relocation_willing_relocate_option(self) -> None:
        from api.extension_autofill_rules import _central_office_relocation_answer

        f = _field(
            label_text="If you are currently not local to one of our central offices, are you willing to relocate?",
            input_type="combobox",
            options=[
                {"value": "a", "text": "Yes, willing to relocate"},
                {"value": "b", "text": "No, not willing to relocate"},
            ],
        )
        prof = {"city": "Austin", "state": "TX", "willing_to_relocate": True}
        val = _central_office_relocation_answer(f, prof)
        assert val is not None
        assert "yes" in val.lower() or "relocat" in val.lower()

    def test_tri_state_commute_nyc_metro_yes(self) -> None:
        from api.extension_autofill_rules import _tri_state_commute_yes_no_answer

        f = _field(
            label_text="Are you located in the NYC metropolitan area?",
            input_type="radio",
            options=[{"value": "y", "text": "Yes"}, {"value": "n", "text": "No"}],
        )
        assert _tri_state_commute_yes_no_answer(f, {"city": "Jersey City", "state": "NJ"}) == "Yes"

    def test_tri_state_commute_with_city_not_metro(self) -> None:
        from api.extension_autofill_rules import _tri_state_commute_yes_no_answer

        f = _field(
            label_text="Are you located in the NYC metropolitan area?",
            input_type="radio",
            options=[{"value": "y", "text": "Yes"}, {"value": "n", "text": "No"}],
        )
        assert _tri_state_commute_yes_no_answer(f, {"city": "Chicago", "state": "IL"}) == "No"

    def test_years_experience_yes_no_threshold(self) -> None:
        from api.extension_autofill_rules import _years_experience_answer

        f = _field(
            label_text="Do you have 5+ years of experience?",
            input_type="radio",
            options=[{"value": "y", "text": "Yes"}, {"value": "n", "text": "No"}],
        )
        assert _years_experience_answer(f, {"years_experience": 6}) == "Yes"
        assert _years_experience_answer(f, {"years_experience": 2}) == "No"

    def test_years_experience_bucket_match(self) -> None:
        from api.extension_autofill_rules import _years_experience_answer

        f = _field(
            label_text="Years of experience",
            input_type="combobox",
            options=[
                {"value": "0", "text": "3-5"},
                {"value": "1", "text": "6-8"},
            ],
        )
        assert _years_experience_answer(f, {"years_experience": 4}) == "3-5"

    def test_in_office_nyc_currently_live_option(self) -> None:
        f = _field(
            label_text="Can you work in-person in NYC?",
            input_type="combobox",
            options=[
                {"value": "a", "text": "Yes, I currently live in the metropolitan area"},
                {"value": "b", "text": "No, I cannot work in-office"},
            ],
        )
        val = deterministic_value_for_field(f, _bundle(city="Brooklyn", state="NY"))
        assert val is not None
        assert "currently" in val.lower() or val.lower().startswith("yes")

    def test_sponsorship_no_when_authorized(self) -> None:
        f = _field(
            label_text="Will you now or in the future require sponsorship?",
            input_type="radio",
            options=[{"value": "y", "text": "Yes"}, {"value": "n", "text": "No"}],
        )
        val = deterministic_value_for_field(
            f, _bundle(requires_visa_sponsorship=False, work_authorization="has_work_authorization")
        )
        assert val == "No"

    def test_country_display_multi_word_passthrough(self) -> None:
        assert _country_display_name("United States") == "United States"

    def test_salary_expectations_max_only(self) -> None:
        from api.extension_autofill_rules import _salary_expectations_answer

        f = _field(label_text="Expected salary")
        assert _salary_expectations_answer({"desired_salary_range": {"max": 120000}}, f) == "120000"

    def test_education_degree_type_field(self) -> None:
        from api.extension_autofill_rules import _education_field_value

        prof = {"education": [{"institution": "MIT", "degree_type": "MS"}]}
        f = _field(label_text="Degree")
        assert _education_field_value(f, prof, kind="degree", index=0) == "MS"

    def test_consent_work_location_ack(self) -> None:
        assert _is_consent_ack_label("I acknowledge the work location policy") is True

    def test_country_is_us_non_us(self) -> None:
        assert _country_is_us("Canada") is False

    def test_central_office_in_metro_picks_no_option(self) -> None:
        from api.extension_autofill_rules import _central_office_relocation_answer

        f = _field(
            label_text="If you are currently not local to one of our central offices, are you willing to relocate?",
            input_type="combobox",
            options=[
                {"value": "a", "text": "No, not within commuting distance"},
                {"value": "b", "text": "Yes, willing to relocate"},
            ],
        )
        prof = {"city": "Brooklyn", "state": "NY", "willing_to_relocate": False}
        val = _central_office_relocation_answer(f, prof)
        assert val is not None
        assert val.lower().startswith("no")

    def test_years_experience_exact_and_plus_options(self) -> None:
        from api.extension_autofill_rules import _years_experience_answer

        exact_f = _field(
            label_text="Years of experience",
            input_type="combobox",
            options=[{"value": "5", "text": "5"}],
        )
        assert _years_experience_answer(exact_f, {"years_experience": 5}) == "5"

        plus_f = _field(
            label_text="Years of experience",
            input_type="combobox",
            options=[{"value": "10", "text": "10+"}],
        )
        assert _years_experience_answer(plus_f, {"years_experience": 12}) == "10+"

    def test_years_experience_nearest_bucket(self) -> None:
        from api.extension_autofill_rules import _years_experience_answer

        f = _field(
            label_text="Years of experience",
            input_type="combobox",
            options=[{"value": "0", "text": "1-3"}, {"value": "1", "text": "8-10"}],
        )
        assert _years_experience_answer(f, {"years_experience": 6}) == "8-10"

    def test_in_office_central_office_sf_options_willing(self) -> None:
        from api.extension_autofill_rules import _in_office_answer

        f = _field(
            label_text="Are you open to working 3 days onsite at our central office?",
            input_type="combobox",
            options=[
                {"value": "sf", "text": "San Francisco Office"},
                {"value": "y", "text": "Yes"},
            ],
        )
        prof = {"city": "Oakland", "state": "CA", "willing_to_relocate": True}
        assert _in_office_answer(f, prof) == "Yes"

    def test_in_office_not_willing_returns_no(self) -> None:
        from api.extension_autofill_rules import _in_office_answer

        f = _field(
            label_text="Are you open to working 3 days onsite at our central office?",
            input_type="combobox",
            options=[{"value": "y", "text": "Yes"}, {"value": "n", "text": "No"}],
        )
        prof = {"city": "Denver", "state": "CO", "willing_to_relocate": False}
        assert _in_office_answer(f, prof) == "No"

    def test_github_url_field(self) -> None:
        f = _field(label_text="GitHub profile URL", input_type="url")
        val = deterministic_value_for_field(f, _bundle())
        assert val == "https://github.com/janedoe"

    def test_build_assignments_website_and_education_indices(self) -> None:
        fields = [
            _field(field_uid="0", label_text="Portfolio website", input_type="url"),
            _field(field_uid="1", label_text="Degree", input_type="combobox", options=[{"value": "bs", "text": "BS"}]),
            _field(field_uid="2", label_text="Discipline / Major"),
            _field(field_uid="3", label_text="School / University"),
        ]
        result = build_deterministic_raw_assignments(fields, _bundle())
        by_uid = {item["field_uid"]: item["value"] for item in result}
        assert "0" in by_uid
        assert "1" in by_uid
        assert "2" in by_uid
        assert "3" in by_uid

