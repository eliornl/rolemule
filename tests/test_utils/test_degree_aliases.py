"""Tests for utils/degree_aliases.py."""

from utils.degree_aliases import (
    DEGREE_ALIAS_SPECS,
    _best_fallback_label,
    _option_allowed_for_spec,
    _pick_level_generic_option,
    align_degree_to_form_options,
    classify_degree,
    pick_degree_from_options,
)


def test_classify_degree_phd() -> None:
    spec = classify_degree("Ph.D. in Computer Science")
    assert spec is not None
    assert spec.key == "phd"


def test_classify_degree_bachelor_ba() -> None:
    spec = classify_degree("B.A.")
    assert spec is not None
    assert spec.key == "ba"


def test_classify_degree_high_school() -> None:
    spec = classify_degree("High School Diploma")
    assert spec is not None
    assert spec.key == "high_school"


def test_classify_degree_unknown() -> None:
    assert classify_degree("") is None
    assert classify_degree("   ") is None


def test_pick_degree_from_options_exact_match() -> None:
    options = ["Bachelor's Degree", "Master's Degree"]
    assert pick_degree_from_options("Bachelor's Degree", options) == "Bachelor's Degree"


def test_pick_degree_from_options_mba() -> None:
    options = ["Master of Business Administration (M.B.A.)", "Bachelor's Degree"]
    picked = pick_degree_from_options("MBA", options)
    assert picked == "Master of Business Administration (M.B.A.)"


def test_pick_degree_jd_not_generic_bachelor() -> None:
    options = ["Bachelor's Degree", "Juris Doctor (J.D.)"]
    picked = pick_degree_from_options("J.D.", options)
    assert picked == "Juris Doctor (J.D.)"


def test_align_degree_fallback_label() -> None:
    aligned = align_degree_to_form_options("PhD", [])
    assert "Ph" in aligned or "Doctor" in aligned


def test_align_degree_with_options() -> None:
    options = ["Master of Science (MS)", "Bachelor's Degree"]
    assert align_degree_to_form_options("M.S.", options) == "Master of Science (MS)"


def test_jd_rejects_generic_bachelor_option() -> None:
    options = ["Bachelor's Degree", "Juris Doctor (J.D.)"]
    picked = pick_degree_from_options("J.D.", options)
    assert picked == "Juris Doctor (J.D.)"


def test_pick_degree_substring_match() -> None:
    options = ["Bachelor of Science in Computer Science", "High School Diploma"]
    picked = pick_degree_from_options("Bachelor of Science", options)
    assert picked == "Bachelor of Science in Computer Science"


def test_align_degree_uses_level_generic_option() -> None:
    options = ["Associate's Degree", "Bachelor's Degree"]
    aligned = align_degree_to_form_options("Associate of Applied Science", options)
    assert aligned == "Associate's Degree"


def test_best_fallback_label_from_options() -> None:
    options = ["Doctor of Philosophy (Ph.D.)", "Bachelor's Degree"]
    aligned = align_degree_to_form_options("Ph.D.", options)
    assert "Ph" in aligned or "Doctor" in aligned


def test_classify_parenthetical_variant() -> None:
    spec = classify_degree("Degree (MBA)")
    assert spec is not None
    assert spec.key == "mba"


def test_classify_degree_no_match() -> None:
    assert classify_degree("Underwater Basket Weaving") is None


def test_jd_option_allowed_rejects_generic_bachelor() -> None:
    jd_spec = next(s for s in DEGREE_ALIAS_SPECS if s.key == "jd")
    assert _option_allowed_for_spec(jd_spec, "Bachelor's Degree") is False
    assert _option_allowed_for_spec(jd_spec, "Juris Doctor (J.D.)") is True


def test_pick_level_generic_option_bachelor() -> None:
    ba_spec = next(s for s in DEGREE_ALIAS_SPECS if s.key == "ba")
    picked = _pick_level_generic_option(ba_spec, ["High School", "Bachelor's Degree"])
    assert picked == "Bachelor's Degree"


def test_pick_level_generic_option_unknown_level() -> None:
    spec = next(s for s in DEGREE_ALIAS_SPECS if s.key == "high_school")
    assert _pick_level_generic_option(spec, []) is None


def test_best_fallback_label_prefers_matching_option() -> None:
    phd_spec = next(s for s in DEGREE_ALIAS_SPECS if s.key == "phd")
    label = _best_fallback_label(phd_spec, ["Other", "Doctor of Philosophy (Ph.D.)"])
    assert label == "Doctor of Philosophy (Ph.D.)"


def test_best_fallback_label_uses_level_generic() -> None:
    ms_spec = next(s for s in DEGREE_ALIAS_SPECS if s.key == "ms")
    label = _best_fallback_label(ms_spec, ["Master's Degree"])
    assert label == "Master's Degree"


def test_best_fallback_label_without_options() -> None:
    ba_spec = next(s for s in DEGREE_ALIAS_SPECS if s.key == "ba")
    assert _best_fallback_label(ba_spec, []) == ba_spec.fallback_labels[0]


def test_pick_degree_empty_inputs() -> None:
    assert pick_degree_from_options("", ["Bachelor's Degree"]) is None
    assert pick_degree_from_options("B.A.", []) is None


def test_pick_degree_unclassifiable_text() -> None:
    assert pick_degree_from_options("Certificate of Awesomeness", ["Bachelor's Degree"]) is None


def test_pick_degree_substring_fallback() -> None:
    options = ["B.S. (Honors)"]
    picked = pick_degree_from_options("B.S.", options)
    assert picked == "B.S. (Honors)"


def test_align_degree_empty_text() -> None:
    assert align_degree_to_form_options("", []) == ""
    assert align_degree_to_form_options("   ", []) == ""


def test_align_degree_best_fallback_when_no_option_match() -> None:
    aligned = align_degree_to_form_options("Ph.D.", ["Bachelor's Degree"])
    assert "Ph" in aligned or "Doctor" in aligned


def test_best_fallback_label_skips_jd_bachelor_option() -> None:
    jd_spec = next(s for s in DEGREE_ALIAS_SPECS if s.key == "jd")
    label = _best_fallback_label(jd_spec, ["Bachelor's Degree", "Juris Doctor (J.D.)"])
    assert label == "Juris Doctor (J.D.)"


def test_pick_degree_level_generic_master() -> None:
    picked = pick_degree_from_options("M.S.", ["High School", "Master's Degree"])
    assert picked == "Master's Degree"


def test_align_degree_best_fallback_with_unmatched_options() -> None:
    aligned = align_degree_to_form_options("M.S.", ["High School Diploma"])
    assert "Master" in aligned


def test_align_degree_returns_raw_when_unclassifiable() -> None:
    raw = "Custom Professional Certificate"
    assert align_degree_to_form_options(raw, []) == raw


def test_best_fallback_uses_level_generic_when_labels_do_not_match() -> None:
    ms_spec = next(s for s in DEGREE_ALIAS_SPECS if s.key == "ms")
    # No fallback label substring match — only generic master's option fits.
    label = _best_fallback_label(ms_spec, ["Unrelated Option", "Master's Degree"])
    assert label == "Master's Degree"
