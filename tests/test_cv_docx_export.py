"""Tests for utils.cv_docx_export — markdown CV to DOCX."""

import io
import zipfile

import pytest

from utils.cv_docx_export import markdown_cv_to_docx_bytes

SAMPLE_CV = """# Elior Nataf Lackritz
**Founding Engineer**
eliornataflackritz@gmail.com | Hoboken, NJ, United States

## Professional Summary
Senior Software Engineer specializing in backend architecture.

## Work Experience
Cakewalk — Founding Engineer
*2025-07–Present*
Building an automated benefits platform from the ground up.
▪ Architecting production-ready AWS infrastructure using Terraform
▪ Leading backend development in TypeScript, Node.js, and Python

## Skills
Languages & Frameworks: Python • TypeScript • FastAPI • Django
Infrastructure & DevOps: AWS • Terraform • Docker • Kubernetes
"""


class TestMarkdownCvToDocxBytes:
    def test_returns_valid_docx_zip(self):
        data = markdown_cv_to_docx_bytes(SAMPLE_CV)
        assert data[:2] == b"PK"
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert "word/document.xml" in zf.namelist()
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "Elior Nataf Lackritz" in xml
        assert "Architecting production-ready AWS" in xml

    def test_sections_renamed_like_source_resume(self):
        data = markdown_cv_to_docx_bytes(SAMPLE_CV)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "Relevant Experience" in xml
        assert "Core Technologies" in xml
        assert "Professional Summary" not in xml

    def test_header_order_contact_before_title(self):
        data = markdown_cv_to_docx_bytes(SAMPLE_CV)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        contact_pos = xml.find("eliornataflackritz@gmail.com")
        title_pos = xml.find("Founding Engineer")
        assert contact_pos != -1 and title_pos != -1
        assert contact_pos < title_pos

    def test_skills_use_middle_dot_separators(self):
        data = markdown_cv_to_docx_bytes(SAMPLE_CV)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "Python • TypeScript" in xml

    def test_role_split_into_title_and_company(self):
        data = markdown_cv_to_docx_bytes(SAMPLE_CV)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "Founding Engineer" in xml
        assert "Cakewalk" in xml

    def test_education_section_and_bullet_variants(self):
        cv = """# Jane Doe
**Engineer**
jane@example.com

## Education
### MIT — Bachelor of Science
*2018–2022*

## Skills
Languages: Python • Go
- Python experience
* Star bullet item
▪ Square bullet item
"""
        data = markdown_cv_to_docx_bytes(cv)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "MIT" in xml
        assert "Python" in xml

    def test_role_line_in_experience_section(self):
        cv = """# Jane Doe
jane@example.com

## Work Experience
Acme Corp — Platform Engineer
Led migrations.
"""
        data = markdown_cv_to_docx_bytes(cv)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "Platform Engineer" in xml
        assert "Acme Corp" in xml

    @pytest.mark.asyncio
    async def test_export_without_libreoffice_returns_docx(self):
        from unittest.mock import patch

        from api.cv_optimizer import _export_optimized_cv_file

        with patch("api.cv_optimizer._resolve_soffice_path", return_value=None):
            data, media_type, filename = await _export_optimized_cv_file(
                SAMPLE_CV, user_api_key=None
            )

        assert filename == "optimized-cv.docx"
        assert "wordprocessingml" in media_type
        assert data[:2] == b"PK"


class TestMarkdownCvToDocxEdgeCases:
    def test_single_asterisk_subtitle_and_colon_skills(self):
        cv = """# Jane Doe
*Product Manager*
jane@example.com

## Skills
Languages: Python, Go, Rust
"""
        data = markdown_cv_to_docx_bytes(cv)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "Product Manager" in xml
        assert "Python • Go" in xml

    def test_education_degree_on_left_and_plain_heading(self):
        cv = """# Jane Doe
jane@example.com

## Education
### Bachelor of Science — MIT
Plain school line without dash separator
"""
        data = markdown_cv_to_docx_bytes(cv)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "MIT" in xml
        assert "Plain school line" in xml

    def test_role_block_without_separator(self):
        cv = """# Jane Doe
jane@example.com

## Work Experience
### Senior Engineer
"""
        data = markdown_cv_to_docx_bytes(cv)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "Senior Engineer" in xml

    def test_contact_line_inside_section(self):
        cv = """# Jane Doe

## Work Experience
jane@example.com | Remote
Led migrations.
"""
        data = markdown_cv_to_docx_bytes(cv)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "jane@example.com" in xml

    def test_bold_subtitle_in_section_and_education_role_line(self):
        cv = """# Jane Doe
jane@example.com

## Work Experience
**Staff Engineer**

## Education
MIT — Bachelor of Arts
"""
        data = markdown_cv_to_docx_bytes(cv)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "Staff Engineer" in xml
        assert "MIT" in xml

    def test_skills_bullet_with_middle_dot_separator(self):
        cv = """# Jane Doe
jane@example.com

## Skills
• Languages: Python • Go
"""
        data = markdown_cv_to_docx_bytes(cv)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "Languages" in xml
        assert "Python" in xml

    def test_date_line_skipped_as_bullet_and_single_asterisk_subtitle(self):
        from utils.cv_docx_export import _is_date_line, _strip_wrapping_asterisks

        assert _is_date_line("*2020–2024*") is True
        assert _strip_wrapping_asterisks("*Subtitle*") == "Subtitle"

    def test_skill_colon_line_in_skills_section(self):
        cv = """# Jane Doe
jane@example.com

## Skills
Languages: Python, Go, Rust
"""
        data = markdown_cv_to_docx_bytes(cv)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "Python" in xml
        assert "Languages" in xml

    def test_single_asterisk_strip_and_date_line_skipped(self):
        cv = """# Jane Doe
*Product Designer*
jane@example.com

## Work Experience
*2020–2022*
- Built features
"""
        data = markdown_cv_to_docx_bytes(cv)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "Product Designer" in xml
        assert "Built features" in xml

    def test_skill_colon_fallback_and_plain_education_line(self):
        cv = """# Jane Doe
jane@example.com

## Skills
Tools: Docker

## Education
Standalone University Name
"""
        data = markdown_cv_to_docx_bytes(cv)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "Docker" in xml
        assert "Standalone University Name" in xml

    def test_education_degree_on_right_side(self):
        cv = """# Jane Doe
jane@example.com

## Education
MIT — Bachelor of Science
"""
        data = markdown_cv_to_docx_bytes(cv)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "MIT" in xml
        assert "Bachelor" in xml

    def test_skills_bullet_with_colon_and_middle_dot(self):
        cv = """# Jane Doe
jane@example.com

## Skills
• Cloud: AWS • GCP • Azure
"""
        data = markdown_cv_to_docx_bytes(cv)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "AWS" in xml
        assert "GCP" in xml

    def test_asterisk_bullet_line(self):
        cv = """# Jane Doe
jane@example.com

## Work Experience
* Led platform migration
"""
        data = markdown_cv_to_docx_bytes(cv)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "Led platform migration" in xml
