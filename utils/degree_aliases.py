"""
Canonical degree alias normalization for ATS dropdowns (Greenhouse, Ashby, etc.).

Maps common abbreviations and full titles (BA, BS, MSc, MBA, LLB, PhD, …) to
preferred option labels and option-matching predicates. Sources: Wiktionary
Appendix:Academic degrees, common US job-board dropdowns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

OptionMatcher = Callable[[str], bool]


@dataclass(frozen=True)
class DegreeAliasSpec:
    """One canonical degree family (most-specific specs are listed first)."""

    key: str
    patterns: Tuple[str, ...]
    fallback_labels: Tuple[str, ...]
    option_matchers: Tuple[OptionMatcher, ...]

    def compiled_patterns(self) -> Tuple[re.Pattern[str], ...]:
        return tuple(re.compile(p, re.IGNORECASE) for p in self.patterns)


def _opt_contains(*needles: str) -> OptionMatcher:
    def _match(option_text: str) -> bool:
        low = option_text.lower()
        return any(n in low for n in needles)

    return _match


def _opt_regex(pattern: str) -> OptionMatcher:
    rx = re.compile(pattern, re.IGNORECASE)

    def _match(option_text: str) -> bool:
        return bool(rx.search(option_text))

    return _match


# Order matters: first matching spec wins (specific before generic).
DEGREE_ALIAS_SPECS: Tuple[DegreeAliasSpec, ...] = (
    DegreeAliasSpec(
        "high_school",
        (
            r"\bhigh\s+school\b",
            r"\bsecondary\s+school\b",
            r"\bg\.?e\.?d\.?\b",
            r"\bhs\s+diploma\b",
        ),
        ("High School", "High School Diploma", "GED"),
        (_opt_contains("high school", "ged"),),
    ),
    DegreeAliasSpec(
        "associate",
        (
            r"\bassociate'?s?\s+(of\s+)?(arts|science|applied)\b",
            r"\bassociate\s+degree\b",
            r"\ba\.?a\.?\s*(s\.?|degree)?\b",
            r"\ba\.?s\.?\s*(s\.?|degree)?\b",
            r"\ba\.?a\.?s\.?\b",
            r"\baa\b",
            r"\bas\b(?!\s*(?:in|of)\s)",
        ),
        ("Associate's Degree", "Associate of Arts (AA)", "Associate of Science (AS)"),
        (
            _opt_contains("associate"),
            _opt_regex(r"\(\s*aa\s*\)"),
            _opt_regex(r"\(\s*as\s*\)"),
        ),
    ),
    DegreeAliasSpec(
        "phd",
        (
            r"\bph\.?\s*d\.?\b",
            r"\bd\.?\s*phil\.?\b",
            r"\bdphil\b",
            r"\bdoctor\s+of\s+philosophy\b",
        ),
        ("Doctor of Philosophy (Ph.D.)", "Ph.D.", "Doctorate"),
        (
            _opt_contains("doctor of philosophy"),
            _opt_regex(r"ph\.?\s*d"),
            _opt_contains("doctorate"),
        ),
    ),
    DegreeAliasSpec(
        "md",
        (
            r"\bm\.?\s*d\.?\b(?!\s*and)",
            r"\bdoctor\s+of\s+medicine\b",
            r"\bmedicinae\s+doctor\b",
        ),
        ("Doctor of Medicine (M.D.)", "M.D.", "Medical Doctor"),
        (_opt_contains("doctor of medicine", "m.d", "medical doctor"),),
    ),
    DegreeAliasSpec(
        "jd",
        (
            r"\bj\.?\s*d\.?\b",
            r"\bjuris\s+doctor\b",
            r"\bdoctor\s+of\s+jurisprudence\b",
        ),
        ("Juris Doctor (J.D.)", "J.D.", "Doctor of Law"),
        (
            _opt_contains("juris doctor", "j.d"),
            _opt_contains("doctor of law"),
        ),
    ),
    DegreeAliasSpec(
        "llb",
        (
            r"\bl\.?\s*l\.?\s*b\.?\b",
            r"\bbachelor\s+of\s+laws\b",
            r"\bb\.?\s*l\.?\b",
            r"^law$",
            r"^laws$",
        ),
        ("Bachelor's Degree", "Bachelor of Laws (LLB)", "Juris Doctor (J.D.)"),
        (
            _opt_contains("bachelor of laws", "llb"),
            _opt_contains("bachelor's degree", "bachelors degree"),
            _opt_contains("juris doctor", "j.d"),
        ),
    ),
    DegreeAliasSpec(
        "pharmd",
        (r"\bpharm\.?\s*d\.?\b", r"\bdoctor\s+of\s+pharmacy\b"),
        ("Doctor of Pharmacy (PharmD)", "PharmD", "Pharm.D."),
        (_opt_contains("pharmacy", "pharmd", "pharm.d"),),
    ),
    DegreeAliasSpec(
        "dpt",
        (r"\bd\.?\s*p\.?\s*t\.?\b", r"\bdoctor\s+of\s+physical\s+therapy\b"),
        ("Doctor of Physical Therapy (DPT)", "DPT"),
        (_opt_contains("physical therapy", "dpt"),),
    ),
    DegreeAliasSpec(
        "psyd",
        (r"\bpsy\.?\s*d\.?\b", r"\bdoctor\s+of\s+psychology\b"),
        ("Doctor of Psychology (PsyD)", "PsyD", "Psy.D."),
        (_opt_contains("psychology", "psyd", "psy.d"),),
    ),
    DegreeAliasSpec(
        "edd",
        (r"\be\.?\s*d\.?\s*d\.?\b", r"\bdoctor\s+of\s+education\b"),
        ("Doctor of Education (EdD)", "EdD", "Ed.D."),
        (_opt_contains("doctor of education", "edd", "ed.d"),),
    ),
    DegreeAliasSpec(
        "dba",
        (r"\bd\.?\s*b\.?\s*a\.?\b", r"\bdoctor\s+of\s+business\s+administration\b"),
        ("Doctor of Business Administration (DBA)", "DBA", "D.B.A."),
        (_opt_contains("doctor of business", "dba", "d.b.a"),),
    ),
    DegreeAliasSpec(
        "ba",
        (
            r"\bb\.?\s*a\.?\b",
            r"\bab\b",
            r"\ba\.?\s*b\.?\b",
            r"\bbachelor\s+of\s+arts\b",
            r"\bb\.?\s*arts\b",
        ),
        ("Bachelor's Degree", "Bachelor of Arts (BA)", "BA"),
        (
            _opt_contains("bachelor of arts"),
            _opt_regex(r"\(\s*ba\s*\)"),
            _opt_contains("bachelor's degree", "bachelors degree"),
        ),
    ),
    DegreeAliasSpec(
        "bs",
        (
            r"\bb\.?\s*s\.?\b(?!\s*n\b)",
            r"\bb\.?\s*sc\.?\b",
            r"\bbsc\b",
            r"\bs\.?\s*b\.?\b",
            r"\bsc\.?\s*b\.?\b",
            r"\bbachelor\s+of\s+science\b",
        ),
        ("Bachelor's Degree", "Bachelor of Science (BS)", "BS"),
        (
            _opt_contains("bachelor of science"),
            _opt_regex(r"\(\s*bs\s*\)"),
            _opt_regex(r"\(\s*b\.?\s*sc\.?\s*\)"),
            _opt_contains("bachelor's degree", "bachelors degree"),
        ),
    ),
    DegreeAliasSpec(
        "bba",
        (r"\bb\.?\s*b\.?\s*a\.?\b", r"\bbachelor\s+of\s+business\s+administration\b"),
        ("Bachelor of Business Administration (BBA)", "BBA", "Bachelor's Degree"),
        (
            _opt_contains("business administration", "bba", "b.b.a"),
            _opt_regex(r"\(\s*bba\s*\)"),
        ),
    ),
    DegreeAliasSpec(
        "beng",
        (r"\bb\.?\s*eng\.?\b", r"\bbachelor\s+of\s+engineering\b"),
        ("Bachelor of Engineering (BEng)", "BEng", "Bachelor's Degree"),
        (_opt_contains("bachelor of engineering", "beng", "b.eng"),),
    ),
    DegreeAliasSpec(
        "bfa",
        (r"\bb\.?\s*f\.?\s*a\.?\b", r"\bbachelor\s+of\s+fine\s+arts\b"),
        ("Bachelor of Fine Arts (BFA)", "BFA", "Bachelor's Degree"),
        (_opt_contains("fine arts", "bfa", "b.f.a"),),
    ),
    DegreeAliasSpec(
        "bed",
        (r"\bb\.?\s*ed\.?\b", r"\bbachelor\s+of\s+education\b"),
        ("Bachelor of Education (BEd)", "BEd", "Bachelor's Degree"),
        (_opt_contains("bachelor of education", "bed", "b.ed"),),
    ),
    DegreeAliasSpec(
        "barch",
        (r"\bb\.?\s*arch\.?\b", r"\bbachelor\s+of\s+architecture\b"),
        ("Bachelor of Architecture (BArch)", "BArch", "Bachelor's Degree"),
        (_opt_contains("architecture", "barch", "b.arch"),),
    ),
    DegreeAliasSpec(
        "bsw",
        (r"\bb\.?\s*s\.?\s*w\.?\b", r"\bbachelor\s+of\s+social\s+work\b"),
        ("Bachelor of Social Work (BSW)", "BSW", "Bachelor's Degree"),
        (_opt_contains("social work", "bsw", "b.s.w"),),
    ),
    DegreeAliasSpec(
        "becon",
        (
            r"\bb\.?\s*econ\.?\b",
            r"\bbecon\b",
            r"\bbachelor\s+of\s+economics\b",
            r"\bb\.?\s*sc\.?\s*\(?\s*econ",
        ),
        ("Bachelor of Arts (BA)", "Bachelor of Science (BS)", "Bachelor's Degree"),
        (
            _opt_contains("economics", "econ"),
            _opt_contains("bachelor of arts", "bachelor of science", "bachelor's"),
        ),
    ),
    DegreeAliasSpec(
        "bachelor_generic",
        (
            r"\bbachelor'?s?\s*(degree|s)?\b",
            r"\bundergraduate\s+degree\b",
            r"\bundergrad\b",
            r"\bbaccalaureate\b",
        ),
        ("Bachelor's Degree", "Bachelor of Arts (BA)", "Bachelor of Science (BS)"),
        (
            _opt_contains("bachelor's degree", "bachelors degree"),
            _opt_contains("bachelor"),
        ),
    ),
    DegreeAliasSpec(
        "llm",
        (r"\bl\.?\s*l\.?\s*m\.?\b", r"\bmaster\s+of\s+laws\b"),
        ("Master of Laws (LLM)", "LLM", "Master's Degree"),
        (_opt_contains("master of laws", "llm", "l.l.m"),),
    ),
    DegreeAliasSpec(
        "mba",
        (
            r"\bm\.?\s*b\.?\s*a\.?\b",
            r"\bmaster\s+of\s+business\s+administration\b",
            r"\be\.?\s*m\.?\s*b\.?\s*a\.?\b",
            r"\bexecutive\s+mba\b",
        ),
        ("Master of Business Administration (M.B.A.)", "MBA", "M.B.A.", "Master's Degree"),
        (
            _opt_contains("business administration", "mba", "m.b.a"),
            _opt_regex(r"\(\s*mba\s*\)"),
        ),
    ),
    DegreeAliasSpec(
        "ms",
        (
            r"\bm\.?\s*s\.?\b(?!\s*w\b)",
            r"\bm\.?\s*sc\.?\b",
            r"\bmsc\b",
            r"\bmaster\s+of\s+science\b",
        ),
        ("Master of Science (MS)", "Master's Degree", "MS"),
        (
            _opt_contains("master of science"),
            _opt_regex(r"\(\s*ms\s*\)"),
            _opt_regex(r"\(\s*m\.?\s*sc\.?\s*\)"),
        ),
    ),
    DegreeAliasSpec(
        "ma",
        (r"\bm\.?\s*a\.?\b", r"\bmaster\s+of\s+arts\b", r"\ba\.?\s*m\.?\b"),
        ("Master of Arts (MA)", "Master's Degree", "MA"),
        (
            _opt_contains("master of arts"),
            _opt_regex(r"\(\s*ma\s*\)"),
        ),
    ),
    DegreeAliasSpec(
        "meng",
        (r"\bm\.?\s*eng\.?\b", r"\bmaster\s+of\s+engineering\b"),
        ("Master of Engineering (MEng)", "Master's Degree", "MEng"),
        (_opt_contains("master of engineering", "meng", "m.eng"),),
    ),
    DegreeAliasSpec(
        "med",
        (r"\bm\.?\s*ed\.?\b", r"\bmaster\s+of\s+education\b"),
        ("Master of Education (MEd)", "Master's Degree", "MEd"),
        (_opt_contains("master of education", "med", "m.ed"),),
    ),
    DegreeAliasSpec(
        "mfa",
        (r"\bm\.?\s*f\.?\s*a\.?\b", r"\bmaster\s+of\s+fine\s+arts\b"),
        ("Master of Fine Arts (MFA)", "Master's Degree", "MFA"),
        (_opt_contains("fine arts", "mfa", "m.f.a"),),
    ),
    DegreeAliasSpec(
        "mph",
        (r"\bm\.?\s*p\.?\s*h\.?\b", r"\bmaster\s+of\s+public\s+health\b"),
        ("Master of Public Health (MPH)", "Master's Degree", "MPH"),
        (_opt_contains("public health", "mph", "m.p.h"),),
    ),
    DegreeAliasSpec(
        "msw",
        (r"\bm\.?\s*s\.?\s*w\.?\b", r"\bmaster\s+of\s+social\s+work\b"),
        ("Master of Social Work (MSW)", "Master's Degree", "MSW"),
        (_opt_contains("social work", "msw", "m.s.w"),),
    ),
    DegreeAliasSpec(
        "mpa",
        (r"\bm\.?\s*p\.?\s*a\.?\b", r"\bmaster\s+of\s+public\s+administration\b"),
        ("Master of Public Administration (MPA)", "Master's Degree", "MPA"),
        (_opt_contains("public administration", "mpa", "m.p.a"),),
    ),
    DegreeAliasSpec(
        "master_generic",
        (
            r"\bmaster'?s?\s*(degree|s)?\b",
            r"\bpostgraduate\s+degree\b",
            r"\bgraduate\s+degree\b",
        ),
        ("Master's Degree", "Master of Science (MS)", "Master of Arts (MA)"),
        (
            _opt_contains("master's degree", "masters degree"),
            _opt_contains("master"),
        ),
    ),
)

_COMPILED_SPECS: Tuple[Tuple[DegreeAliasSpec, Tuple[re.Pattern[str], ...]], ...] = tuple(
    (spec, spec.compiled_patterns()) for spec in DEGREE_ALIAS_SPECS
)

# Maps a spec key to a coarse level used when ATS dropdowns only offer generic labels
# (e.g. Greenhouse "Bachelor's Degree" instead of "Bachelor of Arts (BA)").
_SPEC_LEVEL: Dict[str, str] = {
    "high_school": "high_school",
    "associate": "associate",
    "ba": "bachelor",
    "bs": "bachelor",
    "bba": "bachelor",
    "beng": "bachelor",
    "bfa": "bachelor",
    "bed": "bachelor",
    "barch": "bachelor",
    "bsw": "bachelor",
    "becon": "bachelor",
    "bachelor_generic": "bachelor",
    "llm": "master",
    "mba": "master",
    "ms": "master",
    "ma": "master",
    "meng": "master",
    "med": "master",
    "mfa": "master",
    "mph": "master",
    "msw": "master",
    "mpa": "master",
    "master_generic": "master",
    "phd": "doctorate",
    "md": "doctorate",
    "jd": "law",
    "llb": "bachelor",
    "pharmd": "doctorate",
    "dpt": "doctorate",
    "psyd": "doctorate",
    "edd": "doctorate",
    "dba": "doctorate",
}

_LEVEL_OPTION_NEEDLES: Dict[str, Tuple[str, ...]] = {
    "high_school": ("high school", "ged"),
    "associate": ("associate's degree", "associate's", "associate of"),
    "bachelor": ("bachelor's degree", "bachelors degree"),
    "master": ("master's degree", "masters degree"),
    "law": ("juris doctor", "j.d", "bachelor of laws", "llb"),
    "doctorate": ("doctor of philosophy", "ph.d", "doctor of medicine", "m.d"),
}


def _is_generic_bachelor_option(option_text: str) -> bool:
    low = option_text.lower()
    return (
        "bachelor" in low
        and "juris" not in low
        and "llb" not in low
        and "l.l.b" not in low
        and "laws" not in low
    )


def _option_allowed_for_spec(spec: DegreeAliasSpec, option_text: str) -> bool:
    if spec.key == "jd" and _is_generic_bachelor_option(option_text):
        return False
    return True


def _pick_level_generic_option(spec: DegreeAliasSpec, options: Sequence[str]) -> Optional[str]:
    """Pick a generic dropdown label when only coarse degree levels are offered."""
    level = _SPEC_LEVEL.get(spec.key)
    if not level:
        return None
    needles = _LEVEL_OPTION_NEEDLES.get(level, ())
    for needle in needles:
        for opt in options:
            if needle in opt.lower() and _option_allowed_for_spec(spec, opt):
                return opt
    return None


def _best_fallback_label(spec: DegreeAliasSpec, options: Sequence[str]) -> str:
    """Prefer a fallback label that exists in scraped options when possible."""
    if options:
        opt_lows = [o.lower() for o in options]
        for label in spec.fallback_labels:
            low = label.lower()
            for opt, opt_low in zip(options, opt_lows):
                if not _option_allowed_for_spec(spec, opt):
                    continue
                if low == opt_low or low in opt_low or opt_low in low:
                    return opt
        picked = _pick_level_generic_option(spec, options)
        if picked:
            return picked
    return spec.fallback_labels[0]


def _degree_match_variants(raw: str) -> List[str]:
    text = (raw or "").strip()
    if not text:
        return []
    variants = [re.sub(r"\s+", " ", text).lower()]
    for chunk in re.findall(r"\(([^)]+)\)", text):
        chunk = chunk.strip()
        if chunk:
            variants.append(chunk.lower())
    return variants


def classify_degree(raw: str) -> Optional[DegreeAliasSpec]:
    """Return the best matching degree spec for a profile degree string, or None."""
    variants = _degree_match_variants(raw)
    if not variants:
        return None
    for spec, patterns in _COMPILED_SPECS:
        for variant in variants:
            for pattern in patterns:
                if pattern.search(variant):
                    return spec
    return None


def pick_degree_from_options(raw: str, options: Sequence[str]) -> Optional[str]:
    """Pick the best dropdown option label for a profile degree string."""
    text = (raw or "").strip()
    if not text or not options:
        return None
    low = re.sub(r"\s+", " ", text).lower()
    for opt in options:
        if opt.lower() == low:
            return opt
    spec = classify_degree(text)
    if not spec:
        return None
    for matcher in spec.option_matchers:
        for opt in options:
            if matcher(opt) and _option_allowed_for_spec(spec, opt):
                return opt
    picked = _pick_level_generic_option(spec, options)
    if picked:
        return picked
    if low and len(low) >= 4:
        for opt in options:
            opt_low = opt.lower()
            if low in opt_low or opt_low in low:
                return opt
    return None


def align_degree_to_form_options(raw: str, options: Sequence[str]) -> str:
    """
    Map profile degree strings to ATS dropdown labels.

    Uses scraped options when available; otherwise returns a canonical fallback.
    """
    text = (raw or "").strip()
    if not text:
        return text
    if options:
        picked = pick_degree_from_options(text, options)
        if picked:
            return picked
    spec = classify_degree(text)
    if spec and spec.fallback_labels:
        return _best_fallback_label(spec, options)
    return text
