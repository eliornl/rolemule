"""
Profile API endpoints for comprehensive user profile management.
Provides 4-step profile setup with validation, completion tracking, and comprehensive data management.
"""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Union
from enum import Enum

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator, ValidationInfo, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete as sa_delete, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from utils.auth import get_current_user, invalidate_all_user_tokens
from utils.database import get_database
from config.settings import get_settings
from utils.json_utils import serialize_object_for_json
from utils.resume_parser import parse_resume_from_file, SUPPORTED_EXTENSIONS
from utils.user_resume_storage import delete_resume_file, resume_absolute_path, save_resume_bytes
from utils.cache import (
    get_cached_user_profile,
    cache_user_profile,
    invalidate_user_profile,
    invalidate_user_llm_cache,
    check_rate_limit,
)
from utils.encryption import (
    encrypt_api_key,
    decrypt_api_key,
)
from utils.gemini_api_key_format import validate_gemini_api_key
from utils.logging_config import get_structured_logger, mask_email, sanitize_log_value
from utils.error_responses import APIError, ErrorCode, internal_error, no_api_key_error, not_found_error, not_implemented_error, rate_limit_error, validation_error
from models.database import User, UserProfile as UserProfileModel, JobApplication, WorkflowSession, UserWorkflowPreferences, UserResumeAsset

logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)
settings = get_settings()

router = APIRouter()

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _log_user_email(current_user: Dict[str, Any]) -> str:
    """Masked email safe for log lines (never pass current_user dict to logging)."""
    return mask_email(str(current_user.get("email", "")))


def get_user_id_from_token(current_user: Dict[str, Any]) -> uuid.UUID:
    """
    Safely extract user ID from current_user object, checking both 'id' and '_id' keys.
    Converts to UUID for consistency in PostgreSQL operations.

    Args:
        current_user: User information from token validation

    Returns:
        User ID as UUID

    Raises:
        HTTPException: If no valid user ID is found in the token
    """
    user_id = current_user.get("id") or current_user.get("_id")
    if not user_id:
        logger.warning("Invalid user session: no user_id found in token")
        raise validation_error("Invalid user session. Please login again.")

    # Ensure user_id is converted to UUID if it's a string
    if isinstance(user_id, str):
        try:
            return uuid.UUID(user_id)
        except Exception as e:
            logger.warning(
                "Failed to convert user_id to UUID: %s",
                sanitize_log_value(e),
            )
            raise validation_error("Invalid user ID format.")

    return user_id


# =============================================================================
# CONSTANTS AND VALIDATION PATTERNS
# =============================================================================

# Maximum lengths
MAX_SUMMARY_LENGTH: int = 1000
MAX_LOCATION_LENGTH: int = 100
MAX_TITLE_LENGTH: int = 100
MAX_YEARS_EXPERIENCE: int = 70
MAX_DESCRIPTION_LENGTH: int = 4000
MAX_WORK_EXPERIENCE_ITEMS: int = 10
MAX_EDUCATION_ITEMS: int = 10
MAX_FIELD_OF_STUDY_LENGTH: int = 200
MAX_SKILLS_ITEMS: int = 50
MAX_COMPANY_SIZE_ITEMS: int = 5
MAX_JOB_TYPE_ITEMS: int = 5
MAX_WORK_ARRANGEMENT_ITEMS: int = 3
MAX_COMPANY_LENGTH: int = 100
MAX_PHONE_LENGTH: int = 40
MAX_PROFILE_URL_LENGTH: int = 500
_VALID_WORK_AUTHORIZATION = frozenset(
    {
        "no_work_authorization",
        "has_work_authorization",
        "us_lawful_permanent_resident",
        "us_citizen",
    }
)
# Minimum lengths
MIN_LENGTH: int = 1
MIN_SKILLS_ITEMS: int = 1
MIN_COMPANY_SIZE_ITEMS: int = 1
MIN_JOB_TYPE_ITEMS: int = 1
MIN_WORK_ARRANGEMENT_ITEMS: int = 1
# Resume upload limits and magic-bytes validation
MAX_RESUME_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB
# Maps allowed extension → required leading magic bytes (None = no fixed signature)
_RESUME_MAGIC: Dict[str, Optional[bytes]] = {
    "pdf":  b"%PDF",
    "docx": b"PK\x03\x04",  # DOCX/XLSX/PPTX are ZIP-based
    "txt":  None,            # UTF-8 text has no fixed signature
}
# Legacy Word 97–2003 binary (.doc) — OLE compound document; not supported (use .docx or PDF).
_MS_WORD_DOC_MAGIC_PREFIX: bytes = b"\xd0\xcf\x11\xe0"

_LEGACY_DOC_USER_MSG: str = (
    "Legacy Word (.doc) is not supported. In Word or Google Docs, use Save As → "
    "Word (.docx) or PDF, then upload that file."
)

# Location validation
LOCATION_PATTERN = r"^[a-zA-Z0-9\s\-\.\,\']+$"

# Character validation patterns
PROFESSIONAL_NAME_PATTERN: str = r"^[^\x00-\x08\x0B\x0C\x0E-\x1F\x7F]+$"
SKILL_PATTERN: str = r"^[a-zA-Z0-9\s\-\.\+\#\&\(\)\/]+$"
DESCRIPTION_PATTERN: str = r"^[^\x00-\x08\x0B\x0C\x0E-\x1F\x7F]+$"

# =============================================================================
# SHARED VALIDATION METHODS
# =============================================================================


def _validate_professional_name(value: str, field_name: str) -> str:
    """Validate professional names (company, job title, institution, degree, etc.)."""
    name: str = value.strip()

    if not name:
        raise ValueError(f"{field_name} cannot be empty")

    if not re.match(PROFESSIONAL_NAME_PATTERN, name):
        raise ValueError(
            f"{field_name} contains invalid characters. Only letters, numbers, spaces, and common punctuation are allowed."
        )

    name = re.sub(r"\s+", " ", name)
    return name.strip()


def _validate_text_field(
    value: Optional[str], field_name: str, max_length: int
) -> Optional[str]:
    """Validate text fields like descriptions and summaries."""
    if not value:
        return None

    text: str = value.strip()

    if len(text) > max_length:
        raise ValueError(f"{field_name} cannot exceed {max_length} characters")

    if not re.match(DESCRIPTION_PATTERN, text):
        raise ValueError(
            f"{field_name} contains invalid characters. Only letters, numbers, spaces, and common punctuation are allowed."
        )

    text = re.sub(r"\r\n|\r|\n", "\n", text)
    text = re.sub(r"\t", " ", text)
    text = re.sub(r" +", " ", text)

    return text.strip()


def _validate_location(v: Optional[str], field_name: str) -> Optional[str]:
    """Validate and normalize location format."""
    if v is None:
        return None

    if not v.strip():
        return None

    if not re.match(LOCATION_PATTERN, v):
        raise ValueError(f"{field_name} contains invalid characters")

    cleaned = " ".join(v.split())

    return cleaned


def _validate_profile_url_field(value: str, field_label: str) -> None:
    """Require http(s) scheme for stored profile URLs."""
    t = value.strip()
    if not t:
        return
    if not t.startswith(("http://", "https://")):
        raise ValueError(f"{field_label} must start with http:// or https://")
    if len(t) > MAX_PROFILE_URL_LENGTH:
        raise ValueError(f"{field_label} cannot exceed {MAX_PROFILE_URL_LENGTH} characters")


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    t = str(value).strip()
    return t or None


def _validator_field_values(info_or_values: Union[ValidationInfo, Dict[str, Any], None]) -> Dict[str, Any]:
    """Partial field data from Pydantic ValidationInfo or a raw dict (unit tests)."""
    if info_or_values is None:
        return {}
    if isinstance(info_or_values, dict):
        return info_or_values
    data = getattr(info_or_values, "data", None)
    return data if isinstance(data, dict) else {}


def _validate_required_location_field(v: str, field_name: str) -> str:
    result = _validate_location(v, field_name)
    if result is None:
        raise ValueError(f"{field_name} cannot be empty")
    return result


def _validate_basic_info_years_experience(v: int) -> int:
    if v < 0:
        raise ValueError("Years of experience cannot be negative")
    if v > MAX_YEARS_EXPERIENCE:
        raise ValueError(
            f"Years of experience cannot exceed {MAX_YEARS_EXPERIENCE} years"
        )
    return v


def _validate_basic_info_phone(v: str) -> str:
    if not v:
        return ""
    t = v.strip()
    if len(t) > MAX_PHONE_LENGTH:
        raise ValueError(f"Phone cannot exceed {MAX_PHONE_LENGTH} characters")
    return t


def _validate_optional_profile_url(v: str, field_label: str) -> str:
    if not v or not str(v).strip():
        return ""
    _validate_profile_url_field(str(v), field_label)
    return str(v).strip()[:MAX_PROFILE_URL_LENGTH]


def _validate_employment_start_date(v: str) -> str:
    if not v:
        raise ValueError("Start date is required")

    start_date: str = v.strip()

    if not re.match(r"^\d{4}-\d{2}$", start_date):
        raise ValueError("Start date must be in YYYY-MM format (e.g., 2023-01)")

    try:
        year, month = map(int, start_date.split("-"))
    except ValueError:
        raise ValueError("Start date must be in YYYY-MM format (e.g., 2023-01)")

    if not (1900 <= year <= 2100):
        raise ValueError("Start date year must be between 1900 and 2100")

    if not (1 <= month <= 12):
        raise ValueError("Start date month must be between 01 and 12")

    parsed_date: datetime = datetime.strptime(start_date, "%Y-%m").replace(tzinfo=timezone.utc)
    current_date: datetime = datetime.now(timezone.utc)

    if parsed_date > current_date:
        raise ValueError("Start date cannot be in the future")

    return start_date


def _validate_employment_end_date(v: Optional[str], *_: Any) -> Optional[str]:
    if not v:
        return None

    end_date = v.strip()

    if end_date.lower() == "present":
        return "Present"

    try:
        parsed_end_date = datetime.strptime(end_date, "%Y-%m")
    except ValueError:
        raise ValueError('End date must be in YYYY-MM format or "Present"')

    current_date = datetime.now(timezone.utc)
    max_future_date = datetime(current_date.year + 1, 12, 31, tzinfo=timezone.utc)
    parsed_end_date = parsed_end_date.replace(tzinfo=timezone.utc)
    if parsed_end_date > max_future_date:
        raise ValueError("End date cannot be more than 1 year in the future")

    return end_date


def _validate_employment_is_current(
    v: bool,
    info_or_values: Union[ValidationInfo, Dict[str, Any]],
) -> bool:
    if v:
        values = _validator_field_values(info_or_values)
        end_date = values.get("end_date")
        if end_date and end_date.strip().lower() not in ["present", ""]:
            raise ValueError(
                'If this is your current position, end date should be empty or "Present"'
            )
    return v


def _validate_work_experience_list(
    v: List["WorkExperienceItem"],
) -> List["WorkExperienceItem"]:
    if not v:
        return v

    current_positions = [exp for exp in v if exp.is_current]
    if len(current_positions) > 1:
        raise ValueError(
            "You can only have one current position. Please set is_current=True for only one position."
        )

    return v


def _validate_education_field_of_study(v: str) -> str:
    ft = _validate_professional_name(v, "Field of study")
    if len(ft) > MAX_FIELD_OF_STUDY_LENGTH:
        raise ValueError(f"Field of study cannot exceed {MAX_FIELD_OF_STUDY_LENGTH} characters")
    return ft


def _validate_education_start_date(v: str) -> str:
    if not v or not str(v).strip():
        raise ValueError("Start date is required")
    start_date = str(v).strip()
    if not re.match(r"^\d{4}-\d{2}$", start_date):
        raise ValueError("Start date must be in YYYY-MM format (e.g., 2023-01)")
    try:
        year, month = map(int, start_date.split("-"))
    except ValueError:
        raise ValueError("Start date must be in YYYY-MM format (e.g., 2023-01)")
    if not (1900 <= year <= 2100):
        raise ValueError("Start date year must be between 1900 and 2100")
    if not (1 <= month <= 12):
        raise ValueError("Start date month must be between 01 and 12")
    parsed_date: datetime = datetime.strptime(start_date, "%Y-%m").replace(tzinfo=timezone.utc)
    current_date: datetime = datetime.now(timezone.utc)
    if parsed_date > current_date:
        raise ValueError("Start date cannot be in the future")
    return start_date


def _validate_education_end_date(
    v: Optional[str],
    info_or_values: Union[ValidationInfo, Dict[str, Any]],
) -> Optional[str]:
    if not v:
        return None
    end_date = v.strip()
    try:
        parsed_end_date = datetime.strptime(end_date, "%Y-%m")
    except ValueError:
        raise ValueError("End date must be in YYYY-MM format")
    current_date = datetime.now(timezone.utc)
    max_future_date = datetime(current_date.year + 1, 12, 31, tzinfo=timezone.utc)
    parsed_end_date = parsed_end_date.replace(tzinfo=timezone.utc)
    if parsed_end_date > max_future_date:
        raise ValueError("End date cannot be more than 1 year in the future")
    start_raw = _validator_field_values(info_or_values).get("start_date")
    if start_raw and isinstance(start_raw, str):
        try:
            parsed_start = datetime.strptime(start_raw.strip(), "%Y-%m").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            pass  # unparseable start_date; skip cross-field check
        else:
            if parsed_end_date <= parsed_start:
                raise ValueError("End date must be after start date")
    return end_date


def _validate_education_is_current(
    v: bool,
    info_or_values: Union[ValidationInfo, Dict[str, Any]],
) -> bool:
    if v:
        end_date = _validator_field_values(info_or_values).get("end_date")
        if end_date and str(end_date).strip():
            raise ValueError("If currently enrolled, leave end date empty")
    return v


def _validate_skills_list(v: List[str]) -> List[str]:
    if not v:
        return v

    validated_skills: List[str] = []
    seen_skills: set = set()

    for skill in v:
        if not skill or not skill.strip():
            continue

        skill = skill.strip()

        if not re.match(SKILL_PATTERN, skill):
            raise ValueError(
                f'Skill "{skill}" contains invalid characters. Only letters, numbers, spaces, and common technical characters are allowed.'
            )

        if len(skill.replace(" ", "")) < 2:
            continue

        skill_lower: str = skill.lower()
        if skill_lower in seen_skills:
            continue

        skill = re.sub(r"\s+", " ", skill)
        skill = skill.strip()

        validated_skills.append(skill)
        seen_skills.add(skill_lower)

    return validated_skills


# =============================================================================
# ENUMS
# =============================================================================


class JobType(str, Enum):
    """Job type enum for career preferences."""

    FULL_TIME = "Full-time"
    PART_TIME = "Part-time"
    CONTRACT = "Contract"
    FREELANCE = "Freelance"
    INTERNSHIP = "Internship"


class WorkArrangement(str, Enum):
    """Work arrangement enum for career preferences."""

    ONSITE = "Onsite"
    REMOTE = "Remote"
    HYBRID = "Hybrid"


class CompanySize(str, Enum):
    """Company size enum for career preferences."""

    STARTUP = "Startup (1-10 employees)"
    SMALL = "Small (11-50 employees)"
    MEDIUM = "Medium (51-200 employees)"
    LARGE = "Large (201-1000 employees)"
    ENTERPRISE = "Enterprise (1000+ employees)"


class MaxTravelPreference(str, Enum):
    """Maximum travel requirement preference enum for career preferences."""

    NONE = "0"
    MINIMAL = "25"
    MODERATE = "50"
    FREQUENT = "75"
    EXTENSIVE = "100"


def _transform_career_preference_enums(v: Any, info: ValidationInfo) -> Any:
    if not v:
        return v

    enum_map = {
        "job_types": JobType,
        "work_arrangements": WorkArrangement,
        "desired_company_sizes": CompanySize,
        "max_travel_preference": MaxTravelPreference,
    }

    target_enum = enum_map.get(info.field_name)
    if not target_enum:
        return v

    def convert_value(val: Any) -> Any:
        if isinstance(val, str):
            try:
                return target_enum[val.upper().replace("-", "_")]
            except KeyError:
                try:
                    return target_enum(val)
                except ValueError:
                    return val
        return val

    if isinstance(v, list):
        return [convert_value(item) for item in v]
    return convert_value(v)


def _validate_desired_salary_range(v: Optional[Dict[str, int]]) -> Optional[Dict[str, int]]:
    if not v:
        return None

    normalized: Dict[str, int] = {}
    for key in ("min", "max"):
        if key not in v:
            continue
        raw = v[key]
        if isinstance(raw, bool):
            raise ValueError(f"Salary {key} must be an integer")
        if isinstance(raw, int):
            amount = raw
        elif isinstance(raw, str):
            digits = re.sub(r"\D", "", raw.strip())
            if not digits:
                continue
            amount = int(digits)
        else:
            raise ValueError(f"Salary {key} must be an integer")
        if amount < 0:
            raise ValueError(f"Salary {key} must be positive")
        if amount > 2000000:
            raise ValueError(f"Salary {key} seems unreasonably high")
        normalized[key] = amount

    if "min" in normalized and "max" in normalized and normalized["min"] >= normalized["max"]:
        raise ValueError("Minimum salary must be less than maximum salary")

    return normalized or None


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class BasicInfoRequest(BaseModel):
    """Basic information step request model."""

    city: str = Field(
        ...,
        min_length=MIN_LENGTH,
        max_length=MAX_LOCATION_LENGTH,
        description="City of residence",
    )
    state: str = Field(
        ...,
        min_length=MIN_LENGTH,
        max_length=MAX_LOCATION_LENGTH,
        description="State/province of residence",
    )
    country: str = Field(
        ...,
        min_length=MIN_LENGTH,
        max_length=MAX_LOCATION_LENGTH,
        description="Country of residence",
    )
    professional_title: str = Field(
        ...,
        min_length=MIN_LENGTH,
        max_length=MAX_TITLE_LENGTH,
        description="Professional title or headline",
    )
    years_experience: int = Field(
        ...,
        ge=0,
        le=MAX_YEARS_EXPERIENCE,
        description="Years of professional experience",
    )
    is_student: bool = Field(False, description="Whether user is currently a student")
    summary: str = Field(
        ...,
        min_length=MIN_LENGTH,
        max_length=MAX_SUMMARY_LENGTH,
        description="Professional summary or bio (resume-style overview of your background)",
    )
    phone: str = Field(
        default="",
        max_length=MAX_PHONE_LENGTH,
        description="Phone for applications (optional)",
    )
    linkedin_url: str = Field(default="", max_length=MAX_PROFILE_URL_LENGTH)
    github_url: str = Field(default="", max_length=MAX_PROFILE_URL_LENGTH)
    portfolio_url: str = Field(default="", max_length=MAX_PROFILE_URL_LENGTH)

    validate_city = field_validator("city")(
        lambda v: _validate_required_location_field(v, "City")
    )
    validate_state = field_validator("state")(
        lambda v: _validate_required_location_field(v, "State")
    )
    validate_country = field_validator("country")(
        lambda v: _validate_required_location_field(v, "Country")
    )
    validate_professional_title = field_validator("professional_title")(
        lambda v: _validate_professional_name(v, "Professional title")
    )
    validate_years_experience = field_validator("years_experience")(
        _validate_basic_info_years_experience
    )
    validate_summary = field_validator("summary")(
        lambda v: _validate_text_field(v, "Professional summary", MAX_SUMMARY_LENGTH)
    )
    validate_phone = field_validator("phone")(_validate_basic_info_phone)
    validate_linkedin_url = field_validator("linkedin_url")(
        lambda v: _validate_optional_profile_url(v, "LinkedIn URL")
    )
    validate_github_url = field_validator("github_url")(
        lambda v: _validate_optional_profile_url(v, "GitHub")
    )
    validate_portfolio_url = field_validator("portfolio_url")(
        lambda v: _validate_optional_profile_url(v, "Portfolio URL")
    )


class WorkExperienceItem(BaseModel):
    """Work experience item model."""

    company: str = Field(
        ...,
        min_length=MIN_LENGTH,
        max_length=MAX_COMPANY_LENGTH,
        description="Company or organization name",
    )
    job_title: str = Field(
        ...,
        min_length=MIN_LENGTH,
        max_length=MAX_TITLE_LENGTH,
        description="Job title or position held",
    )
    start_date: str = Field(
        ...,
        min_length=7,
        max_length=7,
        description="Employment start date in YYYY-MM format",
    )
    end_date: Optional[str] = Field(
        None,
        min_length=7,
        max_length=7,
        description="Employment end date in YYYY-MM format or 'Present' for current position",
    )
    description: Optional[str] = Field(
        None,
        min_length=MIN_LENGTH,
        max_length=MAX_DESCRIPTION_LENGTH,
        description="Job responsibilities and achievements",
    )
    is_current: bool = Field(False, description="Whether this is the current position")

    validate_company = field_validator("company")(
        lambda v: _validate_professional_name(v, "Company name")
    )
    validate_job_title = field_validator("job_title")(
        lambda v: _validate_professional_name(v, "Job title")
    )
    validate_start_date = field_validator("start_date")(_validate_employment_start_date)
    validate_end_date = field_validator("end_date")(_validate_employment_end_date)
    validate_description = field_validator("description")(
        lambda v: _validate_text_field(v, "Job description", 2000)
    )
    validate_is_current = field_validator("is_current")(_validate_employment_is_current)


class WorkExperienceRequest(BaseModel):
    """Work experience step request model."""

    work_experience: List[WorkExperienceItem] = Field(
        default_factory=list,
        max_items=MAX_WORK_EXPERIENCE_ITEMS,
        description="List of work experience entries",
    )

    validate_work_experience = field_validator("work_experience")(
        _validate_work_experience_list
    )


class EducationItem(BaseModel):
    """Single education entry (school / degree / dates)."""

    institution: str = Field(
        ...,
        min_length=MIN_LENGTH,
        max_length=MAX_COMPANY_LENGTH,
        description="School or institution name",
    )
    degree: str = Field(
        ...,
        min_length=MIN_LENGTH,
        max_length=MAX_TITLE_LENGTH,
        description="Degree or qualification",
    )
    field_of_study: str = Field(
        ...,
        min_length=MIN_LENGTH,
        max_length=MAX_FIELD_OF_STUDY_LENGTH,
        description="Major or field of study (required)",
    )
    start_date: str = Field(
        ...,
        min_length=7,
        max_length=7,
        description="Start date in YYYY-MM format (required)",
    )
    end_date: Optional[str] = Field(
        None,
        max_length=7,
        description="End / graduation date in YYYY-MM format",
    )
    is_current: bool = Field(False, description="Currently enrolled")

    validate_institution = field_validator("institution")(
        lambda v: _validate_professional_name(v, "Institution")
    )
    validate_degree = field_validator("degree")(
        lambda v: _validate_professional_name(v, "Degree")
    )
    validate_field_of_study = field_validator("field_of_study")(_validate_education_field_of_study)
    validate_edu_start_date = field_validator("start_date")(_validate_education_start_date)
    validate_edu_end_date = field_validator("end_date")(_validate_education_end_date)
    validate_edu_is_current = field_validator("is_current")(_validate_education_is_current)

    @model_validator(mode="after")
    def validate_education_end_when_completed(self) -> "EducationItem":
        """Require graduation/end date unless the user marks Currently enrolled."""
        if not self.is_current:
            ed = self.end_date
            if ed is None or (isinstance(ed, str) and not str(ed).strip()):
                raise ValueError(
                    "End date is required unless you mark Currently enrolled"
                )
        return self


class EducationRequest(BaseModel):
    """Education step request model."""

    education: List[EducationItem] = Field(
        default_factory=list,
        max_items=MAX_EDUCATION_ITEMS,
        description="Education history entries",
    )


class SkillsQualificationsRequest(BaseModel):
    """Skills and qualifications step request model."""

    skills: List[str] = Field(
        default_factory=list,
        min_items=MIN_SKILLS_ITEMS,
        max_items=MAX_SKILLS_ITEMS,
        description="List of professional skills",
    )

    validate_skills_list = field_validator("skills")(_validate_skills_list)


class CareerPreferencesRequest(BaseModel):
    """Career preferences step request model."""

    desired_salary_range: Optional[Dict[str, int]] = Field(
        None, description="Optional minimum and/or maximum salary expectations"
    )
    desired_company_sizes: List[CompanySize] = Field(
        default_factory=list,
        min_items=MIN_COMPANY_SIZE_ITEMS,
        max_items=MAX_COMPANY_SIZE_ITEMS,
        description="List of preferred company sizes",
    )
    job_types: List[JobType] = Field(
        default_factory=list,
        min_items=MIN_JOB_TYPE_ITEMS,
        max_items=MAX_JOB_TYPE_ITEMS,
        description="List of preferred employment types",
    )
    work_arrangements: List[WorkArrangement] = Field(
        default_factory=list,
        min_items=MIN_WORK_ARRANGEMENT_ITEMS,
        max_items=MAX_WORK_ARRANGEMENT_ITEMS,
        description="List of preferred work arrangements",
    )
    willing_to_relocate: bool = Field(
        False, description="Whether user is willing to relocate for a job"
    )
    requires_visa_sponsorship: bool = Field(
        False, description="Whether user requires visa sponsorship"
    )
    work_authorization: Optional[str] = Field(
        default=None,
        description=(
            "no_work_authorization | has_work_authorization | "
            "us_lawful_permanent_resident | us_citizen"
        ),
    )
    has_security_clearance: bool = Field(
        False, description="Whether user has security clearance"
    )
    max_travel_preference: MaxTravelPreference = Field(
        MaxTravelPreference.NONE,
        description="Maximum travel percentage user is willing to accept",
    )

    transform_enums = field_validator(
        "job_types",
        "work_arrangements",
        "desired_company_sizes",
        "max_travel_preference",
        mode="before",
    )(_transform_career_preference_enums)
    validate_desired_salary_range = field_validator("desired_salary_range")(
        _validate_desired_salary_range
    )

    @model_validator(mode="after")
    def _normalize_work_authorization(self) -> "CareerPreferencesRequest":
        raw = self.work_authorization
        if raw is None or (isinstance(raw, str) and not str(raw).strip()):
            object.__setattr__(self, "work_authorization", None)
            return self
        wa = str(raw).strip().lower()
        if wa not in _VALID_WORK_AUTHORIZATION:
            raise ValueError(
                "work_authorization must be one of: "
                "no_work_authorization, has_work_authorization, "
                "us_lawful_permanent_resident, us_citizen"
            )
        object.__setattr__(self, "work_authorization", wa)
        return self


class ProfileStatusResponse(BaseModel):
    """Profile completion status response."""

    profile_completed: bool = Field(..., description="Whether profile is completed")
    completion_percentage: int = Field(..., description="Completion percentage")
    completed_steps: List[str] = Field(..., description="List of completed steps")
    missing_steps: List[str] = Field(..., description="List of missing steps")
    next_step: Optional[str] = Field(None, description="Next recommended step")


class ProfileDataResponse(BaseModel):
    """Complete profile data response."""

    user_info: Dict[str, Any] = Field(
        ...,
        description="Authentication data (id, email, full_name, created_at, auth_method)",
    )
    profile_data: Dict[str, Any] = Field(
        ..., description="Complete profile data from user_profiles table"
    )
    completion_status: ProfileStatusResponse = Field(
        ..., description="Profile completion status"
    )


# =============================================================================
# RESUME PARSING ENDPOINT
# =============================================================================


class ResumeParseResponse(BaseModel):
    """Response model for resume parsing endpoint."""

    success: bool = Field(..., description="Whether parsing was successful")
    data: Optional[Dict[str, Any]] = Field(
        None, description="Parsed profile data from resume"
    )
    message: str = Field(..., description="Status message")
    confidence: Optional[str] = Field(
        None, description="Parsing confidence: HIGH, MEDIUM, or LOW"
    )
    processing_time: Optional[float] = Field(
        None, description="Time taken to parse in seconds"
    )


_MIME_BY_RESUME_EXT: Dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain; charset=utf-8",
}


def _merge_resume_contact_into_profile_if_empty(
    prof: UserProfileModel,
    parsed: Dict[str, Any],
) -> None:
    """Fill phone / profile URLs from resume parse only when DB fields are empty."""
    p_phone = parsed.get("phone")
    if isinstance(p_phone, str) and p_phone.strip() and not (prof.phone and prof.phone.strip()):
        prof.phone = p_phone.strip()[:MAX_PHONE_LENGTH]

    for fld in ("linkedin_url", "github_url", "portfolio_url"):
        val = parsed.get(fld)
        if not isinstance(val, str) or not val.strip():
            continue
        cur = getattr(prof, fld)
        if cur and str(cur).strip():
            continue
        try:
            _validate_profile_url_field(val, fld)
        except ValueError:
            continue
        setattr(prof, fld, val.strip()[:MAX_PROFILE_URL_LENGTH])


async def _upsert_user_resume_asset(
    db: AsyncSession,
    user_id: uuid.UUID,
    content: bytes,
    filename: str,
    file_extension: str,
) -> None:
    """Write bytes to disk and upsert ``user_resume_assets`` (one row per user)."""
    base_dir = settings.user_resume_storage_dir
    rel, sha_hex, _ext = save_resume_bytes(base_dir, user_id, content, filename)
    mime = _MIME_BY_RESUME_EXT.get(file_extension, "application/octet-stream")
    res = await db.execute(select(UserResumeAsset).where(UserResumeAsset.user_id == user_id))
    row = res.scalar_one_or_none()
    safe_name = (filename or "resume")[:255]
    if row:
        delete_resume_file(base_dir, row.storage_relative_path)
        row.storage_relative_path = rel
        row.original_filename = safe_name
        row.mime_type = mime[:100]
        row.byte_size = len(content)
        row.sha256_hex = sha_hex
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(
            UserResumeAsset(
                id=uuid.uuid4(),
                user_id=user_id,
                storage_relative_path=rel,
                original_filename=safe_name,
                mime_type=mime[:100],
                byte_size=len(content),
                sha256_hex=sha_hex,
            )
        )


@router.post("/parse-resume", response_model=ResumeParseResponse)
async def parse_resume_endpoint(
    resume: UploadFile = File(..., description="Resume file (PDF, DOCX, or TXT)"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
):
    """Parse a resume file and extract structured profile data."""
    try:
        user_id = get_user_id_from_token(current_user)

        # Rate limit: 10 parse attempts per hour (LLM + CPU-heavy operation)
        is_allowed, _remaining = await check_rate_limit(
            identifier=f"parse_resume:{user_id}",
            limit=10,
            window_seconds=3600,
        )
        if not is_allowed:
            raise rate_limit_error("Too many resume parse attempts. Please try again later.", retry_after=3600)

        # Validate file shape before API key — users should see format errors even when BYOK/server key is missing.
        if not resume.filename:
            raise validation_error("Filename is required")

        file_extension = resume.filename.lower().split(".")[-1]
        if file_extension == "doc":
            raise validation_error(_LEGACY_DOC_USER_MSG)
        if file_extension not in SUPPORTED_EXTENSIONS:
            raise validation_error(f"Unsupported file format. Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}")

        content = await resume.read()

        if not content:
            raise validation_error("Uploaded file is empty")

        if len(content) > MAX_RESUME_SIZE_BYTES:
            raise APIError(ErrorCode.VALIDATION_ERROR, f"File is too large. Maximum size is {MAX_RESUME_SIZE_BYTES // (1024 * 1024)} MB.", status_code=413)

        # Validate actual file content matches the declared extension (prevents spoofing)
        expected_magic = _RESUME_MAGIC.get(file_extension)
        if expected_magic is not None and not content.startswith(expected_magic):
            if content.startswith(_MS_WORD_DOC_MAGIC_PREFIX):
                raise validation_error(_LEGACY_DOC_USER_MSG)
            raise validation_error(
                "File content does not match the declared type (e.g. renamed file). "
                "Use a real PDF, Word .docx, or UTF-8 text file."
            )
        if file_extension == "txt":
            try:
                content.decode("utf-8")
            except UnicodeDecodeError:
                raise validation_error("TXT files must be UTF-8 encoded.")

        # Resolve the user's BYOK key (if any) so the LLM call uses it.
        user_api_key = None
        user_result = await db.execute(select(User).where(User.id == user_id))
        user_record = user_result.scalar_one_or_none()
        if user_record and user_record.gemini_api_key_encrypted:
            try:
                user_api_key = decrypt_api_key(user_record.gemini_api_key_encrypted)
            except Exception as e:
                logger.warning(
                    "Failed to decrypt user API key for resume parse: %s",
                    sanitize_log_value(str(e)),
                )

        server_has_key = bool(getattr(settings, 'gemini_api_key', None)) or settings.use_vertex_ai
        if not user_api_key and not server_has_key:
            raise no_api_key_error()

        logger.info('Parsing resume for user %s: %s (%d bytes)', sanitize_log_value(current_user.get("id")), sanitize_log_value(resume.filename), len(content))

        parsed_data = await parse_resume_from_file(content, resume.filename, user_api_key=user_api_key)

        try:
            await _upsert_user_resume_asset(
                db,
                user_id,
                content,
                resume.filename or "resume.dat",
                file_extension,
            )
            prof_r = await db.execute(select(UserProfileModel).where(UserProfileModel.user_id == user_id))
            prof = prof_r.scalar_one_or_none()
            if prof:
                _merge_resume_contact_into_profile_if_empty(prof, parsed_data)
                prof.updated_at = datetime.now(timezone.utc)
            await db.commit()
            await invalidate_user_profile(str(user_id))
        except Exception as merge_err:
            await db.rollback()
            logger.warning(
                "Resume parse succeeded but persist/merge failed: %s",
                sanitize_log_value(str(merge_err)),
                exc_info=True,
            )

        return ResumeParseResponse(
            success=True,
            data=parsed_data,
            message="Resume parsed successfully",
            confidence=parsed_data.get("parsing_confidence", "MEDIUM"),
            processing_time=parsed_data.get("processing_time", 0),
        )

    except HTTPException:
        raise

    except ValueError as ve:
        logger.warning("Resume parsing validation error: %s", sanitize_log_value(str(ve)))
        raise validation_error(str(ve))

    except Exception as e:
        logger.error("Resume parsing failed: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to parse resume. Please try again or enter your information manually.")


@router.get("/resume")
async def download_stored_resume(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
):
    """Download the user's stored resume file (from parse-resume or future uploads)."""
    user_id = get_user_id_from_token(current_user)
    res = await db.execute(select(UserResumeAsset).where(UserResumeAsset.user_id == user_id))
    row = res.scalar_one_or_none()
    if not row:
        raise not_found_error(resource_type="Stored resume")
    try:
        path = resume_absolute_path(settings.user_resume_storage_dir, row.storage_relative_path)
    except ValueError as e:
        logger.warning(
            "Invalid resume storage path for user %s: %s",
            sanitize_log_value(user_id),
            sanitize_log_value(e),
        )
        raise not_found_error(resource_type="Stored resume")
    if not path.is_file():
        raise not_found_error(resource_type="Stored resume")
    return FileResponse(
        str(path),
        media_type=row.mime_type or "application/octet-stream",
        filename=row.original_filename or "resume",
    )


@router.delete("/resume")
async def delete_stored_resume(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
):
    """Remove stored resume file metadata and on-disk bytes."""
    user_id = get_user_id_from_token(current_user)
    res = await db.execute(select(UserResumeAsset).where(UserResumeAsset.user_id == user_id))
    row = res.scalar_one_or_none()
    if not row:
        raise not_found_error(resource_type="Stored resume")
    delete_resume_file(settings.user_resume_storage_dir, row.storage_relative_path)
    await db.execute(sa_delete(UserResumeAsset).where(UserResumeAsset.user_id == user_id))
    await db.commit()
    await invalidate_user_profile(str(user_id))
    return {"message": "Resume file deleted"}


# =============================================================================
# API ENDPOINTS
# =============================================================================


@router.get("/")
async def get_profile_data(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
):
    """Get complete user profile data with Redis caching."""
    try:
        user_id = get_user_id_from_token(current_user)
        user_id_str = str(user_id)

        # Try to get from cache first
        cached_profile = await get_cached_user_profile(user_id_str)
        if cached_profile:
            logger.debug(
                'Profile cache hit for user %s...',
                sanitize_log_value(sanitize_log_value(user_id_str)[:8]),
            )
            return cached_profile

        # Get user profile from database
        result = await db.execute(
            select(UserProfileModel).where(UserProfileModel.user_id == user_id)
        )
        user_profile = result.scalar_one_or_none()

        if not user_profile:
            logger.info(
                "No profile found for user %s, creating empty profile",
                sanitize_log_value(str(user_id)),
            )
            # Create empty profile
            user_profile = UserProfileModel(
                id=uuid.uuid4(),
                user_id=user_id,
            )
            db.add(user_profile)
            await db.commit()
            await db.refresh(user_profile)

        # Get completion status
        completion_status = await get_profile_completion_status(
            user_id, user_profile, db
        )

        # Prepare user info
        user_info = {
            "id": current_user["id"],
            "email": current_user["email"],
            "full_name": current_user["full_name"],
            "auth_method": current_user["auth_method"],
            "profile_completed": current_user["profile_completed"],
            "has_google_linked": current_user.get("has_google_linked", False),
            "has_password": current_user.get("has_password", True),
            "created_at": current_user["created_at"],
            "updated_at": current_user["updated_at"],
            "last_login": current_user["last_login"],
        }

        # Profile data structure
        profile_data = user_profile.to_dict() if user_profile else {}
        resume_q = await db.execute(select(UserResumeAsset).where(UserResumeAsset.user_id == user_id))
        resume_row = resume_q.scalar_one_or_none()
        if resume_row:
            profile_data["resume_file"] = {"has_file": True, **resume_row.to_dict()}
        else:
            profile_data["resume_file"] = {"has_file": False}

        response_data = {
            "user_info": serialize_object_for_json(user_info),
            "profile_data": serialize_object_for_json(profile_data),
            "completion_status": serialize_object_for_json(completion_status),
        }

        # Cache the response
        await cache_user_profile(user_id_str, response_data)

        return response_data

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Failed to get profile data: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to get profile data")


@router.put("/basic-info")
async def update_basic_info(
    basic_info: BasicInfoRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
):
    """Update basic user information (Step 1 of profile setup)."""
    try:
        user_id = get_user_id_from_token(current_user)

        # Check if profile exists
        result = await db.execute(
            select(UserProfileModel).where(UserProfileModel.user_id == user_id)
        )
        user_profile = result.scalar_one_or_none()

        if user_profile:
            # Update existing profile
            user_profile.city = basic_info.city
            user_profile.state = basic_info.state
            user_profile.country = basic_info.country
            user_profile.professional_title = basic_info.professional_title
            user_profile.years_experience = basic_info.years_experience
            user_profile.is_student = basic_info.is_student
            user_profile.summary = basic_info.summary
            user_profile.phone = _blank_to_none(basic_info.phone)
            user_profile.linkedin_url = _blank_to_none(basic_info.linkedin_url)
            user_profile.github_url = _blank_to_none(basic_info.github_url)
            user_profile.portfolio_url = _blank_to_none(basic_info.portfolio_url)
            user_profile.updated_at = datetime.now(timezone.utc)
        else:
            # Create new profile
            user_profile = UserProfileModel(
                id=uuid.uuid4(),
                user_id=user_id,
                city=basic_info.city,
                state=basic_info.state,
                country=basic_info.country,
                professional_title=basic_info.professional_title,
                years_experience=basic_info.years_experience,
                is_student=basic_info.is_student,
                summary=basic_info.summary,
                phone=_blank_to_none(basic_info.phone),
                linkedin_url=_blank_to_none(basic_info.linkedin_url),
                github_url=_blank_to_none(basic_info.github_url),
                portfolio_url=_blank_to_none(basic_info.portfolio_url),
            )
            db.add(user_profile)

        await db.commit()
        
        # Invalidate profile cache
        await invalidate_user_profile(str(user_id))
        
        logger.info("Updated basic info for user: %s", _log_user_email(current_user))

        return {"message": "Basic information updated successfully"}

    except Exception as e:
        await db.rollback()
        logger.error("Failed to update basic info: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to update basic information")


@router.put("/work-experience")
async def update_work_experience(
    work_data: WorkExperienceRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
):
    """Update work experience (Step 2 of profile setup)."""
    try:
        user_id = get_user_id_from_token(current_user)

        # Convert to dict format for storage
        work_experience = [exp.model_dump() for exp in work_data.work_experience]

        # Get or create profile
        result = await db.execute(
            select(UserProfileModel).where(UserProfileModel.user_id == user_id)
        )
        user_profile = result.scalar_one_or_none()

        if user_profile:
            user_profile.work_experience = work_experience
            flag_modified(user_profile, "work_experience")
            user_profile.updated_at = datetime.now(timezone.utc)
        else:
            user_profile = UserProfileModel(
                id=uuid.uuid4(),
                user_id=user_id,
                work_experience=work_experience,
            )
            db.add(user_profile)

        await db.commit()
        
        # Invalidate profile cache
        await invalidate_user_profile(str(user_id))

        logger.info('Updated work experience for user: %s - %s entries', _log_user_email(current_user), sanitize_log_value(len(work_experience)))

        current_positions = [
            exp for exp in work_experience if exp.get("is_current", False)
        ]

        return {
            "message": "Work experience updated successfully",
            "summary": {
                "total_entries": len(work_experience),
                "current_positions": len(current_positions),
                "has_experience": len(work_experience) > 0,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(
            "Failed to update work experience for user %s: %s", _log_user_email(current_user), sanitize_log_value(str(e)),
            exc_info=True,
        )
        raise internal_error("Failed to update work experience")


@router.put("/education")
async def update_education(
    edu_data: EducationRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
):
    """Update education history (Step 3 of profile setup)."""
    try:
        user_id = get_user_id_from_token(current_user)
        education = [row.model_dump() for row in edu_data.education]

        result = await db.execute(
            select(UserProfileModel).where(UserProfileModel.user_id == user_id)
        )
        user_profile = result.scalar_one_or_none()

        if user_profile:
            user_profile.education = education
            flag_modified(user_profile, "education")
            user_profile.updated_at = datetime.now(timezone.utc)
        else:
            user_profile = UserProfileModel(
                id=uuid.uuid4(),
                user_id=user_id,
                education=education,
            )
            db.add(user_profile)

        await db.commit()

        await invalidate_user_profile(str(user_id))

        logger.info('Updated education for user: %s — %s entries', _log_user_email(current_user), sanitize_log_value(len(education)))

        return {
            "message": "Education updated successfully",
            "summary": {
                "total_entries": len(education),
                "has_education": len(education) > 0,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(
            "Failed to update education for user %s: %s", _log_user_email(current_user), sanitize_log_value(str(e)),
            exc_info=True,
        )
        raise internal_error("Failed to update education")


@router.put("/skills-qualifications")
async def update_skills_qualifications(
    skills_data: SkillsQualificationsRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
):
    """Update skills and qualifications (Step 4 of profile setup)."""
    try:
        user_id = get_user_id_from_token(current_user)

        # Get or create profile
        result = await db.execute(
            select(UserProfileModel).where(UserProfileModel.user_id == user_id)
        )
        user_profile = result.scalar_one_or_none()

        if user_profile:
            user_profile.skills = skills_data.skills
            flag_modified(user_profile, "skills")
            user_profile.updated_at = datetime.now(timezone.utc)
        else:
            user_profile = UserProfileModel(
                id=uuid.uuid4(),
                user_id=user_id,
                skills=skills_data.skills,
            )
            db.add(user_profile)

        await db.commit()
        
        # Invalidate profile cache
        await invalidate_user_profile(str(user_id))

        logger.info('Updated skills and qualifications for user: %s', _log_user_email(current_user))

        return {"message": "Skills and qualifications updated successfully"}

    except Exception as e:
        await db.rollback()
        logger.error("Failed to update skills and qualifications: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to update skills and qualifications")


@router.put("/career-preferences")
async def update_career_preferences(
    preferences: CareerPreferencesRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
):
    """Update career preferences (Step 5 of profile setup)."""
    try:
        user_id = get_user_id_from_token(current_user)

        # Get or create profile
        result = await db.execute(
            select(UserProfileModel).where(UserProfileModel.user_id == user_id)
        )
        user_profile = result.scalar_one_or_none()

        # Convert enums to values
        job_types = [jt.value for jt in preferences.job_types] if preferences.job_types else []
        work_arrangements = [wa.value for wa in preferences.work_arrangements] if preferences.work_arrangements else []
        company_sizes = [cs.value for cs in preferences.desired_company_sizes] if preferences.desired_company_sizes else []
        max_travel = preferences.max_travel_preference.value if preferences.max_travel_preference else None

        if user_profile:
            user_profile.desired_salary_range = preferences.desired_salary_range
            user_profile.job_types = job_types
            user_profile.work_arrangements = work_arrangements
            user_profile.desired_company_sizes = company_sizes
            user_profile.willing_to_relocate = preferences.willing_to_relocate
            user_profile.requires_visa_sponsorship = preferences.requires_visa_sponsorship
            user_profile.work_authorization = preferences.work_authorization
            user_profile.has_security_clearance = preferences.has_security_clearance
            user_profile.max_travel_preference = max_travel
            user_profile.updated_at = datetime.now(timezone.utc)
            for _f in ("desired_salary_range", "job_types", "work_arrangements", "desired_company_sizes"):
                flag_modified(user_profile, _f)
        else:
            user_profile = UserProfileModel(
                id=uuid.uuid4(),
                user_id=user_id,
                desired_salary_range=preferences.desired_salary_range,
                job_types=job_types,
                work_arrangements=work_arrangements,
                desired_company_sizes=company_sizes,
                willing_to_relocate=preferences.willing_to_relocate,
                requires_visa_sponsorship=preferences.requires_visa_sponsorship,
                work_authorization=preferences.work_authorization,
                has_security_clearance=preferences.has_security_clearance,
                max_travel_preference=max_travel,
            )
            db.add(user_profile)

        await db.commit()
        
        # Invalidate profile cache
        await invalidate_user_profile(str(user_id))

        logger.info("Updated career preferences for user: %s", _log_user_email(current_user))

        return {"message": "Career preferences updated successfully"}

    except Exception as e:
        await db.rollback()
        logger.error("Failed to update career preferences: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to update career preferences")


# =============================================================================
# PROFILE COMPLETION ENDPOINT
# =============================================================================


@router.post("/complete")
async def complete_profile(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
):
    """
    Mark user profile as complete after all sections are filled.
    
    This endpoint validates that all required sections are complete
    and updates the user's profile_completed flag.
    """
    try:
        user_id = get_user_id_from_token(current_user)

        # Get user profile to check completion
        result = await db.execute(
            select(UserProfileModel).where(UserProfileModel.user_id == user_id)
        )
        user_profile = result.scalar_one_or_none()

        if not user_profile:
            raise validation_error("Profile data not found. Please complete all profile sections first.")

        # Check all required sections are complete
        basic_complete = _check_basic_info_completion(user_profile)
        work_complete = _check_work_experience_completion(user_profile)
        education_complete = _check_education_completion(user_profile)
        skills_complete = _check_skills_qualifications_completion(user_profile)
        preferences_complete = _check_career_preferences_completion(user_profile)

        if not all(
            [
                basic_complete,
                work_complete,
                education_complete,
                skills_complete,
                preferences_complete,
            ]
        ):
            missing = []
            if not basic_complete:
                missing.append("Basic Info")
            if not work_complete:
                missing.append("Work Experience")
            if not education_complete:
                missing.append("Education")
            if not skills_complete:
                missing.append("Skills")
            if not preferences_complete:
                missing.append("Career Preferences")
            
            raise validation_error(f"Please complete the following sections: {', '.join(missing)}")

        # Update user's profile_completed flag
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                profile_completed=True,
                profile_completion_percentage=100,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

        # Invalidate profile cache
        await invalidate_user_profile(str(user_id))

        logger.info("Profile marked as complete for user: %s", _log_user_email(current_user))

        return {
            "success": True,
            "message": "Profile completed successfully!",
            "profile_completed": True,
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to complete profile: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to complete profile")


# =============================================================================
# API KEY MANAGEMENT ENDPOINTS
# =============================================================================


class ApiKeyRequest(BaseModel):
    """Request model for setting an API key."""

    api_key: str = Field(
        ...,
        min_length=20,
        max_length=100,
        description="The Gemini API key to store",
    )


class ApiKeyStatusResponse(BaseModel):
    """Response model for API key status."""

    has_user_key: bool = Field(..., description="Whether user has their own API key configured")
    has_api_key: bool = Field(..., description="Whether user has an API key configured (alias for has_user_key)")
    server_has_key: bool = Field(..., description="Whether server has a default API key configured")
    use_vertex_ai: bool = Field(False, description="Whether the server is using Vertex AI (model choice locked)")
    key_preview: Optional[str] = Field(
        None, description="Masked preview of the key (first 4 and last 4 chars)"
    )


@router.get("/api-key/status", response_model=ApiKeyStatusResponse)
async def get_api_key_status(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> ApiKeyStatusResponse:
    """
    Check if user has a Gemini API key configured.
    
    Returns status and a masked preview of the key if set.
    """
    try:
        user_id = get_user_id_from_token(current_user)

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise not_found_error("User not found")

        has_user_key = user.gemini_api_key_encrypted is not None
        key_preview = None

        if has_user_key:
            try:
                decrypted_key = decrypt_api_key(user.gemini_api_key_encrypted)
                # Show first 4 and last 4 characters
                if len(decrypted_key) > 8:
                    key_preview = f"{decrypted_key[:4]}...{decrypted_key[-4:]}"
                else:
                    key_preview = "****"
            except Exception:
                # If decryption fails, key is corrupted
                key_preview = "(invalid)"

        # Check if server has a default API key configured
        from config.settings import get_settings
        settings = get_settings()
        use_vertex_ai = bool(getattr(settings, "use_vertex_ai", False))
        # Vertex AI also means the server provides AI — no user key needed
        server_has_key = bool(settings.gemini_api_key) or use_vertex_ai

        return ApiKeyStatusResponse(
            has_user_key=has_user_key,
            has_api_key=has_user_key,  # Alias for backward compatibility
            server_has_key=server_has_key,
            use_vertex_ai=use_vertex_ai,
            key_preview=key_preview,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get API key status: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to get API key status")


@router.post("/api-key")
async def set_api_key(
    request: ApiKeyRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
):
    """
    Set or update the user's Gemini API key.
    
    The key is encrypted before storage and never logged.
    """
    try:
        user_id = get_user_id_from_token(current_user)

        # Validate the API key format
        if not validate_gemini_api_key(request.api_key):
            raise validation_error("Invalid API key format. Please check your Gemini API key.")

        # Encrypt the API key
        encrypted_key = encrypt_api_key(request.api_key.strip())

        # Update user record
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                gemini_api_key_encrypted=encrypted_key,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

        # Invalidate user profile cache and all per-user LLM response caches
        # so that requests under the new key start fresh.
        await invalidate_user_profile(str(user_id))
        await invalidate_user_llm_cache(str(user_id))

        logger.info("API key updated for user: %s", _log_user_email(current_user))

        return {"message": "API key saved successfully"}

    except HTTPException:
        raise
    except ValueError as e:
        raise validation_error(str(e))
    except Exception as e:
        await db.rollback()
        logger.error("Failed to save API key: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to save API key")


@router.delete("/api-key")
async def delete_api_key(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
):
    """
    Delete the user's stored Gemini API key.
    """
    try:
        user_id = get_user_id_from_token(current_user)

        # Update user record to remove the key
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                gemini_api_key_encrypted=None,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

        # Invalidate user profile cache and all per-user LLM response caches
        # so that requests now using the shared default key start fresh.
        await invalidate_user_profile(str(user_id))
        await invalidate_user_llm_cache(str(user_id))

        logger.info("API key deleted for user: %s", _log_user_email(current_user))

        return {"message": "API key deleted successfully"}

    except Exception as e:
        await db.rollback()
        logger.error("Failed to delete API key: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to delete API key")


@router.post("/api-key/validate")
async def validate_api_key_endpoint(
    request: ApiKeyRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Validate a Gemini API key by making a test API call.
    
    This endpoint tests if the key works without saving it.
    """
    try:
        user_id = get_user_id_from_token(current_user)

        # Rate limit: 10 validation attempts per hour per user (calls external Google API)
        is_allowed, _remaining = await check_rate_limit(
            identifier=f"api_key_validate:{user_id}",
            limit=10,
            window_seconds=3600,
        )
        if not is_allowed:
            raise rate_limit_error("Too many API key validation attempts. Please try again later.", retry_after=3600)

        if not validate_gemini_api_key(request.api_key):
            raise validation_error("Invalid API key format")

        # Test the API key by making a simple call
        from google import genai as google_genai

        client = google_genai.Client(api_key=request.api_key.strip())

        try:
            models = list(client.models.list())
            if not models:
                raise validation_error("API key appears valid but returned no models")
        except Exception as api_error:
            logger.warning("API key validation failed: %s", sanitize_log_value(str(api_error)))
            raise validation_error("API key validation failed. Please check your key is correct and has proper permissions.")

        return {
            "valid": True,
            "message": "API key is valid",
            "models_available": len(models),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("API key validation error: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to validate API key")


@router.get("/status", response_model=ProfileStatusResponse)
async def get_profile_status(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> ProfileStatusResponse:
    """Get profile completion status for the authenticated user."""
    try:
        user_id = get_user_id_from_token(current_user)

        result = await db.execute(
            select(UserProfileModel).where(UserProfileModel.user_id == user_id)
        )
        user_profile = result.scalar_one_or_none()

        steps: Dict[str, bool] = {
            "basic_info": _check_basic_info_completion(user_profile),
            "work_experience": _check_work_experience_completion(user_profile),
            "education": _check_education_completion(user_profile),
            "skills_qualifications": _check_skills_qualifications_completion(user_profile),
            "career_preferences": _check_career_preferences_completion(user_profile),
        }

        completed_steps: List[str] = [step for step, completed in steps.items() if completed]
        missing_steps: List[str] = [step for step, completed in steps.items() if not completed]

        completion_percentage: int = int((len(completed_steps) / len(steps)) * 100)
        next_step: Optional[str] = missing_steps[0] if missing_steps else None
        profile_completed: bool = len(missing_steps) == 0

        return ProfileStatusResponse(
            profile_completed=profile_completed,
            completion_percentage=completion_percentage,
            completed_steps=completed_steps,
            missing_steps=missing_steps,
            next_step=next_step,
        )

    except Exception as e:
        logger.error("Failed to get profile status: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to get profile status")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


async def get_profile_completion_status(
    user_id: uuid.UUID, user_profile: Optional[UserProfileModel], db: AsyncSession
) -> Dict[str, Any]:
    """Get profile completion status for a user."""
    basic_info_complete = _check_basic_info_completion(user_profile)
    work_experience_complete = _check_work_experience_completion(user_profile)
    education_complete = _check_education_completion(user_profile)
    skills_qualifications_complete = _check_skills_qualifications_completion(user_profile)
    career_preferences_complete = _check_career_preferences_completion(user_profile)

    completed_sections = sum([
        1 if basic_info_complete else 0,
        1 if work_experience_complete else 0,
        1 if education_complete else 0,
        1 if skills_qualifications_complete else 0,
        1 if career_preferences_complete else 0,
    ])
    total_sections = 5
    completion_percentage = int((completed_sections / total_sections) * 100)

    # Update user document with completion status
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(
            profile_completed=completion_percentage == 100,
            profile_completion_percentage=completion_percentage,
            updated_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()

    return {
        "basic_info": basic_info_complete,
        "work_experience": work_experience_complete,
        "education": education_complete,
        "skills_qualifications": skills_qualifications_complete,
        "career_preferences": career_preferences_complete,
        "completion_percentage": completion_percentage,
        "profile_completed": completion_percentage == 100,
    }


def _check_basic_info_completion(user_profile: Optional[UserProfileModel]) -> bool:
    """Check if basic info step is completed."""
    if not user_profile:
        return False

    all_fields = [
        user_profile.city,
        user_profile.state,
        user_profile.country,
        user_profile.professional_title,
        user_profile.years_experience,
        user_profile.summary,
    ]

    return all(field is not None for field in all_fields)


def _check_work_experience_completion(user_profile: Optional[UserProfileModel]) -> bool:
    """Check if work experience step is completed."""
    if not user_profile:
        return False

    work_experience = user_profile.work_experience
    # NULL = step never saved. Empty JSON list [] = user saved "no relevant experience yet"
    # (distinct from NULL in PostgreSQL JSONB).
    if work_experience is None:
        return False
    return True


def _check_education_completion(user_profile: Optional[UserProfileModel]) -> bool:
    """Check if education step is completed (saved rows or explicit empty list)."""
    if not user_profile:
        return False

    education = user_profile.education
    if education is None:
        return False
    return True


def _check_skills_qualifications_completion(user_profile: Optional[UserProfileModel]) -> bool:
    """Check if skills and qualifications step is completed."""
    if not user_profile:
        return False

    skills = user_profile.skills or []
    return len(skills) > 0


def _check_career_preferences_completion(user_profile: Optional[UserProfileModel]) -> bool:
    """Check if career preferences step is completed."""
    if not user_profile:
        return False

    desired_company_sizes = user_profile.desired_company_sizes or []
    job_types = user_profile.job_types or []
    work_arrangements = user_profile.work_arrangements or []
    career_fields_ok = (
        len(desired_company_sizes) > 0
        and len(job_types) > 0
        and len(work_arrangements) > 0
    )
    if not career_fields_ok:
        return False

    wa = (user_profile.work_authorization or "").strip()
    if wa in _VALID_WORK_AUTHORIZATION:
        return True

    # Profiles completed before work_authorization existed: leave column NULL but
    # treat career step as done when the rest of the profile is already complete.
    return (
        _check_basic_info_completion(user_profile)
        and _check_work_experience_completion(user_profile)
        and _check_education_completion(user_profile)
        and _check_skills_qualifications_completion(user_profile)
    )


# =============================================================================
# APPLICATION PREFERENCES ENDPOINTS
# =============================================================================

# Column-level defaults — must match UserWorkflowPreferences model defaults
_PREFERENCE_DEFAULTS: Dict[str, Any] = {
    "workflow_gate_threshold": 0.5,
    "auto_generate_documents": False,
    "cover_letter_tone": "professional",
    "resume_length": "concise",
    "preferred_model": None,
}

_VALID_COVER_LETTER_TONES = {"professional", "conversational", "enthusiastic"}
_VALID_RESUME_LENGTHS = {"concise", "detailed"}
_VALID_MODELS = {
    "gemini-3.5-flash",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
}


class ApplicationPreferencesRequest(BaseModel):
    """Request model for updating workflow application preferences."""

    workflow_gate_threshold: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description=(
            "Match-score threshold (0–1) below which the workflow pauses for confirmation. "
            "Default: 0.5 (50%)"
        ),
    )
    auto_generate_documents: Optional[bool] = Field(
        None,
        description=(
            "When true, resume advice and cover letter are generated automatically "
            "after company research. When false (default), they are generated on demand."
        ),
    )
    cover_letter_tone: Optional[str] = Field(
        None,
        description="Writing tone for cover letters. One of: professional, conversational, enthusiastic.",
    )
    resume_length: Optional[str] = Field(
        None,
        description="Verbosity of resume advice. One of: concise, detailed.",
    )
    preferred_model: Optional[str] = Field(
        None,
        description=(
            "Preferred Gemini model for BYOK users. "
            f"Allowed values: {', '.join(sorted(_VALID_MODELS))}. "
            "Set to null to revert to the system default."
        ),
    )


class ApplicationPreferencesResponse(BaseModel):
    """Response model for application preferences."""

    workflow_gate_threshold: float
    auto_generate_documents: bool
    cover_letter_tone: str
    resume_length: str
    preferred_model: Optional[str] = None


@router.get("/preferences", response_model=ApplicationPreferencesResponse)
async def get_application_preferences(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> ApplicationPreferencesResponse:
    """Return the current user's workflow preferences (with defaults if no row exists yet)."""
    try:
        user_id = get_user_id_from_token(current_user)

        result = await db.execute(
            select(UserWorkflowPreferences).where(
                UserWorkflowPreferences.user_id == user_id
            )
        )
        prefs_row = result.scalar_one_or_none()

        if prefs_row:
            return ApplicationPreferencesResponse(
                workflow_gate_threshold=prefs_row.workflow_gate_threshold,
                auto_generate_documents=prefs_row.auto_generate_documents,
                cover_letter_tone=prefs_row.cover_letter_tone,
                resume_length=prefs_row.resume_length,
                preferred_model=prefs_row.preferred_model,
            )

        # No row yet — return defaults without writing anything
        return ApplicationPreferencesResponse(**_PREFERENCE_DEFAULTS)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get application preferences: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to get application preferences")


@router.patch("/preferences", response_model=ApplicationPreferencesResponse)
async def update_application_preferences(
    request: ApplicationPreferencesRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
) -> ApplicationPreferencesResponse:
    """Partially update the user's workflow preferences.

    Creates the preferences row on first call (upsert pattern).
    Only provided fields are updated; omitted fields keep their current value.
    """
    try:
        user_id = get_user_id_from_token(current_user)

        result = await db.execute(
            select(UserWorkflowPreferences).where(
                UserWorkflowPreferences.user_id == user_id
            )
        )
        prefs_row = result.scalar_one_or_none()

        if prefs_row is None:
            # First time — create row with defaults, then apply the patch.
            # Wrap the INSERT in a savepoint so that a concurrent INSERT from
            # another request (race condition) causes an IntegrityError that we
            # can recover from with a re-SELECT instead of rolling back the
            # entire transaction.
            try:
                async with db.begin_nested():
                    prefs_row = UserWorkflowPreferences(
                        id=uuid.uuid4(),
                        user_id=user_id,
                        workflow_gate_threshold=_PREFERENCE_DEFAULTS["workflow_gate_threshold"],
                        auto_generate_documents=_PREFERENCE_DEFAULTS["auto_generate_documents"],
                        cover_letter_tone=_PREFERENCE_DEFAULTS["cover_letter_tone"],
                        resume_length=_PREFERENCE_DEFAULTS["resume_length"],
                        preferred_model=_PREFERENCE_DEFAULTS["preferred_model"],
                    )
                    db.add(prefs_row)
            except IntegrityError:
                # The savepoint context manager automatically rolled back the savepoint
                # on IntegrityError — the parent transaction is still valid.
                # Do NOT call db.rollback() here: that would roll back the entire
                # parent transaction, making all subsequent DB work in this request
                # fail with "transaction is already rolled back".
                result2 = await db.execute(
                    select(UserWorkflowPreferences).where(
                        UserWorkflowPreferences.user_id == user_id
                    )
                )
                prefs_row = result2.scalar_one()

        if request.workflow_gate_threshold is not None:
            prefs_row.workflow_gate_threshold = request.workflow_gate_threshold
        if request.auto_generate_documents is not None:
            prefs_row.auto_generate_documents = request.auto_generate_documents
        if request.cover_letter_tone is not None:
            tone = request.cover_letter_tone.lower()
            if tone not in _VALID_COVER_LETTER_TONES:
                raise validation_error(f"cover_letter_tone must be one of: {', '.join(_VALID_COVER_LETTER_TONES)}")
            prefs_row.cover_letter_tone = tone
        if request.resume_length is not None:
            length = request.resume_length.lower()
            if length not in _VALID_RESUME_LENGTHS:
                raise validation_error(f"resume_length must be one of: {', '.join(_VALID_RESUME_LENGTHS)}")
            prefs_row.resume_length = length
        if "preferred_model" in request.model_fields_set:
            if request.preferred_model is not None and request.preferred_model not in _VALID_MODELS:
                raise validation_error(f"preferred_model must be one of: {', '.join(sorted(_VALID_MODELS))}")
            prefs_row.preferred_model = request.preferred_model

        await db.commit()

        logger.info('Updated workflow preferences for %s: gate=%s auto_docs=%s tone=%s resume_length=%s model=%s', _log_user_email(current_user), sanitize_log_value(prefs_row.workflow_gate_threshold), sanitize_log_value(prefs_row.auto_generate_documents), sanitize_log_value(prefs_row.cover_letter_tone), sanitize_log_value(prefs_row.resume_length), sanitize_log_value(prefs_row.preferred_model))

        return ApplicationPreferencesResponse(
            workflow_gate_threshold=prefs_row.workflow_gate_threshold,
            auto_generate_documents=prefs_row.auto_generate_documents,
            cover_letter_tone=prefs_row.cover_letter_tone,
            resume_length=prefs_row.resume_length,
            preferred_model=prefs_row.preferred_model,
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to update application preferences: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to update application preferences")


# =============================================================================
# DATA EXPORT, DELETION, AND ACCOUNT MANAGEMENT ENDPOINTS
# =============================================================================


class DeleteAccountRequest(BaseModel):
    """
    Request model for account deletion — requires password confirmation.
    For Google-only accounts (no password), pass an empty string to confirm.
    """

    password: str = Field(..., max_length=128, description="Current password to confirm deletion. Pass empty string for Google-only accounts.")


class NotificationSettingsRequest(BaseModel):
    """Request model for notification settings update."""

    email_notifications: bool = Field(True, description="Enable email notifications")
    application_updates: bool = Field(True, description="Receive application status updates")
    weekly_summary: bool = Field(True, description="Receive weekly application summary")
    tips_and_suggestions: bool = Field(True, description="Receive tips and suggestions")


@router.get("/export")
async def export_user_data(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
):
    """
    Export all user data in JSON format for GDPR compliance (Right to Data Portability).
    
    Returns a JSON file containing:
    - Account information
    - Profile data
    - Job applications
    - Workflow sessions and results
    
    This endpoint supports the GDPR right to data portability.
    """
    from fastapi.responses import StreamingResponse
    from models.database import (
        User,
        UserProfile as UserProfileModel,
    )
    import io
    import json
    
    try:
        user_id = get_user_id_from_token(current_user)

        # Rate limit: 5 exports per hour (large DB read — prevent resource exhaustion)
        is_allowed, _remaining = await check_rate_limit(
            identifier=f"export_data:{user_id}",
            limit=5,
            window_seconds=3600,
        )
        if not is_allowed:
            raise rate_limit_error("Too many export requests. Please try again later.", retry_after=3600)

        # Get user data
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise not_found_error("User not found")

        # Get user profile
        result = await db.execute(
            select(UserProfileModel).where(UserProfileModel.user_id == user_id)
        )
        user_profile = result.scalar_one_or_none()

        # Get all job applications
        result = await db.execute(
            select(JobApplication).where(JobApplication.user_id == user_id)
        )
        applications = result.scalars().all()

        # Get all workflow sessions
        result = await db.execute(
            select(WorkflowSession).where(WorkflowSession.user_id == user_id)
        )
        workflow_sessions = result.scalars().all()

        # Compile export data
        export_data = {
            "export_info": {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "export_version": "1.0",
                "user_id": str(user_id),
            },
            "account": {
                "email": user.email,
                "full_name": user.full_name,
                "auth_method": user.auth_method,
                "profile_completed": user.profile_completed,
                "profile_completion_percentage": user.profile_completion_percentage,
                "has_google_linked": user.google_id is not None,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "updated_at": user.updated_at.isoformat() if user.updated_at else None,
                "last_login": user.last_login.isoformat() if user.last_login else None,
            },
            "profile": user_profile.to_dict() if user_profile else None,
            "applications": [app.to_dict() for app in applications],
            "workflow_sessions": [session.to_dict() for session in workflow_sessions],
            "statistics": {
                "total_applications": len(applications),
                "total_workflow_sessions": len(workflow_sessions),
            },
        }

        # Create JSON file
        json_content = json.dumps(export_data, indent=2, default=str)
        
        # Create streaming response
        buffer = io.BytesIO(json_content.encode('utf-8'))
        buffer.seek(0)
        
        filename = f"job-assistant-export-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
        
        masked_email = mask_email(str(user.email))
        logger.info('User data exported for: %s', sanitize_log_value(masked_email))
        
        return StreamingResponse(
            buffer,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": "application/json",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to export user data: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to export user data")


@router.delete("/delete-account")
async def delete_user_account(
    request_data: DeleteAccountRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
):
    """
    Permanently delete user account and all associated data (GDPR Right to Erasure).
    Requires password confirmation to prevent accidental or unauthorized deletion.

    This action:
    - Deletes the user account
    - Deletes all profile data
    - Deletes all job applications
    - Deletes all workflow sessions
    - Invalidates all cached data and active tokens

    THIS ACTION CANNOT BE UNDONE. Recommend users export their data first.
    """
    from models.database import (
        User,
        UserProfile as UserProfileModel,
        UserResumeAsset,
    )
    from api.auth import pwd_context, _bcrypt_safe

    try:
        user_id = get_user_id_from_token(current_user)
        masked_user_email = mask_email(str(current_user.get("email", "")))

        # Rate limit: 3 attempts per hour per user (destructive endpoint)
        is_allowed, _remaining = await check_rate_limit(
            identifier=f"delete_account:{user_id}",
            limit=3,
            window_seconds=3600,
        )
        if not is_allowed:
            raise rate_limit_error("Too many account deletion attempts. Please try again later.", retry_after=3600)

        # Confirm identity: verify the provided password before deleting
        user_check = await db.execute(select(User).where(User.id == user_id))
        user_obj = user_check.scalar_one_or_none()
        if not user_obj:
            raise not_found_error("User not found")
        if not user_obj.password_hash:
            # Google-only users have no password.  Accept an empty string as the
            # "confirmation" value so the frontend can still call this endpoint,
            # but require the request body to explicitly provide an empty string
            # (i.e., the caller must have passed a JSON body with `"password": ""`).
            # This prevents accidental deletion via misconfigured API clients.
            if request_data.password != "":
                raise validation_error(
                    "This account uses Google Sign-In and has no password. "
                    "Pass an empty string for the password field to confirm deletion."
                )
        elif not pwd_context.verify(_bcrypt_safe(request_data.password), user_obj.password_hash):
            raise validation_error("Incorrect password. Account deletion cancelled.")

        # Revoke all active tokens before deletion
        try:
            await invalidate_all_user_tokens(user_id)
            from utils.personal_access_tokens import revoke_all_user_pats

            await revoke_all_user_pats(db, user_id)
        except Exception as revoke_error:
            logger.warning(
                "Failed to revoke tokens during account deletion: %s",
                sanitize_log_value(str(revoke_error)),
            )

        # Use bulk DELETE statements instead of ORM-level per-object deletes.
        # All statements execute in the same implicit transaction; if any
        # statement raises, the session context manager rolls the whole thing back.
        # Count before deleting so we can report accurate numbers.
        app_count_result = await db.execute(
            select(func.count()).select_from(JobApplication).where(JobApplication.user_id == user_id)
        )
        application_count: int = app_count_result.scalar_one() or 0

        session_count_result = await db.execute(
            select(func.count()).select_from(WorkflowSession).where(WorkflowSession.user_id == user_id)
        )
        session_count: int = session_count_result.scalar_one() or 0

        profile_result = await db.execute(
            select(func.count()).select_from(UserProfileModel).where(UserProfileModel.user_id == user_id)
        )
        has_profile: bool = (profile_result.scalar_one() or 0) > 0

        resume_row_result = await db.execute(
            select(UserResumeAsset).where(UserResumeAsset.user_id == user_id)
        )
        resume_asset = resume_row_result.scalar_one_or_none()
        if resume_asset:
            delete_resume_file(settings.user_resume_storage_dir, resume_asset.storage_relative_path)

        # Bulk-delete in child-to-parent order to respect FK constraints
        await db.execute(sa_delete(JobApplication).where(JobApplication.user_id == user_id))
        await db.execute(sa_delete(WorkflowSession).where(WorkflowSession.user_id == user_id))
        await db.execute(sa_delete(UserWorkflowPreferences).where(UserWorkflowPreferences.user_id == user_id))
        await db.execute(sa_delete(UserProfileModel).where(UserProfileModel.user_id == user_id))
        await db.execute(sa_delete(User).where(User.id == user_id))

        await db.commit()

        # Invalidate all cached data for this user (best-effort, post-commit)
        try:
            await invalidate_user_profile(str(user_id))
            await invalidate_user_llm_cache(str(user_id))
        except Exception as cache_error:
            logger.warning(
                "Failed to invalidate cache during account deletion: %s",
                sanitize_log_value(str(cache_error)),
            )

        logger.info('Account deleted for user: %s - Deleted %s applications, %s workflow sessions', sanitize_log_value(masked_user_email), sanitize_log_value(application_count), sanitize_log_value(session_count))

        return {
            "message": "Account successfully deleted",
            "deleted": {
                "applications": application_count,
                "workflow_sessions": session_count,
                "profile": has_profile,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to delete user account: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to delete account. Please try again or contact support.")


class ClearDataRequest(BaseModel):
    """Confirmation payload required to clear all application data."""
    confirm: bool = Field(..., description="Must be true to confirm data deletion")


@router.delete("/clear-data")
async def clear_user_data(
    request_data: ClearDataRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
):
    """
    Clear all application data while keeping the account.

    Requires an explicit ``{"confirm": true}`` body to prevent accidental
    calls and is rate-limited to once per hour per user.

    This action:
    - Deletes all job applications
    - Deletes all workflow sessions
    - Keeps the user account and profile intact

    Use this to start fresh without losing your profile setup.
    """

    try:
        if not request_data.confirm:
            raise validation_error("Set 'confirm' to true to confirm data deletion.")

        user_id = get_user_id_from_token(current_user)
        masked_user_email = mask_email(str(current_user.get("email", "")))

        # Rate limit: at most once per hour to prevent accidental/abusive calls
        is_allowed, _remaining = await check_rate_limit(
            identifier=f"clear_data:{user_id}",
            limit=1,
            window_seconds=3600,
        )
        if not is_allowed:
            raise rate_limit_error(
                "Data has already been cleared recently. Please wait before clearing again.",
                retry_after=3600,
            )

        # Bulk deletes for efficiency and atomicity
        app_count_result = await db.execute(
            select(func.count()).select_from(JobApplication).where(JobApplication.user_id == user_id)
        )
        application_count: int = app_count_result.scalar_one() or 0

        session_count_result = await db.execute(
            select(func.count()).select_from(WorkflowSession).where(WorkflowSession.user_id == user_id)
        )
        session_count: int = session_count_result.scalar_one() or 0

        await db.execute(sa_delete(JobApplication).where(JobApplication.user_id == user_id))
        await db.execute(sa_delete(WorkflowSession).where(WorkflowSession.user_id == user_id))
        await db.commit()

        logger.info('Data cleared for user: %s - Deleted %s applications, %s workflow sessions', sanitize_log_value(masked_user_email), sanitize_log_value(application_count), sanitize_log_value(session_count))

        return {
            "message": "All application data has been cleared",
            "deleted": {
                "applications": application_count,
                "workflow_sessions": session_count,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to clear user data: %s", sanitize_log_value(str(e)), exc_info=True)
        raise internal_error("Failed to clear data. Please try again.")


@router.put("/notifications")
async def update_notification_settings(
    settings_data: NotificationSettingsRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
):
    """
    Update user notification preferences.

    Not yet implemented — notification settings persistence requires a dedicated
    database column or table that has not been created yet.
    Returns 501 until fully implemented.
    """
    raise not_implemented_error(
        "Notification settings persistence is not yet implemented. "
        "This endpoint will be available in a future release."
    )
