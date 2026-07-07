"""
Security utilities for the ApplyPilot.
Provides input sanitization, XSS prevention, and security helpers.
"""

import html
import re
import logging
from typing import Any, Dict, List, Optional

try:
    import bleach
    _BLEACH_AVAILABLE = True
except ImportError:  # pragma: no cover
    _BLEACH_AVAILABLE = False

logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS
# =============================================================================

# Maximum lengths for various fields to prevent DoS
MAX_TEXT_LENGTH = 100000  # 100KB for large text fields
MAX_FIELD_LENGTH = 10000  # 10KB for regular fields
MAX_NAME_LENGTH = 500  # Names, titles, etc.

# Patterns for potentially dangerous content
SCRIPT_PATTERN = re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
EVENT_HANDLER_PATTERN = re.compile(r"\s+on\w+\s*=", re.IGNORECASE)
JAVASCRIPT_URL_PATTERN = re.compile(r"javascript:", re.IGNORECASE)
DATA_URL_PATTERN = re.compile(r"data:\s*text/html", re.IGNORECASE)
STYLE_EXPRESSION_PATTERN = re.compile(r"expression\s*\(", re.IGNORECASE)

# HTML tags that are generally safe (for basic formatting)
SAFE_TAGS = {
    "p", "br", "b", "i", "u", "strong", "em", "ul", "ol", "li",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "code", "pre"
}


# =============================================================================
# XSS SANITIZATION
# =============================================================================


def sanitize_html(content: str, allow_basic_formatting: bool = False) -> str:
    """
    Sanitize HTML content to prevent XSS attacks.

    Args:
        content: Input string that may contain HTML
        allow_basic_formatting: If True, allow safe formatting tags

    Returns:
        Sanitized string safe for display
    """
    if not content:
        return ""

    if not isinstance(content, str):
        content = str(content)

    # Truncate extremely long content
    if len(content) > MAX_TEXT_LENGTH:
        content = content[:MAX_TEXT_LENGTH]
        logger.warning(f"Content truncated from {len(content)} to {MAX_TEXT_LENGTH} chars")

    # Remove script tags and their content
    content = SCRIPT_PATTERN.sub("", content)

    # Remove event handlers (onclick, onmouseover, etc.)
    content = EVENT_HANDLER_PATTERN.sub(" ", content)

    # Remove javascript: URLs
    content = JAVASCRIPT_URL_PATTERN.sub("", content)

    # Remove data: URLs that could contain HTML
    content = DATA_URL_PATTERN.sub("", content)

    # Remove CSS expressions
    content = STYLE_EXPRESSION_PATTERN.sub("", content)

    if allow_basic_formatting:
        if _BLEACH_AVAILABLE:
            # bleach.clean strips all tags not in the allowlist and escapes their content,
            # which is far more robust than the regex approach.
            content = bleach.clean(content, tags=list(SAFE_TAGS), attributes={}, strip=True)
        else:
            # Fallback: escape all HTML when bleach is not installed
            logger.warning(
                "bleach is not installed; falling back to full HTML escaping. "
                "Install with: pip install bleach"
            )
            content = html.escape(content)
    else:
        # Escape all HTML entities
        content = html.escape(content)

    return content


def sanitize_text(text: str, max_length: int = MAX_FIELD_LENGTH) -> str:
    """
    Sanitize plain text input.

    Args:
        text: Input text
        max_length: Maximum allowed length

    Returns:
        Sanitized text
    """
    if not text:
        return ""

    if not isinstance(text, str):
        text = str(text)

    # Truncate if too long
    if len(text) > max_length:
        text = text[:max_length]

    # Remove null bytes and other control characters (except newlines, tabs)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def sanitize_name(name: str) -> str:
    """
    Sanitize a name field (person name, company name, etc.).

    Args:
        name: Input name

    Returns:
        Sanitized name
    """
    if not name:
        return ""

    # Basic text sanitization with shorter max length
    name = sanitize_text(name, MAX_NAME_LENGTH)

    # HTML escape
    name = html.escape(name)

    return name


# =============================================================================
# DICT/OBJECT SANITIZATION
# =============================================================================


def sanitize_dict(
    data: Dict[str, Any],
    html_fields: Optional[List[str]] = None,
    skip_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Recursively sanitize all string values in a dictionary.

    Args:
        data: Dictionary to sanitize
        html_fields: Fields that may contain HTML (will be sanitized but formatting preserved)
        skip_fields: Fields to skip sanitization (e.g., IDs, timestamps)

    Returns:
        Sanitized dictionary
    """
    if not data:
        return data

    html_fields = set(html_fields or [])
    skip_fields = set(skip_fields or ["id", "user_id", "session_id", "created_at", "updated_at"])

    return _sanitize_value(data, html_fields, skip_fields)


def _sanitize_value(
    value: Any,
    html_fields: set,
    skip_fields: set,
    current_key: str = "",
) -> Any:
    """Recursively sanitize a value."""
    if isinstance(value, dict):
        return {
            k: _sanitize_value(v, html_fields, skip_fields, k)
            for k, v in value.items()
        }
    elif isinstance(value, list):
        return [
            _sanitize_value(item, html_fields, skip_fields, current_key)
            for item in value
        ]
    elif isinstance(value, str):
        if current_key in skip_fields:
            return value
        elif current_key in html_fields:
            return sanitize_html(value, allow_basic_formatting=True)
        else:
            return sanitize_html(value, allow_basic_formatting=False)
    else:
        return value


# =============================================================================
# LLM OUTPUT SANITIZATION
# =============================================================================


def sanitize_llm_output(content):
    """
    Sanitize LLM-generated content before storing or displaying.

    Handles str, dict, and list inputs — JSONB fields from the DB are dicts/lists
    and must be sanitized recursively rather than as raw strings.

    Args:
        content: Raw LLM output (str, dict, or list)

    Returns:
        Sanitized content safe for storage and display
    """
    if isinstance(content, dict):
        return {k: sanitize_llm_output(v) for k, v in content.items()}
    if isinstance(content, list):
        return [sanitize_llm_output(item) for item in content]
    if not isinstance(content, str):
        return content
    if not content:
        return ""

    # Remove any script tags the LLM might have generated
    content = SCRIPT_PATTERN.sub("", content)

    # Remove event handlers
    content = EVENT_HANDLER_PATTERN.sub(" ", content)

    # Remove javascript: URLs
    content = JAVASCRIPT_URL_PATTERN.sub("", content)

    # Keep markdown formatting but escape HTML in non-code sections
    # This preserves code blocks while sanitizing regular content

    # Split by code blocks to preserve them
    parts = re.split(r"(```[\s\S]*?```|`[^`]+`)", content)

    sanitized_parts = []
    for i, part in enumerate(parts):
        if part.startswith("```") or part.startswith("`"):
            # Code block - keep as is but escape any actual HTML
            sanitized_parts.append(part)
        else:
            # Regular content - escape HTML entities
            # But preserve markdown symbols
            sanitized = html.escape(part)
            # Unescape markdown symbols that were escaped
            sanitized = sanitized.replace("&gt;", ">")  # For blockquotes
            sanitized = sanitized.replace("\\*", "*")  # For emphasis
            sanitized_parts.append(sanitized)

    return "".join(sanitized_parts)


def sanitize_job_analysis(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize job analysis results from LLM.

    Args:
        analysis: Raw job analysis dictionary

    Returns:
        Sanitized analysis
    """
    # Fields that may contain longer text/HTML
    html_fields = [
        "responsibilities",
        "benefits",
        "team_info",
        "summary",
    ]

    # Fields to skip (IDs, scores, etc.)
    skip_fields = [
        "source",
        "processing_time",
        "from_cache",
        "years_experience_required",
        "salary_range",
        "education_requirements",
    ]

    return sanitize_dict(analysis, html_fields=html_fields, skip_fields=skip_fields)


def sanitize_cover_letter(cover_letter: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize cover letter results from LLM.

    Args:
        cover_letter: Raw cover letter dictionary

    Returns:
        Sanitized cover letter
    """
    if not cover_letter:
        return cover_letter

    # Sanitize the main content
    if "content" in cover_letter:
        cover_letter["content"] = sanitize_llm_output(cover_letter["content"])

    if "letter" in cover_letter:
        cover_letter["letter"] = sanitize_llm_output(cover_letter["letter"])

    if "body" in cover_letter:
        cover_letter["body"] = sanitize_llm_output(cover_letter["body"])

    return cover_letter


def sanitize_resume_recommendations(recommendations: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize resume recommendations from LLM.

    Args:
        recommendations: Raw recommendations dictionary

    Returns:
        Sanitized recommendations
    """
    if not recommendations:
        return recommendations

    # Fields that contain recommendation text
    text_fields = [
        "summary_recommendation",
        "experience_recommendations",
        "skills_recommendations",
        "education_recommendations",
        "overall_feedback",
    ]

    for field in text_fields:
        if field in recommendations:
            if isinstance(recommendations[field], str):
                recommendations[field] = sanitize_llm_output(recommendations[field])
            elif isinstance(recommendations[field], list):
                recommendations[field] = [
                    sanitize_llm_output(item) if isinstance(item, str) else item
                    for item in recommendations[field]
                ]

    return recommendations

