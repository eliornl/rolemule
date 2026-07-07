"""
Deterministic profile-to-form-field mapping for extension autofill.

Runs after the LLM (or on cache replay) so known fields — name, email, screening
questions — are filled reliably from profile data without model guesswork.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from api.extension_autofill_models import AutofillFieldIn

# =============================================================================
# LABEL PATTERNS
# =============================================================================

_NAME_LABEL_RE = re.compile(
    r"\b(full\s+)?(legal\s+)?(applicant\s+)?name\b",
    re.IGNORECASE,
)
_BAD_NAME_LABEL_RE = re.compile(
    r"\b(company|employer|school|university|reference|hiring\s+manager)\s+name\b",
    re.IGNORECASE,
)
_FIRST_NAME_RE = re.compile(r"\bfirst(\s+|-)?name\b", re.IGNORECASE)
_LAST_NAME_RE = re.compile(r"\blast(\s+|-)?name\b", re.IGNORECASE)
_MIDDLE_NAME_RE = re.compile(r"\bmiddle(\s+|-)?name\b", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b(e[-]?mail|email address)\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"\b(phone|mobile|telephone|cell)\b", re.IGNORECASE)
_US_BASED_RE = re.compile(
    r"\b("
    r"based in the united states"
    r"|currently based in"
    r"|currently (in|based in) the (us|u\.s\.|united states)"
    r"|located in the (us|u\.s\.|united states)"
    r"|live in the (us|u\.s\.|united states)"
    r")\b",
    re.IGNORECASE,
)
_SPONSORSHIP_RE = re.compile(
    r"\b("
    r"(visa|employment)\s+sponsorship"
    r"|h[- ]?1b\s+sponsorship"
    r"|new\s+h[- ]?1b"
    r"|require\s+(employment\s+)?sponsorship"
    r"|need\s+(employment\s+)?sponsorship"
    r"|sponsorship to work"
    r"|sponsorship for employment"
    r"|sponsor you for an employment visa"
    r"|sponsor\b.{0,80}\bemployment\s+visa\b"
    r")\b|"
    r"(?:require|need)\b.{0,160}\bsponsor\b.{0,100}\bvisa\b",
    re.IGNORECASE,
)
_WORK_AUTH_RE = re.compile(
    r"\b("
    r"authorized to work"
    r"|legally authorized"
    r"|eligible to work"
    r"|authorization to work"
    r"|work authorization"
    r")\b",
    re.IGNORECASE,
)
_IN_OFFICE_RE = re.compile(
    r"\b("
    r"work in[- ]person"
    r"|in[- ]person in"
    r"|on[- ]site"
    r"|work in the office"
    r"|cannot work remotely"
    r"|do not allow remote"
    r"|does that work for you"
    r"|open to working \d+ days onsite"
    r")\b",
    re.IGNORECASE,
)
_TRI_STATE_COMMUTE_RE = re.compile(
    r"\b("
    r"tri[- ]?state"
    r"|commute into.*office"
    r"|able to commute"
    r"|commuting distance"
    r"|located in.*commute"
    r"|based in nyc.*located"
    r")\b",
    re.IGNORECASE | re.DOTALL,
)
_CENTRAL_OFFICE_RELOC_RE = re.compile(
    r"\b("
    r"not local to.*central office"
    r"|central office.*relocate"
    r"|currently not local.*relocate"
    r"|not local.*willing to relocate"
    r")\b",
    re.IGNORECASE | re.DOTALL,
)
_STARTUP_RE = re.compile(
    r"\b(prepared to work at a startup|work at a startup|startup environment)\b",
    re.IGNORECASE,
)
# Ashby sometimes serializes helper paragraph instead of the question line.
_STARTUP_ASHBY_HELPER_RE = re.compile(
    r"\b(generational company|long hours|performance culture|extremely difficult)\b",
    re.IGNORECASE,
)
_EEO_RE = re.compile(
    r"\b("
    r"eeo|equal employment|veteran status|disability status|"
    r"race|ethnicity|gender identity|demographic|hispanic|latino|\bgender\b"
    r")\b",
    re.IGNORECASE,
)
_COUNTRY_LABEL_RE = re.compile(
    r"\b(country|country of residence|country/region)\b",
    re.IGNORECASE,
)
_CITY_LOCATION_RE = re.compile(
    r"("
    r"location\s*\(\s*city\s*\)"
    r"|\blocation\b[^\n]{0,40}\bcity\b"
    r"|\bcity\b[^\n]{0,40}\blocation\b"
    r"|^location\s*\*?\s*$"
    r"|current (city|location)"
    r"|city of residence|home city"
    r"|your (city|location)"
    r"|where (are you|do you) (located|live|based)"
    r")",
    re.IGNORECASE,
)
_STATE_ONLY_RE = re.compile(
    r"\b(state|province|region)\s*(\*|$)",
    re.IGNORECASE,
)
_YEARS_EXP_RE = re.compile(
    r"\b("
    r"\d+\+\s*years?|"
    r"years of (industry )?experience|"
    r"years of relevant experience|"
    r"have \d+\+ years?"
    r")\b",
    re.IGNORECASE,
)
_SALARY_EXPECT_RE = re.compile(
    r"\b("
    r"salary\s+expectations?|"
    r"compensation\s+expectations?|"
    r"expected\s+salary|"
    r"desired\s+salary|"
    r"pay\s+expectations?|"
    r"salary.*\(\s*in\s*\$"
    r")\b",
    re.IGNORECASE,
)
_START_TIMELINE_RE = re.compile(
    r"\b("
    r"how quickly.*start|"
    r"looking to start|"
    r"start a new role|"
    r"when can you start|"
    r"earliest start|"
    r"notice period|"
    r"availability to start"
    r")\b",
    re.IGNORECASE | re.DOTALL,
)
_DEFAULT_START_NOTICE_ANSWER = "I can start a new role in 2 weeks."
_WEBSITE_RE = re.compile(
    r"\b(website|portfolio|personal site|personal website)\b",
    re.IGNORECASE,
)
_GITHUB_RE = re.compile(r"\bgithub\b", re.IGNORECASE)
_GITHUB_USERNAME_FIELD_RE = re.compile(
    r"github\s*(username|user\s*name|handle)\b",
    re.IGNORECASE,
)
_LINKEDIN_RE = re.compile(r"\blinkedin\b", re.IGNORECASE)
_ACKNOWLEDGE_RE = re.compile(
    r"\b("
    r"by checking this box"
    r"|i agree to allow"
    r"|store and process my data"
    r"|retain my data"
    r"|processing my (personal )?data"
    r"|data for the purpose"
    r"|future opportunities for employment"
    r"|privacy (policy|notice)"
    r"|consent to (the )?(processing|storage|collection)"
    r"|acknowledge.*agree"
    r"|confirm.*agree"
    r"|agree to the following"
    r")\b",
    re.IGNORECASE | re.DOTALL,
)
_WORK_LOCATION_ACK_RE = re.compile(
    r"acknowledge.*work\s+location|work\s+location\s+expectations",
    re.IGNORECASE | re.DOTALL,
)
_MARKETING_OPT_IN_RE = re.compile(
    r"\b(newsletter|marketing emails?|promotional offers?|send me (job )?alerts)\b",
    re.IGNORECASE,
)
_DEGREE_RE = re.compile(r"\bdegree\b", re.IGNORECASE)
_DISCIPLINE_RE = re.compile(
    r"\b(discipline|major|field of study|concentration)\b",
    re.IGNORECASE,
)
_SCHOOL_RE = re.compile(
    r"\b(school|university|college|institution)\b",
    re.IGNORECASE,
)
_LOCATION_IN_LABEL_RE = re.compile(
    r"\b(?:in[- ]person in|work in)\s+([A-Za-z .,\-]+?)(?:\?|\*|\.|$)",
    re.IGNORECASE,
)

_US_COUNTRY_VALUES = frozenset(
    {
        "us",
        "usa",
        "u.s.",
        "u.s.a.",
        "united states",
        "united states of america",
    }
)
_US_WORK_AUTH = frozenset(
    {
        "us_citizen",
        "us_lawful_permanent_resident",
        "has_work_authorization",
    }
)

_NYC_METRO_CITIES = frozenset(
    {
        "new york",
        "brooklyn",
        "manhattan",
        "queens",
        "bronx",
        "staten island",
        "hoboken",
        "jersey city",
        "newark",
        "yonkers",
        "white plains",
    }
)
_NYC_STATES = frozenset({"ny", "new york"})

_COUNTRY_CODE_TO_DISPLAY: Dict[str, str] = {
    "us": "United States",
    "usa": "United States",
    "u.s.": "United States",
    "u.s.a.": "United States",
    "united states": "United States",
    "united states of america": "United States",
    "ca": "Canada",
    "canada": "Canada",
    "gb": "United Kingdom",
    "uk": "United Kingdom",
    "united kingdom": "United Kingdom",
    "il": "Israel",
    "israel": "Israel",
    "de": "Germany",
    "germany": "Germany",
    "fr": "France",
    "france": "France",
    "in": "India",
    "india": "India",
}


# =============================================================================
# HELPERS
# =============================================================================


def _norm_label(label: str) -> str:
    return re.sub(r"\s+", " ", (label or "").strip())


def _label_blob(field: AutofillFieldIn) -> str:
    parts = [
        field.label_text or "",
        field.placeholder or "",
        field.aria_label or "",
        field.name_attr or "",
        field.id_attr or "",
    ]
    return _norm_label(" ".join(p for p in parts if p))


def _profile_dict(bundle: Dict[str, Any]) -> Dict[str, Any]:
    prof = bundle.get("profile")
    return prof if isinstance(prof, dict) else {}


def _split_full_name(full_name: str) -> tuple[str, str, str]:
    """Return (first, middle, last) tokens from a full name."""
    parts = [p for p in re.split(r"\s+", (full_name or "").strip()) if p]
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "", parts[0]
    first = parts[0]
    last = parts[-1]
    middle = " ".join(parts[1:-1]) if len(parts) > 2 else ""
    return first, middle, last


def _family_name_from_full_name(full_name: str) -> str:
    """Last-name fields: all tokens after the first given name (e.g. Nataf Lackritz)."""
    parts = [p for p in re.split(r"\s+", (full_name or "").strip()) if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return " ".join(parts[1:])


def _sponsorship_answer(field: AutofillFieldIn, prof: Dict[str, Any]) -> Optional[str]:
    """
    Visa / employment sponsorship screening.

    Yes = candidate needs sponsorship. No = already authorized / does not need it.
    """
    label = _label_blob(field)
    if not _SPONSORSHIP_RE.search(label):
        return None

    if "requires_visa_sponsorship" in prof and not bool(prof.get("requires_visa_sponsorship")):
        flag = False
    else:
        flag = None
        if "requires_visa_sponsorship" in prof:
            flag = bool(prof.get("requires_visa_sponsorship"))
        wa = prof.get("work_authorization")
        if wa in _US_WORK_AUTH or wa == "has_work_authorization":
            # Authorized to work → does not need future sponsorship (profile flag wins if set).
            if flag is None or flag is False:
                flag = False
        if flag is None:
            return None

    options = _option_texts(field)
    if options:
        want_yes = flag
        picked = _pick_option(
            options,
            lambda t: t.lower().startswith("yes") if want_yes else t.lower().startswith("no"),
        )
        if picked:
            return picked
    return _yes_no_from_bool(flag)


def _location_city_field_excluded(label: str) -> bool:
    """True when label is relocation / office / preferences — not applicant city."""
    low = label.lower()
    if _COUNTRY_LABEL_RE.search(label):
        return True
    if _STATE_ONLY_RE.search(label) and "city" not in low:
        return True
    if _IN_OFFICE_RE.search(label) or _LOCATION_IN_LABEL_RE.search(label):
        return True
    if _CENTRAL_OFFICE_RELOC_RE.search(label):
        return True
    if "relocation" in low or "relocate" in low:
        return True
    if "office" in low and "location" in low:
        return True
    if "location preference" in low or "preferred location" in low:
        return True
    if "work location" in low and "city" not in low:
        return True
    return False


def _is_profile_city_location_field(label: str) -> bool:
    if _location_city_field_excluded(label):
        return False
    if _CITY_LOCATION_RE.search(label):
        return True
    low = label.lower()
    if "learn about" in low or "job source" in low or "hear about" in low:
        return False
    if re.search(r"(?:^|[\s_./-])(?:systemfield_)?location(?:[\s_*/-]|$)", label, re.I):
        return True
    return bool(re.search(r"\blocation\b", label, re.I) and re.search(r"\bcity\b", label, re.I))


def _location_city_answer(prof: Dict[str, Any]) -> Optional[str]:
    """Greenhouse 'Location (City)' and similar — city + state from profile."""
    city = (prof.get("city") or "").strip()
    state = (prof.get("state") or "").strip()
    if not city:
        return None
    if state:
        return f"{city}, {state}"
    return city


def _country_display_name(country: Optional[str]) -> Optional[str]:
    if not country or not str(country).strip():
        return None
    norm = re.sub(r"[^a-z ]", "", str(country).lower()).strip()
    if norm in _COUNTRY_CODE_TO_DISPLAY:
        return _COUNTRY_CODE_TO_DISPLAY[norm]
    # Already a readable name — pass through with title case words
    raw = str(country).strip()
    if len(raw) >= 3 and " " in raw:
        return raw
    return raw.upper() if len(raw) <= 3 else raw


def _education_entries(prof: Dict[str, Any]) -> List[Dict[str, Any]]:
    edu = prof.get("education") or []
    if not isinstance(edu, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in edu:
        if isinstance(item, dict):
            out.append(item)
    return out


def _align_degree_to_form_options(raw: str, options: Sequence[str]) -> str:
    """Map profile degree strings to ATS dropdown labels via ``utils.degree_aliases``."""
    from utils.degree_aliases import align_degree_to_form_options

    return align_degree_to_form_options(raw, options)


def _years_experience_bucket_fallback(years: int) -> str:
    """Standard bucket when combobox options were not scraped from the client."""
    if years <= 7:
        return "5-7"
    if years <= 10:
        return "8-10"
    return "11+"


def _is_yes_no_option_set(options: Sequence[str]) -> bool:
    """True only for plain Yes/No choices — not 'Yes, and I currently live…' combobox rows."""
    if not options:
        return False
    for opt in options:
        low = opt.strip().lower()
        if low in ("yes", "no"):
            continue
        if re.match(r"^(yes|no)[\s.!?]*$", low):
            continue
        return False
    return True


def _parse_plus_years_threshold(label: str) -> Optional[int]:
    """Extract N from '5+ years' / 'Do you have 5+ years of experience?'"""
    m = re.search(r"(\d+)\s*\+\s*years?", label, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def _free_text_field(field: AutofillFieldIn) -> bool:
    """Greenhouse screening text areas often omit input_type."""
    tag = (getattr(field, "tag", None) or "").strip().lower()
    if tag == "textarea":
        return True
    input_type = field.input_type
    return input_type in (None, "", "text", "textarea")


def _salary_text_field(field: AutofillFieldIn) -> bool:
    return _free_text_field(field)


def _salary_expectations_answer(prof: Dict[str, Any], field: AutofillFieldIn) -> Optional[str]:
    """
    Map profile.desired_salary_range {min, max} to numeric salary text fields.
    Returns None when the user has not set a range (field stays empty).
    """
    rng = prof.get("desired_salary_range")
    if not isinstance(rng, dict):
        return None
    lo = rng.get("min")
    hi = rng.get("max")
    try:
        lo_i = int(lo) if lo is not None else None
    except (TypeError, ValueError):
        lo_i = None
    try:
        hi_i = int(hi) if hi is not None else None
    except (TypeError, ValueError):
        hi_i = None
    if lo_i is None and hi_i is None:
        return None
    if lo_i is not None and hi_i is not None:
        if lo_i == hi_i:
            return str(lo_i)
        return f"{lo_i}-{hi_i}"
    if hi_i is not None:
        return str(hi_i)
    if lo_i is not None:
        return str(lo_i)
    return None


def _education_field_value(
    field: AutofillFieldIn,
    prof: Dict[str, Any],
    *,
    kind: str,
    index: int,
) -> Optional[str]:
    entries = _education_entries(prof)
    if index >= len(entries):
        return None
    entry = entries[index]
    if kind == "degree":
        val = entry.get("degree") or entry.get("degree_type")
    elif kind == "discipline":
        val = entry.get("field_of_study") or entry.get("major")
    elif kind == "school":
        val = entry.get("institution") or entry.get("school")
    else:
        return None
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def _is_consent_ack_label(label: str) -> bool:
    if not label or _EEO_RE.search(label):
        return False
    if _MARKETING_OPT_IN_RE.search(label):
        return False
    if _WORK_LOCATION_ACK_RE.search(label):
        return True
    return bool(_ACKNOWLEDGE_RE.search(label))


def _acknowledge_answer(field: AutofillFieldIn) -> str:
    options = _option_texts(field)
    if options:
        picked = _pick_option(
            options,
            lambda t: t.startswith("yes")
            or "agree" in t
            or "confirm" in t
            or "acknowledge" in t,
        )
        if picked:
            return picked
    return "Yes"


def _github_username_from_profile(prof: Dict[str, Any]) -> Optional[str]:
    url = (prof.get("github_url") or "").strip()
    if not url:
        return None
    m = re.search(r"github\.com/([^/?\s#]+)", url, re.IGNORECASE)
    if m:
        return m.group(1).strip("/")
    return None


def _website_url(prof: Dict[str, Any]) -> Optional[str]:
    """Portfolio first; GitHub profile URL when no portfolio (even if a GitHub Username field exists)."""
    portfolio = (prof.get("portfolio_url") or "").strip()
    if portfolio:
        return portfolio
    github = (prof.get("github_url") or "").strip()
    return github or None


def _country_is_us(country: Optional[str]) -> Optional[bool]:
    if not country or not str(country).strip():
        return None
    norm = re.sub(r"[^a-z ]", "", str(country).lower()).strip()
    if norm in _US_COUNTRY_VALUES:
        return True
    if norm and norm not in _US_COUNTRY_VALUES:
        return False
    return None


def _work_auth_implies_us(work_auth: Optional[str]) -> bool:
    return (work_auth or "").strip().lower() in _US_WORK_AUTH


def _yes_no_from_bool(flag: bool) -> str:
    return "Yes" if flag else "No"


def _option_texts(field: AutofillFieldIn) -> List[str]:
    if not field.options:
        return []
    out: List[str] = []
    for opt in field.options:
        text = (opt.text or opt.value or "").strip()
        if text:
            out.append(text)
    return out


def _pick_option(options: Sequence[str], predicate) -> Optional[str]:
    for text in options:
        if predicate(text.lower()):
            return text
    return None


def _user_in_nyc_metro(prof: Dict[str, Any]) -> bool:
    """Known NYC-metro cities/states for commute Yes/No and Greenhouse relocation rows."""
    city = (prof.get("city") or "").strip().lower()
    state = (prof.get("state") or "").strip().lower()
    if city in _NYC_METRO_CITIES:
        return True
    if state in _NYC_STATES and city:
        return True
    return False


def _label_mentions_nyc(label: str) -> bool:
    low = label.lower()
    return bool(re.search(r"\b(nyc|new york|manhattan)\b", low))


def _label_asks_nyc_area_commute(label: str) -> bool:
    """NYC metro / tri-state commute screening (Lever, Greenhouse, etc.)."""
    if _label_mentions_nyc(label) or _TRI_STATE_COMMUTE_RE.search(label):
        return True
    low = label.lower()
    return bool(
        re.search(r"\bcommute\b", low)
        and re.search(r"\b(office|nyc|new york|tri[- ]?state)\b", low)
    )


def _tri_state_commute_yes_no_answer(
    field: AutofillFieldIn, prof: Dict[str, Any]
) -> Optional[str]:
    """
    Plain Yes/No tri-state / NYC commute (Lever radio, etc.).

    Uses profile city/state against a small metro list — LLM alone often answers No.
    Long Greenhouse dropdown rows are handled separately in ``_in_office_answer``.
    """
    label = _label_blob(field)
    if not _label_asks_nyc_area_commute(label):
        return None
    options = _option_texts(field)
    if options and not _is_yes_no_option_set(options):
        return None
    if _user_in_nyc_metro(prof):
        return "Yes"
    if bool(prof.get("willing_to_relocate")):
        return "Yes"
    if (prof.get("city") or "").strip():
        return "No"
    return None


def _central_office_relocation_answer(
    field: AutofillFieldIn, prof: Dict[str, Any]
) -> Optional[str]:
    """
    Greenhouse relocation dropdown when user is / is not near a central office.

    Works even when the client cannot scrape combobox options (Greenhouse react-select).
    """
    label = _label_blob(field)
    if not _CENTRAL_OFFICE_RELOC_RE.search(label):
        return None

    options = _option_texts(field)
    in_metro = _user_in_nyc_metro(prof)
    willing = bool(prof.get("willing_to_relocate"))

    if options:
        if in_metro:
            picked = _pick_option(
                options,
                lambda t: "commuting" in t.lower()
                or ("n/a" in t.lower() and "within" in t.lower()),
            )
            if picked:
                return picked
            picked = _pick_option(
                options,
                lambda t: "currently local" in t.lower()
                or ("metropolitan" in t.lower() and "local" in t.lower()),
            )
            if picked:
                return picked
            picked = _pick_option(
                options,
                lambda t: t.strip().lower().startswith("no"),
            )
            if picked:
                return picked
        if willing:
            picked = _pick_option(
                options,
                lambda t: t.strip().lower().startswith("yes"),
            )
            if picked:
                return picked
            picked = _pick_option(
                options,
                lambda t: "relocate" in t.lower() or "relocation" in t.lower(),
            )
            if picked:
                return picked
        picked = _pick_option(
            options,
            lambda t: "not willing" in t or "cannot relocate" in t or t.strip().lower().startswith("no"),
        )
        if picked:
            return picked

    if in_metro:
        return "N/A - Within Commuting Distance"
    if willing:
        return "Yes"
    return "No"


def _years_experience_answer(
    field: AutofillFieldIn, prof: Dict[str, Any]
) -> Optional[str]:
    val = prof.get("years_experience")
    if val is None:
        return None
    try:
        years = int(val)
    except (TypeError, ValueError):
        return None
    label = _label_blob(field)
    options = _option_texts(field)
    threshold = _parse_plus_years_threshold(label)
    if threshold is not None:
        # Greenhouse comboboxes often omit options at scan time — still Yes/No, not "5-7".
        effective_floor = max(threshold - 1, 0) if threshold >= 5 else threshold
        yn = "Yes" if years >= effective_floor else "No"
        if not options or _is_yes_no_option_set(options):
            return yn
    if options and _is_yes_no_option_set(options):
        return "Yes" if years >= 1 else "No"
    if options:
        exact = str(years)
        for opt in options:
            if opt.strip() == exact:
                return opt
        for opt in options:
            m = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", opt.strip())
            if m and int(m.group(1)) <= years <= int(m.group(2)):
                return opt
        for opt in options:
            m = re.match(r"^(\d+)\+$", opt.strip())
            if m and years >= int(m.group(1)):
                return opt
        best: Optional[str] = None
        best_dist: Optional[int] = None
        for opt in options:
            m = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", opt.strip())
            if not m:
                continue
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo <= years <= hi:
                return opt
            dist = min(abs(years - lo), abs(years - hi))
            if best_dist is None or dist < best_dist:
                best = opt
                best_dist = dist
        if best:
            return best
    return _years_experience_bucket_fallback(years)


def _in_office_answer(field: AutofillFieldIn, prof: Dict[str, Any]) -> Optional[str]:
    label = _label_blob(field)
    asks_nyc_commute = _label_asks_nyc_area_commute(label)
    if not _IN_OFFICE_RE.search(label) and not asks_nyc_commute:
        return None
    commute_yn = _tri_state_commute_yes_no_answer(field, prof)
    if commute_yn is not None:
        return commute_yn

    options = _option_texts(field)
    willing = bool(prof.get("willing_to_relocate"))
    in_metro = _user_in_nyc_metro(prof)
    target_is_nyc = asks_nyc_commute
    central_office = "central office" in label.lower()

    if central_office:
        if options:
            has_office_codes = any(
                re.search(r"\bnyc\b|\bsf\b|san francisco", o, re.IGNORECASE) for o in options
            )
            if has_office_codes and in_metro:
                picked = _pick_option(
                    options,
                    lambda t: bool(re.search(r"\bnyc\b|new york", t, re.IGNORECASE)),
                )
                if picked:
                    return picked
            if not has_office_codes and (in_metro or willing):
                picked = _pick_option(
                    options,
                    lambda t: t.strip().lower().startswith("yes"),
                )
                if picked:
                    return picked
            if willing:
                picked = _pick_option(
                    options,
                    lambda t: t.strip().lower().startswith("yes"),
                )
                if picked:
                    return picked
        if in_metro and not options:
            return "NYC"
        if in_metro:
            picked_office = None
            if options:
                picked_office = _pick_option(
                    options,
                    lambda t: bool(re.search(r"\bnyc\b|new york", t, re.IGNORECASE)),
                )
            return picked_office or "NYC"
        if willing:
            return "Yes"
        return "No"

    if not options:
        if willing or in_metro:
            return "Yes"
        return "No"

    if target_is_nyc and in_metro:
        picked = _pick_option(
            options,
            lambda t: "currently live" in t or "currently in" in t or "currently local" in t or "metropolitan" in t,
        )
        if picked:
            return picked

    if willing:
        picked = _pick_option(
            options,
            lambda t: "relocation" in t or "relocate" in t or "open to" in t,
        )
        if picked:
            return picked

    picked = _pick_option(
        options,
        lambda t: "cannot" in t or "can not" in t or "not able" in t or "no," in t,
    )
    if picked:
        return picked

    if willing:
        return _pick_option(options, lambda t: t.startswith("yes"))
    return _pick_option(options, lambda t: t.startswith("no"))


def _startup_answer(prof: Dict[str, Any]) -> Optional[str]:
    sizes = prof.get("desired_company_sizes") or []
    if not isinstance(sizes, list):
        return None
    for size in sizes:
        if isinstance(size, str) and "startup" in size.lower():
            return "Yes"
    if sizes:
        only_large = all(
            isinstance(s, str)
            and any(k in s.lower() for k in ("enterprise", "large", "1000+", "500+"))
            for s in sizes
        )
        if only_large:
            return "No"
    return "Yes"


# =============================================================================
# PUBLIC API
# =============================================================================


def _form_has_middle_name_field(fields: Optional[Sequence[AutofillFieldIn]]) -> bool:
    if not fields:
        return False
    for f in fields:
        if _MIDDLE_NAME_RE.search(_label_blob(f)):
            return True
    return False


def deterministic_value_for_field(
    field: AutofillFieldIn,
    profile_bundle: Dict[str, Any],
    *,
    all_fields: Optional[Sequence[AutofillFieldIn]] = None,
) -> Optional[str]:
    """
    Return a profile-backed value for a single field, or None if no rule applies.

    Args:
        field: Serialized form control from the extension.
        profile_bundle: Snapshot from ``_load_profile_bundle`` (email, full_name, profile).

    Returns:
        Plain-text value to write into the field, or None.
    """
    label = _label_blob(field)
    if not label or _EEO_RE.search(label):
        return None

    prof = _profile_dict(profile_bundle)
    full_name = (profile_bundle.get("full_name") or "").strip()
    input_type = (field.input_type or "").lower()

    # --- Contact ---
    if _EMAIL_RE.search(label) and input_type in ("", "text", "email"):
        email = (profile_bundle.get("email") or "").strip()
        return email or None

    if _PHONE_RE.search(label) and input_type in ("", "text", "tel"):
        phone = (prof.get("phone") or "").strip()
        return phone or None

    if _FIRST_NAME_RE.search(label) and not _LAST_NAME_RE.search(label):
        first, _, _ = _split_full_name(full_name)
        return first or None

    if _LAST_NAME_RE.search(label) and not _FIRST_NAME_RE.search(label):
        if _form_has_middle_name_field(all_fields):
            _, _, last = _split_full_name(full_name)
            return last or None
        family = _family_name_from_full_name(full_name)
        return family or None

    if _MIDDLE_NAME_RE.search(label):
        _, middle, _ = _split_full_name(full_name)
        return middle or None

    if _NAME_LABEL_RE.search(label) and not _BAD_NAME_LABEL_RE.search(label):
        return full_name or None

    if _LINKEDIN_RE.search(label) and input_type in ("", "text", "url", "combobox"):
        linkedin = (prof.get("linkedin_url") or "").strip()
        return linkedin or None

    if _GITHUB_USERNAME_FIELD_RE.search(label) and input_type in ("", "text", "combobox"):
        return _github_username_from_profile(prof)

    if _GITHUB_RE.search(label) and not _GITHUB_USERNAME_FIELD_RE.search(label) and input_type in (
        "",
        "text",
        "url",
        "combobox",
    ):
        github = (prof.get("github_url") or "").strip()
        return github or None

    if _WEBSITE_RE.search(label) and not _LINKEDIN_RE.search(label) and input_type in (
        "",
        "text",
        "url",
        "combobox",
    ):
        return _website_url(prof)

    if (
        _COUNTRY_LABEL_RE.search(label)
        and not _PHONE_RE.search(label)
        and input_type in ("", "text", "select", "combobox")
    ):
        return _country_display_name(prof.get("country"))

    if _is_profile_city_location_field(label) and input_type in (
        "",
        "text",
        "search",
        "combobox",
    ):
        return _location_city_answer(prof)

    if _is_consent_ack_label(label):
        if input_type == "checkbox":
            return "checked"
        if input_type in ("", "text", "select", "combobox"):
            return _acknowledge_answer(field)

    if _SALARY_EXPECT_RE.search(label) and _salary_text_field(field):
        return _salary_expectations_answer(prof, field)

    if _START_TIMELINE_RE.search(label) and _free_text_field(field):
        return _DEFAULT_START_NOTICE_ANSWER

    if _YEARS_EXP_RE.search(label) and input_type in ("", "text", "select", "combobox"):
        return _years_experience_answer(field, prof)

    sponsorship = _sponsorship_answer(field, prof)
    if sponsorship is not None:
        return sponsorship

    # --- Yes / No / combobox screening (options optional for Greenhouse) ---
    is_screening_control = input_type in (
        "yes_no_buttons",
        "radio",
        "role_radio",
        "combobox",
        "select",
    )
    if is_screening_control or field.options:
        if _WORK_AUTH_RE.search(label) and not _SPONSORSHIP_RE.search(label):
            wa = prof.get("work_authorization")
            if wa in _US_WORK_AUTH or wa == "has_work_authorization":
                return "Yes"
            if wa == "no_work_authorization":
                return "No"

        if _US_BASED_RE.search(label) and not _SPONSORSHIP_RE.search(label):
            us_from_country = _country_is_us(prof.get("country"))
            if us_from_country is True or _work_auth_implies_us(prof.get("work_authorization")):
                return "Yes"
            if us_from_country is False and not _work_auth_implies_us(prof.get("work_authorization")):
                return "No"

        if _STARTUP_RE.search(label) or (
            _STARTUP_ASHBY_HELPER_RE.search(label) and input_type in ("yes_no_buttons", "radio", "role_radio")
        ):
            return _startup_answer(prof)

        commute_yn = _tri_state_commute_yes_no_answer(field, prof)
        if commute_yn is not None:
            return commute_yn

        central_reloc = _central_office_relocation_answer(field, prof)
        if central_reloc:
            return central_reloc

        in_office = _in_office_answer(field, prof)
        if in_office:
            return in_office

    return None


def build_deterministic_raw_assignments(
    fields: Sequence[AutofillFieldIn],
    profile_bundle: Dict[str, Any],
) -> List[Dict[str, str]]:
    """
    Build assignment dicts for every field with a deterministic mapping.

    Args:
        fields: All fields from the client request.
        profile_bundle: User + profile snapshot.

    Returns:
        List of ``{"field_uid": str, "value": str}`` dicts.
    """
    out: List[Dict[str, str]] = []
    prof = _profile_dict(profile_bundle)
    degree_idx = 0
    discipline_idx = 0
    school_idx = 0

    for field in fields:
        val = deterministic_value_for_field(field, profile_bundle, all_fields=fields)
        label = _label_blob(field)

        if val is None and _WEBSITE_RE.search(label) and not _LINKEDIN_RE.search(label):
            val = _website_url(prof)

        if val is None and _DEGREE_RE.search(label):
            idx = getattr(field, "duplicate_label_index", None)
            if idx is None:
                idx = degree_idx
            val = _education_field_value(field, prof, kind="degree", index=int(idx))
            if val:
                val = _align_degree_to_form_options(val, _option_texts(field))
            degree_idx += 1

        if val is None and _DISCIPLINE_RE.search(label):
            idx = getattr(field, "duplicate_label_index", None)
            if idx is None:
                idx = discipline_idx
            val = _education_field_value(field, prof, kind="discipline", index=int(idx))
            discipline_idx += 1

        if val is None and _SCHOOL_RE.search(label) and not _BAD_NAME_LABEL_RE.search(label):
            idx = getattr(field, "duplicate_label_index", None)
            if idx is None:
                idx = school_idx
            val = _education_field_value(field, prof, kind="school", index=int(idx))
            school_idx += 1

        if val is None:
            continue
        out.append(
            {
                "field_uid": field.field_uid,
                "value": val,
                "label_text": (field.label_text or "")[:240],
                "duplicate_label_index": int(getattr(field, "duplicate_label_index", 0) or 0),
            }
        )
    return out


def merge_assignment_dicts(
    base: List[Dict[str, Any]],
    overlay: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Merge assignment lists; ``overlay`` wins on duplicate ``field_uid``.

    Args:
        base: Lower-priority assignments (typically LLM output).
        overlay: Higher-priority assignments (deterministic rules).

    Returns:
        De-duplicated assignment dicts preserving overlay values.
    """
    by_uid: Dict[str, Dict[str, Any]] = {}
    for item in base:
        if isinstance(item, dict) and isinstance(item.get("field_uid"), str):
            by_uid[item["field_uid"]] = item
    for item in overlay:
        if isinstance(item, dict) and isinstance(item.get("field_uid"), str):
            uid = item["field_uid"]
            merged = dict(item)
            prior = by_uid.get(uid)
            if prior and not (merged.get("label_text") or "").strip():
                prior_label = (prior.get("label_text") or "").strip()
                if prior_label:
                    merged["label_text"] = prior_label
            by_uid[uid] = merged
    return list(by_uid.values())


def filter_skipped_for_assigned_uids(
    skipped: List[Dict[str, str]],
    assigned_uids: Sequence[str],
) -> List[Dict[str, str]]:
    """
    Drop skip entries for fields that received an assignment.

    Args:
        skipped: Skip list from cache or LLM.
        assigned_uids: field_uid values that were assigned.

    Returns:
        Filtered skip list.
    """
    assigned = set(assigned_uids)
    out: List[Dict[str, str]] = []
    for entry in skipped:
        if not isinstance(entry, dict):
            continue
        uid = entry.get("field_uid")
        if isinstance(uid, str) and uid in assigned:
            continue
        out.append(entry)
    return out
