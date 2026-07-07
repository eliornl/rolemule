"""Shared Pydantic models for Chrome extension autofill endpoints."""

from __future__ import annotations

from typing import Dict, List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

# Limits shared by autofill map request validation
_MAX_FIELDS: int = 80
_MAX_LABEL_CHARS: int = 600
_MAX_OPTION_TEXT: int = 200
_MAX_OPTIONS_PER_SELECT: int = 40
_MAX_PAGE_URL_LEN: int = 2048
_MAX_EXTRAS_KEYS: int = 16
_MAX_EXTRA_KEY_LEN: int = 64
_MAX_EXTRA_VALUE_LEN: int = 500


def _is_http_or_https_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


class AutofillSelectOption(BaseModel):
    """One <option> for a select control."""

    value: str = Field(default="", max_length=500)
    text: str = Field(default="", max_length=_MAX_OPTION_TEXT)


class AutofillFieldIn(BaseModel):
    """Serialized form control from the extension (main document only)."""

    field_uid: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^\d+$",
        description="Stable id from the extension serializer (digits only)",
    )
    tag: str = Field(..., max_length=24)
    input_type: Optional[str] = Field(None, max_length=32)
    name_attr: Optional[str] = Field(None, max_length=240)
    id_attr: Optional[str] = Field(None, max_length=240)
    label_text: str = Field(default="", max_length=_MAX_LABEL_CHARS)
    placeholder: Optional[str] = Field(None, max_length=500)
    aria_label: Optional[str] = Field(None, max_length=500)
    required: bool = False
    max_length: Optional[int] = Field(None, ge=0, le=1_000_000)
    options: Optional[List[AutofillSelectOption]] = Field(None, max_length=_MAX_OPTIONS_PER_SELECT)
    duplicate_label_index: int = Field(
        default=0,
        ge=0,
        le=20,
        description="0-based index when the same label appears on multiple fields (e.g. education rows)",
    )


class AutofillMapRequest(BaseModel):
    """Request body for POST /extension/autofill/map."""

    fields: List[AutofillFieldIn] = Field(..., min_length=1)
    page_url: str = Field(..., min_length=1, max_length=_MAX_PAGE_URL_LEN)
    extras: Optional[Dict[str, str]] = Field(
        default=None,
        description="Optional key/value hints stored in the extension (phone, URLs, etc.)",
    )

    @field_validator("page_url")
    @classmethod
    def _page_url_scheme(cls, v: str) -> str:
        t = v.strip()
        if not _is_http_or_https_url(t):
            raise ValueError("page_url must start with http:// or https://")
        return t

    @model_validator(mode="after")
    def _aggregate_field_rules(self) -> AutofillMapRequest:
        if len(self.fields) > _MAX_FIELDS:
            raise ValueError(f"At most {_MAX_FIELDS} fields allowed")
        uids = [f.field_uid for f in self.fields]
        if len(uids) != len(set(uids)):
            raise ValueError("Each field_uid must be unique")
        if self.extras is not None:
            if len(self.extras) > _MAX_EXTRAS_KEYS:
                raise ValueError(f"At most {_MAX_EXTRAS_KEYS} extras keys allowed")
            for k, val in self.extras.items():
                if len(k) > _MAX_EXTRA_KEY_LEN:
                    raise ValueError("extras key too long")
                if val is not None and len(val) > _MAX_EXTRA_VALUE_LEN:
                    raise ValueError("extras value too long")
        return self


class AutofillAssignmentOut(BaseModel):
    """One suggested value for a field."""

    field_uid: str
    value: str
    label_text: str = Field(default="", description="Echo from request for preview UI")
    duplicate_label_index: int = Field(
        default=0,
        ge=0,
        le=20,
        description="Which repeated label occurrence (0=first Degree row, 1=second, etc.)",
    )


class AutofillMapResponse(BaseModel):
    """LLM mapping result returned to the extension."""

    assignments: List[AutofillAssignmentOut] = Field(default_factory=list)
    skipped: List[Dict[str, str]] = Field(default_factory=list)
    warnings: List[str] = Field(
        default_factory=list,
        description="UX hints (e.g. same-document MVP, no iframes)",
    )
