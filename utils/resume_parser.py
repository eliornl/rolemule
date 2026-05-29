"""
Resume Parser Utility - Extracts structured profile data from resumes using Gemini LLM.

This module provides functionality to:
1. Extract text from PDF, DOCX, and TXT resume files
2. Parse the extracted text using Gemini to get structured profile data
3. Return data compatible with the UserProfile schema
"""

import io
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

from utils.llm_client import get_gemini_client, user_facing_message_from_llm_exception
from utils.llm_parsing import parse_json_from_llm_response

# =============================================================================
# CONSTANTS
# =============================================================================

logger: logging.Logger = logging.getLogger(__name__)

# LLM Configuration
LLM_MAX_TOKENS: int = 16000  # Unified agent output cap
LLM_TEMPERATURE: float = 0.2  # Low temperature for accurate extraction

# File processing
PDF_EXTENSION: str = "pdf"
DOCX_EXTENSION: str = "docx"  # Note: .doc (legacy) not supported - requires different library
TXT_EXTENSION: str = "txt"
SUPPORTED_EXTENSIONS: List[str] = [PDF_EXTENSION, DOCX_EXTENSION, TXT_EXTENSION]
MAX_FILE_SIZE_MB: int = 10
MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024

# =============================================================================
# SYSTEM CONTEXT AND PROMPT
# =============================================================================

SYSTEM_CONTEXT: str = """You are an expert resume parser with 15+ years of experience in HR and recruiting.

## YOUR EXPERTISE:

**Resume Analysis:**
- You can parse any resume format (chronological, functional, combination)
- You understand industry-specific terminology across all sectors
- You recognize implicit information from context
- You accurately extract dates, durations, and timelines

**Data Extraction:**
- You extract structured data accurately from unstructured text
- You handle missing information gracefully (use null, not guesses)
- You normalize data formats (dates, locations, skills)
- You identify the most relevant and recent information

## YOUR PRINCIPLES:
- Extract EXACTLY what's written - don't embellish or assume
- Be PRECISE with dates - if only year is given, use that
- Normalize skills to their common names (e.g., "JS" → "JavaScript")
- When information is missing, use null rather than guessing
- Preserve the original meaning and context of descriptions
- For work experience descriptions: preserve all content from the resume faithfully — do not summarize, shorten, or omit any bullet points or details
- Only extract a work experience entry if it has BOTH a real company name AND a job title AND dates. A brief one-line mention or footnote (e.g. "Previously worked as a chef...") is NOT a work entry — skip it
- PDF text extraction sometimes wraps long lines mid-sentence; join continuation lines so each bullet is a complete sentence"""

RESUME_PARSE_PROMPT: str = """Analyze this resume and extract structured profile information.

## RESUME TEXT:
{resume_text}

## EXTRACTION INSTRUCTIONS:

1. **Personal Information**: Extract name, email, phone, location (city, state, country)
2. **Professional Summary**: Extract or synthesize a brief professional summary
3. **Work Experience**: Extract all jobs with company, title, dates, and key responsibilities
4. **Skills**: Extract all technical and soft skills mentioned
5. **Education**: Extract degrees, institutions, and graduation dates

## OUTPUT FORMAT (JSON):

Return ONLY this JSON structure. No explanations, no markdown, just the JSON:

{{
    "full_name": "<full name or null if not found>",
    "email": "<email address or null>",
    "phone": "<phone number or null>",
    "linkedin_url": "<https URL or null>",
    "github_url": "<https URL or null>",
    "portfolio_url": "<https URL or null>",
    "city": "<city or null>",
    "state": "<state/province or null>",
    "country": "<country or null>",
    "professional_title": "<current or most recent job title>",
    "years_experience": <integer, sum of all work entry durations in months divided by 12, rounded to nearest integer. Do NOT use the calendar span from first job to today — add up each individual role's months separately then divide>,
    "is_student": <true if currently a student, false otherwise>,
    "summary": "<professional summary, 2-4 sentences. If not in resume, synthesize from experience>",
    
    "work_experience": [
        {{
            "company": "<company name>",
            "title": "<job title>",
            "start_date": "<YYYY-MM format or YYYY>",
            "end_date": "<YYYY-MM format, YYYY, or 'present'>",
            "is_current": <true or false>,
            "description": "<Follow this exact format — overview sentence(s) first (no bullet prefix), then each bullet on its own line with its original marker. Example:\nBuilt and scaled the core payments infrastructure serving 10M+ users.\n• Designed event-driven architecture using Kafka and PostgreSQL, reducing latency by 40%.\n• Led a team of 6 engineers across 3 time zones.\n• Migrated legacy monolith to microservices with zero downtime.\nPreserve all content faithfully from the resume.>"
        }}
    ],
    
    "skills": [
        "<skill 1>",
        "<skill 2>"
    ],
    
    "education": [
        {{
            "institution": "<school/university name>",
            "degree": "<degree type, e.g., Bachelor's, Master's>",
            "field": "<field of study>",
            "graduation_date": "<YYYY or YYYY-MM>",
            "gpa": "<GPA if mentioned, null otherwise>"
        }}
    ],
    
    "certifications": [
        "<certification 1>",
        "<certification 2>"
    ],
    
    "languages": [
        {{
            "language": "<language name>",
            "proficiency": "<Native/Fluent/Professional/Conversational>"
        }}
    ],
    
    "parsing_confidence": "<HIGH | MEDIUM | LOW>",
    "parsing_notes": "<any issues or uncertainties encountered during parsing>"
}}

## IMPORTANT RULES:
1. Return ONLY the JSON object - no other text
2. Use null for missing fields, not empty strings or guesses
3. List work experience from most recent to oldest
4. Normalize skill names to their common forms
5. Calculate years_experience by summing each role's duration in months (individually), then dividing the total by 12 and rounding to nearest integer. Example: role A = 10 months, role B = 33 months, role C = 8 months → total 51 months → 51/12 = 4.25 → 4 years
6. Set is_student to true only if currently enrolled in a degree program
7. Only extract work experience entries that are presented as proper jobs with a company name, job title, AND start date. Do NOT create entries from brief summary sentences or footnotes that mention past roles in passing (e.g. "Prior to X, worked as Y..." or "Previously co-founded...") — these are intentional summaries, not work entries
8. For descriptions: overview sentence(s) first (no bullet prefix), then each bullet on its own line with its original marker — exactly as shown in the example inside the JSON template. Preserve all content faithfully"""


# =============================================================================
# TEXT EXTRACTION FUNCTIONS
# =============================================================================


def extract_text_from_pdf(content: bytes) -> str:
    """
    Extract text from PDF file bytes using PyMuPDF.

    Args:
        content: PDF file content as bytes

    Returns:
        Extracted text content

    Raises:
        ValueError: If PDF processing fails
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ValueError(
            "PDF processing requires PyMuPDF. Install with: pip install pymupdf"
        )

    try:
        doc = fitz.open(stream=content, filetype="pdf")
        pages_text = []

        for page in doc:
            text = page.get_text()
            pages_text.append(text)

        doc.close()
        return "\n\n".join(pages_text)

    except Exception as e:
        raise ValueError(f"Failed to extract PDF content: {str(e)}")


def extract_text_from_docx(content: bytes) -> str:
    """
    Extract text from DOCX file bytes using docx2txt.

    Args:
        content: DOCX file content as bytes

    Returns:
        Extracted text content

    Raises:
        ValueError: If DOCX processing fails
    """
    try:
        import docx2txt
    except ImportError:
        raise ValueError(
            "DOCX processing requires docx2txt. Install with: pip install docx2txt"
        )

    try:
        file_like = io.BytesIO(content)
        text_content = docx2txt.process(file_like)
        return text_content.strip() if text_content else ""

    except Exception as e:
        raise ValueError(f"Failed to extract DOCX content: {str(e)}")


def extract_text_from_file(
    content: bytes, filename: str
) -> str:
    """
    Extract text from a file based on its extension.

    Args:
        content: File content as bytes
        filename: Original filename (used to determine format)

    Returns:
        Extracted text content

    Raises:
        ValueError: If file format is unsupported or extraction fails
    """
    if not filename:
        raise ValueError("Filename is required to determine file format")

    # Get file extension
    filename_lower = filename.lower()
    extension = filename_lower.split(".")[-1] if "." in filename_lower else ""

    # Validate extension
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file format: .{extension}. "
            f"Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    # Validate file size
    if len(content) == 0:
        raise ValueError("Uploaded file is empty")
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB")

    # Extract text based on format
    if extension == PDF_EXTENSION:
        return extract_text_from_pdf(content)
    elif extension == DOCX_EXTENSION:
        return extract_text_from_docx(content)
    elif extension == TXT_EXTENSION:
        # Try UTF-8 first, then fallback encodings
        for encoding in ["utf-8", "latin-1", "cp1252", "iso-8859-1"]:
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("Unable to decode text file. Please use UTF-8 encoding.")
    else:
        raise ValueError(f"Unsupported file format: .{extension}")


# =============================================================================
# RESUME PARSING
# =============================================================================


async def parse_resume(resume_text: str, user_api_key: str | None = None) -> Dict[str, Any]:
    """
    Parse resume text using Gemini LLM to extract structured profile data.

    Args:
        resume_text: Extracted text from resume file
        user_api_key: Optional BYOK key. When provided, used instead of the
                      server-side key so self-hosted users can parse resumes
                      with their own Gemini API key.

    Returns:
        Dictionary containing parsed profile data matching UserProfile schema

    Raises:
        ValueError: If parsing fails or LLM returns invalid response
    """
    if not resume_text or len(resume_text.strip()) < 50:
        raise ValueError(
            "Resume text is too short. Please provide a complete resume."
        )

    start_time = datetime.now(timezone.utc)

    try:
        gemini_client = await get_gemini_client()

        prompt = RESUME_PARSE_PROMPT.format(
            resume_text=resume_text[:15000]
        )

        response = await gemini_client.generate(
            prompt=prompt,
            system=SYSTEM_CONTEXT,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
            user_api_key=user_api_key,
        )

        if response.get("filtered"):
            logger.warning("Resume parsing was filtered by safety settings")
            return _create_filtered_result(response.get("response", ""))

        response_text = response.get("response", "")
        parsed_data = parse_json_from_llm_response(response_text)

        if not parsed_data:
            logger.error("Failed to parse LLM response as JSON")
            return _create_parse_error_result(response_text)

        processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
        parsed_data["processing_time"] = processing_time
        parsed_data["parse_method"] = "GEMINI_LLM"

        cleaned_data = _clean_parsed_data(parsed_data)

        logger.info(
            f"Resume parsed successfully in {processing_time:.2f}s - "
            f"Name: {cleaned_data.get('full_name', 'Unknown')}, "
            f"Skills: {len(cleaned_data.get('skills', []))}, "
            f"Experience: {len(cleaned_data.get('work_experience', []))} jobs"
        )

        return cleaned_data

    except Exception as e:
        logger.error(f"Resume parsing failed: {str(e)}", exc_info=True)
        friendly = user_facing_message_from_llm_exception(e)
        # Quota / rate-limit: use plain-language message only (no "Failed to parse" prefix).
        if friendly != str(e):
            raise ValueError(friendly)
        raise ValueError(f"Failed to parse resume: {friendly}")


async def parse_resume_from_file(
    content: bytes, filename: str, user_api_key: str | None = None
) -> Dict[str, Any]:
    """
    Complete resume parsing: extract text from file and parse with LLM.

    Args:
        content: File content as bytes
        filename: Original filename
        user_api_key: Optional BYOK key forwarded to the LLM call.

    Returns:
        Dictionary containing parsed profile data

    Raises:
        ValueError: If extraction or parsing fails
    """
    # Step 1: Extract text
    resume_text = extract_text_from_file(content, filename)

    if not resume_text or len(resume_text.strip()) < 50:
        raise ValueError(
            "Could not extract sufficient text from the resume. "
            "Please ensure the file is not corrupted or password-protected."
        )

    # Step 2: Parse with LLM
    return await parse_resume(resume_text, user_api_key=user_api_key)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _clean_parsed_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clean and validate parsed resume data.

    Args:
        data: Raw parsed data from LLM

    Returns:
        Cleaned and validated data
    """
    cleaned = {}

    # String fields - ensure they're strings or None
    string_fields = [
        "full_name", "email", "phone", "linkedin_url", "github_url", "portfolio_url",
        "city", "state", "country",
        "professional_title", "summary", "parsing_confidence", "parsing_notes"
    ]
    for field in string_fields:
        value = data.get(field)
        if value and isinstance(value, str) and value.strip():
            cleaned[field] = value.strip()
        else:
            cleaned[field] = None

    # Integer fields
    years_exp = data.get("years_experience")
    if isinstance(years_exp, (int, float)):
        cleaned["years_experience"] = int(years_exp)
    elif isinstance(years_exp, str) and years_exp.isdigit():
        cleaned["years_experience"] = int(years_exp)
    else:
        cleaned["years_experience"] = 0

    # Boolean fields
    cleaned["is_student"] = bool(data.get("is_student", False))

    # List fields - ensure they're lists
    cleaned["skills"] = _clean_list(data.get("skills", []))
    cleaned["certifications"] = _clean_list(data.get("certifications", []))

    # Work experience - validate structure
    work_exp = data.get("work_experience", [])
    if isinstance(work_exp, list):
        cleaned["work_experience"] = [
            _clean_work_experience(exp)
            for exp in work_exp
            if isinstance(exp, dict)
        ]
    else:
        cleaned["work_experience"] = []

    # Education - validate structure
    education = data.get("education", [])
    if isinstance(education, list):
        cleaned["education"] = [
            _clean_education(edu)
            for edu in education
            if isinstance(edu, dict)
        ]
    else:
        cleaned["education"] = []

    # Languages - validate structure
    languages = data.get("languages", [])
    if isinstance(languages, list):
        cleaned["languages"] = [
            _clean_language(lang)
            for lang in languages
            if isinstance(lang, dict)
        ]
    else:
        cleaned["languages"] = []

    # Preserve metadata
    cleaned["processing_time"] = data.get("processing_time", 0)
    cleaned["parse_method"] = data.get("parse_method", "GEMINI_LLM")

    return cleaned


def _clean_list(items: Any) -> List[str]:
    """Clean a list of strings, removing empty/invalid items."""
    if not isinstance(items, list):
        return []
    return [
        str(item).strip()
        for item in items
        if item and isinstance(item, (str, int, float)) and str(item).strip()
    ]


def _clean_work_experience(exp: Dict[str, Any]) -> Dict[str, Any]:
    """Clean and validate a work experience entry."""
    return {
        "company": str(exp.get("company", "")).strip() or None,
        "title": str(exp.get("title", "")).strip() or None,
        "start_date": str(exp.get("start_date", "")).strip() or None,
        "end_date": str(exp.get("end_date", "")).strip() or None,
        "is_current": bool(exp.get("is_current", False)),
        "description": str(exp.get("description", "")).strip() or None,
    }


def _clean_education(edu: Dict[str, Any]) -> Dict[str, Any]:
    """Clean and validate an education entry."""
    field_val = edu.get("field_of_study") or edu.get("field")
    field_clean = str(field_val).strip() if field_val else None
    return {
        "institution": str(edu.get("institution", "")).strip() or None,
        "degree": str(edu.get("degree", "")).strip() or None,
        "field": field_clean,
        "field_of_study": field_clean,
        "graduation_date": str(edu.get("graduation_date", "")).strip() or None,
        "gpa": str(edu.get("gpa", "")).strip() if edu.get("gpa") else None,
    }


def _clean_language(lang: Dict[str, Any]) -> Dict[str, Any]:
    """Clean and validate a language entry."""
    return {
        "language": str(lang.get("language", "")).strip() or None,
        "proficiency": str(lang.get("proficiency", "")).strip() or None,
    }


def _create_filtered_result(filter_message: str) -> Dict[str, Any]:
    """Create a result when content was filtered."""
    return {
        "full_name": None,
        "email": None,
        "phone": None,
        "city": None,
        "state": None,
        "country": None,
        "professional_title": None,
        "years_experience": 0,
        "is_student": False,
        "summary": None,
        "work_experience": [],
        "skills": [],
        "education": [],
        "certifications": [],
        "languages": [],
        "parsing_confidence": "LOW",
        "parsing_notes": f"Content was filtered: {filter_message}",
        "filtered": True,
        "parse_method": "FILTERED",
    }


def _create_parse_error_result(raw_response: str) -> Dict[str, Any]:
    """Create a result when JSON parsing failed."""
    return {
        "full_name": None,
        "email": None,
        "phone": None,
        "city": None,
        "state": None,
        "country": None,
        "professional_title": None,
        "years_experience": 0,
        "is_student": False,
        "summary": None,
        "work_experience": [],
        "skills": [],
        "education": [],
        "certifications": [],
        "languages": [],
        "parsing_confidence": "LOW",
        "parsing_notes": "Failed to parse LLM response as JSON",
        "parse_error": True,
        "raw_response": raw_response[:2000],  # Keep some for debugging
        "parse_method": "PARSE_ERROR",
    }

