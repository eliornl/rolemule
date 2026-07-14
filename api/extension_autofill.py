"""
Chrome extension: map visible job-application form fields to the user's profile via LLM.

MVP: same-document fields only; client previews suggestions before applying values in-tab.
"""

from __future__ import annotations

import html
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import get_settings
from api.extension_autofill_models import (
    AutofillAssignmentOut,
    AutofillFieldIn,
    AutofillMapRequest,
    AutofillMapResponse,
    AutofillSelectOption,
    _MAX_EXTRA_KEY_LEN,
    _MAX_EXTRA_VALUE_LEN,
    _MAX_EXTRAS_KEYS,
    _MAX_LABEL_CHARS,
    _MAX_OPTION_TEXT,
    _MAX_OPTIONS_PER_SELECT,
    _MAX_PAGE_URL_LEN,
)
from api.extension_autofill_rules import (
    build_deterministic_raw_assignments,
    filter_skipped_for_assigned_uids,
    merge_assignment_dicts,
)
from models.database import User, UserProfile as UserProfileModel, UserResumeAsset
from utils.auth import get_current_user_with_complete_profile
from utils.cache import (
    cache_tool_result,
    check_rate_limit_with_headers,
    generate_hash,
    get_cached_tool_result,
)
from utils.database import get_database
from utils.encryption import decrypt_api_key
from utils.error_responses import (
    ErrorCode,
    external_service_error,
    internal_error,
    no_api_key_error,
    not_found_error,
    rate_limit_error,
)
from utils.llm_client import GeminiError, get_llm_client, get_gemini_client, user_facing_message_from_llm_exception
from utils.llm_parsing import parse_json_from_llm_response
from utils.security import sanitize_text
from utils.logging_config import sanitize_log_value

# Re-exported for tests and extension_autofill_rules consumers
__all__ = ["AutofillSelectOption"]

logger = logging.getLogger(__name__)
router = APIRouter()

# =============================================================================
# CONSTANTS
# =============================================================================

_MAX_ASSIGNMENT_VALUE: int = 8000

_RATE_LIMIT: int = 15
_RATE_LIMIT_DEBUG: int = 200
_RATE_WINDOW_S: int = 3600


def _autofill_rate_limit() -> int:
    """Production cap is 15/hour; local DEBUG allows more iteration while testing."""
    if get_settings().debug:
        return _RATE_LIMIT_DEBUG
    return _RATE_LIMIT

_SYSTEM_PROMPT: str = """You map job application form fields to a user's profile data.

Rules:
- Output ONLY a JSON object with keys "assignments" and "skipped". No markdown fences.
- "assignments" is an array of {"field_uid": string, "value": string}. Use ONLY field_uid values from the input list.
- "skipped" is an array of {"field_uid": string, "reason": string} for fields you refuse to fill or cannot map.
- Use ONLY facts present in the provided profile JSON and extras JSON. Do not invent employers, degrees, or credentials.
- Fields marked required:true are priority — fill them when profile data supports an answer; do not skip merely to be cautious.
- Name fields (full/legal/applicant name): copy PROFILE_JSON full_name EXACTLY as stored — include all given names and surnames; never shorten to first+last only.
- First name / last name split fields: derive from full_name (first token = first name; last name = all remaining tokens joined, e.g. Elior Nataf Lackritz → first Elior, last Nataf Lackritz; middle-only field = tokens between first and last when asked).
- Email fields: use PROFILE_JSON email exactly.
- Phone fields: use profile.phone when present.
- When fields ask for school, university, degree, major, field of study, or graduation dates, map from profile.education when present (each entry may include institution, degree, field_of_study, start_date, end_date, is_current).
- When multiple Degree/Discipline fields appear (duplicate_label_index 0, 1, …), map profile.education[0] to index 0, profile.education[1] to index 1, etc. Fill every row when profile data exists.
- Degree dropdown mapping: copy the profile degree text; the server normalizes common aliases to dropdown labels. Examples — Associate: AA/AS/AAS → Associate's Degree; Bachelor: BA/BS/BSc/BBA/BEng/BFA/LLB/Bachelor of Laws → Bachelor's Degree (or specific Bachelor of … when listed); Master: MA/MS/MSc/MBA/MEng → Master of Arts/Science/Business/etc. or Master's Degree; explicit JD/Juris Doctor in profile → Juris Doctor (J.D.); Doctorate: PhD/MD/EdD → matching Doctor of … option. Never invent a degree not in profile.education.
- Years of industry experience: when options are numeric ranges (e.g. 5-7, 8-10, 11+), pick the bucket closest to profile.years_experience — if the exact count is below a range's lower bound, use the nearest range above (e.g. 4 years → 5-7 when that is the closest bucket).
- Profile may include city, state, country, willing_to_relocate, work_arrangements, desired_company_sizes, phone, linkedin_url, github_url, portfolio_url, work_authorization (no_work_authorization | has_work_authorization | us_lawful_permanent_resident | us_citizen; omit if null), requires_visa_sponsorship (boolean), and resume_file.has_file — use only when present in PROFILE_JSON.
- Country dropdown/combobox fields: map profile.country to the full country name (e.g. US → United States).
- Location (City) / current city / where you are located: use profile.city and profile.state when present (e.g. Hoboken, NJ) — not country dropdowns or relocation screening questions.
- Website/portfolio fields: use portfolio_url when present; if empty, use github_url even when the form also has a separate GitHub Username field.
- GitHub Username fields (not Website): use the username from github_url (e.g. eliornl from https://github.com/eliornl).
- Legal acknowledgement attestations (acknowledge/confirm/agree to statements): select Yes or the affirmative agreement option — do not skip as EEO.
- Application consent checkboxes ("By checking this box, I agree to allow … store/process/retain my data", privacy consent): assign value "checked" — default to checked; skip optional marketing/newsletter opt-ins and EEO/diversity boxes.
- "Based in the United States" / US location questions: Yes when country is US/United States OR work_authorization is us_citizen or us_lawful_permanent_resident; No when country is clearly outside the US and no US work authorization.
- Visa / employment sponsorship questions ("require visa sponsorship", H-1B, etc.): answer "Yes" ONLY if profile.requires_visa_sponsorship is true. Answer "No" when false or when work_authorization is us_citizen, us_lawful_permanent_resident, or has_work_authorization — having authorization means you do NOT need sponsorship; never answer Yes because the user is authorized.
- In-person / on-site / NYC / tri-state commute questions (e.g. commute to NYC office 2x/week): use profile.city and profile.state to judge whether the candidate can reasonably commute (e.g. Hoboken NJ and Jersey City → Yes; Austin TX → No unless willing_to_relocate). Plain Yes/No → Yes when commute is reasonable. Long option lists → pick currently local/metropolitan when close, relocation when willing_to_relocate, else cannot work in-office. Match full option text when listed.
- "Not local to central offices" / willing to relocate (Greenhouse long dropdowns): same geographic reasoning from city/state; pick currently local/metropolitan when close, relocation when willing_to_relocate, else not-willing.
- Startup readiness questions: Yes when desired_company_sizes includes startup; otherwise Yes unless the user only selected enterprise/large company sizes.
- Open-ended questions (why this company/role, why join, motivation, cover-letter-style prompts): ONE or TWO short sentences only (about 25–50 words total). Lead with role fit; one concrete point from profile.summary or work_experience — no lists, no fluff, no repetition. You may name the employer from the page URL when obvious. Do not invent facts.
- input_type "file" for resume/CV: skip (the client attaches the stored resume separately). Do not assign file fields.
- If a field asks for legally sensitive attestations, diversity/EEO self-ID, or anything you should not infer, skip it.
- For salary expectation questions (in $, yearly): use profile.desired_salary_range min/max when present (e.g. 150000-200000); if absent, skip — do not invent a number.
- Start date / notice period / "how quickly are you looking to start" questions: answer with exactly "I can start a new role in 2 weeks." — not 2-4 weeks or a longer paragraph.
- Keep values concise. Match the expected format when obvious (e.g. email for email fields).
- Skip only when profile truly lacks the needed fact or the field is EEO/diversity; do not skip required screening questions when profile has the answer.
"""

# =============================================================================
# HELPERS
# =============================================================================


def _get_user_uuid(current_user: Dict[str, Any]) -> uuid.UUID:
    uid = current_user.get("id") or current_user.get("_id")
    if isinstance(uid, str):
        return uuid.UUID(uid)
    return uid


async def _get_user_api_key(db: AsyncSession, user_id: uuid.UUID) -> Optional[str]:
    try:
        from utils.llm_context import require_user_llm_context

        _u, ctx, _p = await require_user_llm_context(db, user_id)
        return ctx.user_api_key
    except Exception as e:
        from utils.error_responses import APIError

        if isinstance(e, APIError) and getattr(e, "error_code", None) and getattr(e.error_code, "value", e.error_code) == "CFG_6001":
            return None
        logger.warning(
            'Failed to resolve user API key for autofill: %s',
            sanitize_log_value(e),
            exc_info=True,
        )
    return None


async def _llm_ready(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Return True when the user can run LLM-backed autofill."""
    try:
        from utils.llm_context import require_user_llm_context

        await require_user_llm_context(db, user_id)
        return True
    except Exception:
        return False


def _server_has_llm() -> bool:
    """Vertex-only admin escape hatch (legacy name kept for call sites)."""
    from utils.llm.availability import server_has_llm_credentials

    return server_has_llm_credentials(get_settings())


async def _load_profile_bundle(
    db: AsyncSession, user_id: uuid.UUID, user_row: User
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Build a JSON-serializable snapshot for the LLM (user + profile).

    Returns:
        Tuple of (snapshot dict, profile updated_at iso or None for cache keying)
    """
    result = await db.execute(select(UserProfileModel).where(UserProfileModel.user_id == user_id))
    prof = result.scalar_one_or_none()
    snap: Dict[str, Any] = {
        "email": user_row.email,
        "full_name": user_row.full_name,
    }
    prof_sig = ""
    if prof:
        d = prof.to_dict()
        summary = d.get("summary") or ""
        if isinstance(summary, str) and len(summary) > 2500:
            summary = summary[:2500] + "…"
        d["summary"] = summary
        we = d.get("work_experience") or []
        if isinstance(we, list) and len(we) > 12:
            d["work_experience"] = we[:12]
        snap["profile"] = d
        if prof.updated_at:
            prof_sig = prof.updated_at.isoformat()
    else:
        snap["profile"] = {}

    ra_res = await db.execute(select(UserResumeAsset).where(UserResumeAsset.user_id == user_id))
    ra = ra_res.scalar_one_or_none()
    if ra:
        snap["resume_file"] = {
            "has_file": True,
            "original_filename": ra.original_filename,
            "mime_type": ra.mime_type,
            "byte_size": ra.byte_size,
        }
    else:
        snap["resume_file"] = {"has_file": False}

    return snap, prof_sig


def _sanitize_field_dict(f: AutofillFieldIn) -> Dict[str, Any]:
    opts = None
    if f.options:
        opts = [
            {"value": sanitize_text(o.value)[:500], "text": sanitize_text(o.text)[:_MAX_OPTION_TEXT]}
            for o in f.options[:_MAX_OPTIONS_PER_SELECT]
        ]
    return {
        "field_uid": sanitize_text(f.field_uid)[:64],
        "tag": sanitize_text(f.tag)[:24],
        "input_type": sanitize_text(f.input_type)[:32] if f.input_type else None,
        "name_attr": sanitize_text(f.name_attr)[:240] if f.name_attr else None,
        "id_attr": sanitize_text(f.id_attr)[:240] if f.id_attr else None,
        "label_text": sanitize_text(f.label_text)[:_MAX_LABEL_CHARS],
        "placeholder": sanitize_text(f.placeholder)[:500] if f.placeholder else None,
        "aria_label": sanitize_text(f.aria_label)[:500] if f.aria_label else None,
        "required": f.required,
        "max_length": f.max_length,
        "options": opts,
        "duplicate_label_index": f.duplicate_label_index,
    }


def _sanitize_form_autofill_value(val: str) -> str:
    """Plain text for DOM input/textarea values — decode entities, strip controls, keep newlines."""
    if not val:
        return ""
    text = html.unescape(str(val))
    # Resolve double-encoded entities (e.g. &amp;#x27; from display sanitizers).
    text = html.unescape(text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    if len(text) > _MAX_ASSIGNMENT_VALUE:
        text = text[:_MAX_ASSIGNMENT_VALUE]
    return text


def _sanitize_extras(extras: Optional[Dict[str, str]]) -> Dict[str, str]:
    if not extras:
        return {}
    out: Dict[str, str] = {}
    for k, v in list(extras.items())[:_MAX_EXTRAS_KEYS]:
        kk = sanitize_text(str(k))[:_MAX_EXTRA_KEY_LEN]
        if not kk:
            continue
        out[kk] = sanitize_text(str(v))[:_MAX_EXTRA_VALUE_LEN] if v is not None else ""
    return out


def _build_user_prompt(
    fields_compact: List[Dict[str, Any]], profile: Dict[str, Any], extras: Dict[str, str], page_url: str
) -> str:
    return (
        "Page URL (context only): "
        + sanitize_text(page_url)[:_MAX_PAGE_URL_LEN]
        + "\n\nFIELDS_JSON:\n"
        + json.dumps(fields_compact, ensure_ascii=False)
        + "\n\nPROFILE_JSON:\n"
        + json.dumps(profile, ensure_ascii=False, default=str)
        + "\n\nEXTRAS_JSON:\n"
        + json.dumps(extras, ensure_ascii=False)
        + '\n\nRespond with JSON: {"assignments":[{"field_uid":"…","value":"…"}],'
        + '"skipped":[{"field_uid":"…","reason":"…"}]}'
    )


def _validate_assignments(
    raw_assignments: List[Dict[str, Any]],
    fields_by_uid: Dict[str, AutofillFieldIn],
) -> List[AutofillAssignmentOut]:
    out: List[AutofillAssignmentOut] = []
    for item in raw_assignments:
        if not isinstance(item, dict):
            continue
        uid = item.get("field_uid")
        val = item.get("value")
        if not isinstance(uid, str) or uid not in fields_by_uid:
            continue
        if not isinstance(val, str):
            val = str(val) if val is not None else ""
        val = _sanitize_form_autofill_value(val)
        meta = fields_by_uid[uid]
        if meta.max_length is not None and meta.max_length > 0 and len(val) > meta.max_length:
            val = val[: int(meta.max_length)]
        out.append(
            AutofillAssignmentOut(
                field_uid=uid,
                value=val,
                label_text=meta.label_text[:_MAX_LABEL_CHARS],
                duplicate_label_index=meta.duplicate_label_index,
            )
        )
    return out


def _missing_required_warnings(
    request_fields: Sequence["AutofillFieldIn"],
    assignments: Sequence[AutofillAssignmentOut],
) -> List[str]:
    """Warn when required fields (except resume file) received no assignment."""
    assigned = {a.field_uid for a in assignments}
    missing_labels: List[str] = []
    for field in request_fields:
        if not field.required or field.field_uid in assigned:
            continue
        if (field.input_type or "").lower() == "file":
            continue
        label = re.sub(r"\s+", " ", (field.label_text or "").strip())[:100]
        if label:
            missing_labels.append(label)
    if not missing_labels:
        return []
    preview = "; ".join(missing_labels[:3])
    if len(missing_labels) > 3:
        preview += f" (+{len(missing_labels) - 3} more)"
    return [
        f"{len(missing_labels)} required field(s) could not be auto-filled — please review: {preview}"
    ]


def _finalize_autofill_response(
    llm_raw_assignments: List[Dict[str, Any]],
    skipped: List[Dict[str, str]],
    fields_by_uid: Dict[str, AutofillFieldIn],
    profile_bundle: Dict[str, Any],
    request_fields: List[AutofillFieldIn],
) -> Tuple[List[AutofillAssignmentOut], List[Dict[str, str]]]:
    """
    Merge deterministic profile rules over LLM assignments and drop stale skips.

    Args:
        llm_raw_assignments: Raw assignment dicts from cache or LLM.
        skipped: Skipped field entries from cache or LLM.
        fields_by_uid: field_uid → field metadata.
        profile_bundle: User + profile snapshot.
        request_fields: All fields from the client request.

    Returns:
        Tuple of (validated assignments, filtered skipped list).
    """
    det_raw = build_deterministic_raw_assignments(request_fields, profile_bundle)
    merged_raw = merge_assignment_dicts(llm_raw_assignments, det_raw)
    assignments = _validate_assignments(
        [x for x in merged_raw if isinstance(x, dict)],
        fields_by_uid,
    )
    skipped_safe = filter_skipped_for_assigned_uids(
        skipped,
        [a.field_uid for a in assignments],
    )
    return assignments, skipped_safe


# =============================================================================
# ENDPOINT
# =============================================================================


@router.post("/autofill/map", response_model=AutofillMapResponse)
async def map_form_fields_to_profile(
    request: AutofillMapRequest,
    response: Response,
    current_user: Dict[str, Any] = Depends(get_current_user_with_complete_profile),
    db: AsyncSession = Depends(get_database),
) -> AutofillMapResponse:
    """
    Map serialized form field descriptors to profile-backed values using Gemini.

    The extension must show a preview and obtain user confirmation before writing DOM values.
    """
    user_id = _get_user_uuid(current_user)

    rate_cap = _autofill_rate_limit()
    rate = await check_rate_limit_with_headers(
        identifier=f"{user_id}:extension_autofill_map",
        limit=rate_cap,
        window_seconds=_RATE_WINDOW_S,
    )
    if not rate.allowed:
        raise rate_limit_error(
            f"Rate limit exceeded. Maximum {rate_cap} autofill requests per hour. "
            f"Resets in {rate.reset_seconds} seconds.",
            retry_after=rate.reset_seconds,
        )
    for hk, hv in rate.get_headers().items():
        response.headers[hk] = hv

    from utils.llm_context import require_user_llm_context
    from utils.llm_preferences import load_preferred_model

    _u, llm_ctx, _p = await require_user_llm_context(db, user_id)
    user_api_key = llm_ctx.user_api_key
    llm_provider = llm_ctx.provider
    preferred_model = await load_preferred_model(
        db, user_id, user_api_key, has_credentials=True
    )

    user_result = await db.execute(select(User).where(User.id == user_id))
    user_row = user_result.scalar_one_or_none()
    if not user_row:
        raise not_found_error(resource_type="User")

    profile_bundle, prof_sig = await _load_profile_bundle(db, user_id, user_row)
    extras_clean = _sanitize_extras(request.extras)

    fields_by_uid = {f.field_uid: f for f in request.fields}
    fields_compact = [_sanitize_field_dict(f) for f in request.fields]
    page_url_clean = sanitize_text(request.page_url.strip())[:_MAX_PAGE_URL_LEN]

    cache_payload: Dict[str, Any] = {
        "tool": "extension_autofill",
        "user_id": str(user_id),
        "page_url": page_url_clean,
        "fields": fields_compact,
        "profile_sig": prof_sig or "",
        "extras_sig": generate_hash(json.dumps(extras_clean, sort_keys=True)),
    }

    cached = await get_cached_tool_result("extension_autofill", cache_payload)
    warnings = [
        "Main page only: fields inside iframes or shadow roots are not included.",
        "Review every value before applying; the model can mis-map similar labels.",
    ]

    if cached and isinstance(cached, dict) and "assignments" in cached:
        raw_assign = [x for x in (cached.get("assignments") or []) if isinstance(x, dict)]
        raw_skip = cached.get("skipped") or []
        skipped_safe: List[Dict[str, str]] = []
        for s in raw_skip:
            if isinstance(s, dict) and isinstance(s.get("field_uid"), str):
                uid = s["field_uid"]
                if uid not in fields_by_uid:
                    continue
                skipped_safe.append(
                    {
                        "field_uid": sanitize_text(uid)[:64],
                        "reason": sanitize_text(str(s.get("reason", "")))[:500],
                    }
                )
        assignments, skipped_safe = _finalize_autofill_response(
            raw_assign,
            skipped_safe,
            fields_by_uid,
            profile_bundle,
            request.fields,
        )
        warnings.extend(_missing_required_warnings(request.fields, assignments))
        return AutofillMapResponse(assignments=assignments, skipped=skipped_safe, warnings=warnings)

    user_prompt = _build_user_prompt(fields_compact, profile_bundle, extras_clean, page_url_clean)

    try:
        client = await get_llm_client()
        # Tool-level Redis cache (get_cached_tool_result) is sufficient; avoid a second
        # LLM-response cache layer that can drift from this endpoint's validation rules.
        gen = await client.generate(
            prompt=user_prompt,
            system=_SYSTEM_PROMPT,
            temperature=0.15,
            max_tokens=8192,
            use_cache=False,
            user_api_key=user_api_key,
            user_id=str(user_id),
            model=preferred_model,
            provider=llm_provider,
        )
    except GeminiError as e:
        logger.error('Autofill LLM error: %s', sanitize_log_value(e), exc_info=True)
        raise external_service_error(
            user_facing_message_from_llm_exception(e),
            error_code=ErrorCode.LLM_SERVICE_ERROR,
        )
    except Exception as e:
        logger.error('Autofill unexpected error: %s', sanitize_log_value(e), exc_info=True)
        raise internal_error("Failed to generate autofill suggestions")

    raw_text = gen.get("response") or ""
    parsed = parse_json_from_llm_response(raw_text)
    if not isinstance(parsed, dict) or "assignments" not in parsed:
        logger.warning('Autofill parse failed; raw snippet: %s', sanitize_log_value(raw_text[:400]))
        raise external_service_error(
            "Could not parse AI response. Try again with fewer fields visible.",
            error_code=ErrorCode.LLM_SERVICE_ERROR,
        )

    # Do not use sanitize_llm_output here — it HTML-escapes strings (e.g. ' → &#x27;), which
    # must remain plain text for form input/textarea values written by the extension.
    raw_assignments = parsed.get("assignments") if isinstance(parsed.get("assignments"), list) else []
    skipped = parsed.get("skipped") if isinstance(parsed.get("skipped"), list) else []

    skipped_safe: List[Dict[str, str]] = []
    for s in skipped:
        if isinstance(s, dict) and isinstance(s.get("field_uid"), str):
            sk_uid = s["field_uid"]
            if sk_uid not in fields_by_uid:
                continue
            skipped_safe.append(
                {
                    "field_uid": sanitize_text(sk_uid)[:64],
                    "reason": sanitize_text(str(s.get("reason", "")))[:500],
                }
            )

    llm_raw = [x for x in raw_assignments if isinstance(x, dict)]
    assignments, skipped_safe = _finalize_autofill_response(
        llm_raw,
        skipped_safe,
        fields_by_uid,
        profile_bundle,
        request.fields,
    )

    warnings.extend(_missing_required_warnings(request.fields, assignments))

    cache_body = {
        "assignments": [a.model_dump() for a in assignments],
        "skipped": skipped_safe,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    await cache_tool_result("extension_autofill", cache_payload, cache_body)

    return AutofillMapResponse(assignments=assignments, skipped=skipped_safe, warnings=warnings)
