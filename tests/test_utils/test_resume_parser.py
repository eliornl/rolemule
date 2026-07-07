"""Tests for utils/resume_parser.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.resume_parser import (
    SUPPORTED_EXTENSIONS,
    _clean_education,
    _clean_list,
    _clean_parsed_data,
    _clean_work_experience,
    _create_filtered_result,
    _create_parse_error_result,
    extract_text_from_docx,
    extract_text_from_file,
    extract_text_from_pdf,
    parse_resume,
    parse_resume_from_file,
)


def test_extract_text_from_file_unsupported() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        extract_text_from_file(b"data", "file.exe")


def test_extract_text_from_file_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        extract_text_from_file(b"", "resume.txt")


def test_extract_text_from_file_too_large() -> None:
    big = b"x" * (11 * 1024 * 1024)
    with pytest.raises(ValueError, match="too large"):
        extract_text_from_file(big, "resume.txt")


def test_extract_text_from_file_txt_utf8() -> None:
    text = extract_text_from_file(b"Hello resume content here", "cv.txt")
    assert "Hello" in text


def test_extract_text_from_file_no_filename() -> None:
    with pytest.raises(ValueError, match="Filename is required"):
        extract_text_from_file(b"x", "")


def test_extract_text_from_pdf_import_error() -> None:
    with patch.dict("sys.modules", {"fitz": None}):
        with pytest.raises(ValueError, match="PyMuPDF"):
            extract_text_from_pdf(b"%PDF")


def test_extract_text_from_docx_import_error() -> None:
    with patch.dict("sys.modules", {"docx2txt": None}):
        with pytest.raises(ValueError, match="docx2txt"):
            extract_text_from_docx(b"PK")


def test_clean_helpers() -> None:
    assert _clean_list([" a ", "", 3]) == ["a", "3"]
    assert _clean_work_experience({"company": " Acme ", "title": "Eng"})["company"] == "Acme"
    edu = _clean_education({"institution": "U", "field": "CS", "gpa": 3.5})
    assert edu["field_of_study"] == "CS"


def test_clean_parsed_data_structure() -> None:
    raw = {
        "full_name": " Jane ",
        "years_experience": "5",
        "skills": ["Python"],
        "work_experience": [{"company": "A", "title": "B"}],
        "education": [{"institution": "U", "degree": "BS"}],
        "languages": [{"language": "English", "proficiency": "Native"}],
    }
    cleaned = _clean_parsed_data(raw)
    assert cleaned["full_name"] == "Jane"
    assert cleaned["years_experience"] == 5
    assert len(cleaned["work_experience"]) == 1


def test_create_filtered_and_parse_error_results() -> None:
    filtered = _create_filtered_result("blocked")
    assert filtered["filtered"] is True
    err = _create_parse_error_result('{"bad json')
    assert err["parse_error"] is True


@pytest.mark.asyncio
async def test_parse_resume_too_short() -> None:
    with pytest.raises(ValueError, match="too short"):
        await parse_resume("short")


@pytest.mark.asyncio
async def test_parse_resume_success(monkeypatch) -> None:
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(
        return_value={
            "response": '{"full_name": "Jane Doe", "skills": ["Python"], "work_experience": [], "education": []}',
        }
    )
    monkeypatch.setattr("utils.resume_parser.get_gemini_client", AsyncMock(return_value=mock_client))
    result = await parse_resume("x" * 80)
    assert result["full_name"] == "Jane Doe"


@pytest.mark.asyncio
async def test_parse_resume_filtered(monkeypatch) -> None:
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(return_value={"filtered": True, "response": "blocked"})
    monkeypatch.setattr("utils.resume_parser.get_gemini_client", AsyncMock(return_value=mock_client))
    result = await parse_resume("x" * 80)
    assert result.get("filtered") is True


@pytest.mark.asyncio
async def test_parse_resume_json_parse_failure(monkeypatch) -> None:
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(return_value={"response": "not json at all"})
    monkeypatch.setattr("utils.resume_parser.get_gemini_client", AsyncMock(return_value=mock_client))
    result = await parse_resume("x" * 80)
    assert result.get("parse_error") is True


@pytest.mark.asyncio
async def test_parse_resume_from_file_txt(monkeypatch) -> None:
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(
        return_value={"response": '{"full_name": "Bob", "skills": [], "work_experience": [], "education": []}'}
    )
    monkeypatch.setattr("utils.resume_parser.get_gemini_client", AsyncMock(return_value=mock_client))
    content = ("Professional summary " * 10).encode()
    result = await parse_resume_from_file(content, "resume.txt")
    assert result["full_name"] == "Bob"


def test_supported_extensions() -> None:
    assert ".pdf" in SUPPORTED_EXTENSIONS or "pdf" in SUPPORTED_EXTENSIONS


def test_extract_text_from_pdf_success() -> None:
    mock_doc = MagicMock()
    mock_page = MagicMock()
    mock_page.get_text.return_value = "Page one text"
    mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
    mock_fitz = MagicMock()
    mock_fitz.open.return_value = mock_doc

    with patch.dict("sys.modules", {"fitz": mock_fitz}):
        text = extract_text_from_pdf(b"%PDF-1.4 fake")
    assert "Page one text" in text
    mock_doc.close.assert_called_once()


def test_extract_text_from_pdf_processing_error() -> None:
    mock_fitz = MagicMock()
    mock_fitz.open.side_effect = RuntimeError("corrupt pdf")
    with patch.dict("sys.modules", {"fitz": mock_fitz}):
        with pytest.raises(ValueError, match="Failed to extract PDF"):
            extract_text_from_pdf(b"%PDF bad")


def test_extract_text_from_docx_success() -> None:
    mock_docx2txt = MagicMock()
    mock_docx2txt.process.return_value = "  Resume body  "
    with patch.dict("sys.modules", {"docx2txt": mock_docx2txt}):
        assert extract_text_from_docx(b"PK\x03\x04") == "Resume body"


def test_extract_text_from_docx_processing_error() -> None:
    mock_docx2txt = MagicMock()
    mock_docx2txt.process.side_effect = RuntimeError("bad docx")
    with patch.dict("sys.modules", {"docx2txt": mock_docx2txt}):
        with pytest.raises(ValueError, match="Failed to extract DOCX"):
            extract_text_from_docx(b"PK\x03\x04")


def test_extract_text_from_file_latin1_fallback() -> None:
    content = "Résumé with accents".encode("latin-1")
    text = extract_text_from_file(content, "resume.txt")
    assert "sum" in text


def test_clean_parsed_data_non_list_work_and_education() -> None:
    raw = {
        "full_name": "Jane",
        "years_experience": "7",
        "work_experience": "not-a-list",
        "education": 123,
        "skills": ["Go"],
        "languages": "English only",
    }
    cleaned = _clean_parsed_data(raw)
    assert cleaned["years_experience"] == 7
    assert cleaned["work_experience"] == []
    assert cleaned["education"] == []


@pytest.mark.asyncio
async def test_parse_resume_llm_exception_with_friendly_message(monkeypatch) -> None:
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(side_effect=RuntimeError("RESOURCE_EXHAUSTED"))
    monkeypatch.setattr("utils.resume_parser.get_gemini_client", AsyncMock(return_value=mock_client))
    monkeypatch.setattr(
        "utils.resume_parser.user_facing_message_from_llm_exception",
        lambda e: "Rate limit exceeded",
    )
    with pytest.raises(ValueError, match="Rate limit exceeded"):
        await parse_resume("x" * 80)


@pytest.mark.asyncio
async def test_parse_resume_from_file_insufficient_text(monkeypatch) -> None:
    with pytest.raises(ValueError, match="Could not extract sufficient text"):
        await parse_resume_from_file(b"short", "resume.txt")


@pytest.mark.asyncio
async def test_parse_resume_from_file_success(monkeypatch) -> None:
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(
        return_value={"response": '{"full_name": "Ann", "skills": [], "work_experience": [], "education": []}'}
    )
    monkeypatch.setattr("utils.resume_parser.get_gemini_client", AsyncMock(return_value=mock_client))
    content = ("Professional experience " * 10).encode()
    result = await parse_resume_from_file(content, "resume.txt")
    assert result["full_name"] == "Ann"


def test_extract_text_from_file_pdf_branch() -> None:
    mock_doc = MagicMock()
    mock_page = MagicMock()
    mock_page.get_text.return_value = "PDF resume text"
    mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
    mock_fitz = MagicMock()
    mock_fitz.open.return_value = mock_doc
    with patch.dict("sys.modules", {"fitz": mock_fitz}):
        text = extract_text_from_file(b"%PDF-1.4", "resume.pdf")
    assert "PDF resume text" in text


def test_extract_text_from_file_docx_branch() -> None:
    mock_docx2txt = MagicMock()
    mock_docx2txt.process.return_value = "DOCX resume text"
    with patch.dict("sys.modules", {"docx2txt": mock_docx2txt}):
        text = extract_text_from_file(b"PK\x03\x04", "resume.docx")
    assert text == "DOCX resume text"


def test_extract_text_from_file_docx_branch_via_main_path() -> None:
    mock_docx2txt = MagicMock()
    mock_docx2txt.process.return_value = "DOCX via main path"
    with patch.dict("sys.modules", {"docx2txt": mock_docx2txt}):
        text = extract_text_from_file(b"PK\x03\x04", "resume.docx")
    assert text == "DOCX via main path"


def test_clean_parsed_data_years_experience_from_string() -> None:
    cleaned = _clean_parsed_data({"years_experience": "12", "skills": []})
    assert cleaned["years_experience"] == 12


def test_clean_parsed_data_years_experience_from_float() -> None:
    cleaned = _clean_parsed_data({"years_experience": 5.5, "skills": []})
    assert cleaned["years_experience"] == 5


def test_clean_list_non_list_returns_empty() -> None:
    assert _clean_list("not-a-list") == []


@pytest.mark.asyncio
async def test_parse_resume_generic_failure_message(monkeypatch) -> None:
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(side_effect=RuntimeError("network down"))
    monkeypatch.setattr("utils.resume_parser.get_gemini_client", AsyncMock(return_value=mock_client))
    monkeypatch.setattr(
        "utils.resume_parser.user_facing_message_from_llm_exception",
        lambda e: str(e),
    )
    with pytest.raises(ValueError, match="Failed to parse resume"):
        await parse_resume("x" * 80)
