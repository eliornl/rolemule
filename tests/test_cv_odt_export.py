"""Tests for utils.cv_odt_export — HTML and markdown CV to ODT."""

import io
import zipfile

import pytest

from utils.cv_odt_export import html_cv_to_odt_bytes, markdown_cv_to_odt_bytes

SAMPLE_CV = """# Jane Smith
**Senior Engineer**
jane@example.com | Toronto, ON

## Professional Summary
Experienced backend engineer with Python expertise.

## Work Experience
### Engineer — ACME Corp
*2020–Present*
- Led Python migration
- Reduced latency by 40%

## Skills
Python, AWS, PostgreSQL
"""

LLM_STYLE_CV = """# Jane Smith
**Senior Engineer**
jane@example.com | Toronto, ON

## Professional Summary
Experienced backend engineer.

## Work Experience
### Engineer — ACME Corp
*2020–Present*
▪ Led Python migration across 15 services
▪ Reduced API latency by 40%
"""

SAMPLE_HTML = """<!DOCTYPE html>
<html><body style="font-family:Arial,Helvetica,sans-serif">
<h1 style="font-size:24px;font-weight:bold;color:#111">Jane Smith</h1>
<p style="font-size:13px;color:#555">Senior Engineer</p>
<p style="font-size:11px;color:#666">jane@example.com | Toronto, ON</p>
<h2 style="font-size:12px;font-weight:bold;text-transform:uppercase;border-bottom:1px solid #444">Professional Summary</h2>
<p style="font-size:11px;line-height:1.5;color:#222">Experienced backend engineer with Python expertise.</p>
<h2 style="font-size:12px;font-weight:bold;text-transform:uppercase;border-bottom:1px solid #444">Work Experience</h2>
<h3 style="font-size:12px;font-weight:bold;color:#111">Engineer — ACME Corp</h3>
<p style="font-size:11px;font-style:italic;color:#555">2020–Present</p>
<ul style="margin:4px 0 8px 20px;padding:0">
<li style="font-size:11px;line-height:1.5;color:#222">Led Python migration</li>
<li style="font-size:11px;line-height:1.5;color:#222">Reduced latency by 40%</li>
</ul>
</body></html>
"""


class TestHtmlCvToOdtBytes:
    def test_renders_lists_and_headings(self):
        data = html_cv_to_odt_bytes(SAMPLE_HTML)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("content.xml").decode("utf-8")
        assert "Jane Smith" in xml
        assert "PROFESSIONAL SUMMARY" in xml.upper()
        assert "Led Python migration" in xml
        assert 'text:style-name="CVBullet"' in xml
        assert 'text:style-name="CVDate"' in xml or "2020" in xml


class TestMarkdownCvToOdtBytes:
    def test_returns_valid_odt_zip(self):
        data = markdown_cv_to_odt_bytes(SAMPLE_CV)
        assert data[:2] == b"PK"
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert "content.xml" in zf.namelist()
            xml = zf.read("content.xml").decode("utf-8")
        assert "Jane Smith" in xml
        assert "Led Python migration" in xml

    def test_empty_markdown_still_produces_odt(self):
        data = markdown_cv_to_odt_bytes("")
        assert data[:2] == b"PK"

    def test_date_lines_are_not_bullets(self):
        data = markdown_cv_to_odt_bytes(LLM_STYLE_CV)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("content.xml").decode("utf-8")
        assert 'text:style-name="CVDate"' in xml
        assert "2020" in xml
        assert "Present" in xml

    def test_square_bullet_lines_use_bullet_style(self):
        data = markdown_cv_to_odt_bytes(LLM_STYLE_CV)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("content.xml").decode("utf-8")
        assert 'text:style-name="CVBullet"' in xml
        assert "Reduced API latency" in xml

    def test_contact_line_uses_contact_style(self):
        data = markdown_cv_to_odt_bytes(SAMPLE_CV)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("content.xml").decode("utf-8")
        assert 'text:style-name="CVContact"' in xml

    def test_education_and_skill_category_lines(self):
        cv = """# Jane Doe
jane@example.com

## Education
### MIT — Bachelor of Science

## Skills
Languages: Python • Go
"""
        data = markdown_cv_to_odt_bytes(cv)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("content.xml").decode("utf-8")
        assert "Jane Doe" in xml
        assert "Python" in xml

    def test_html_education_role_split(self):
        html = """<!DOCTYPE html><html><body>
<h2>Education</h2>
<h3>MIT — Bachelor of Science</h3>
</body></html>"""
        data = html_cv_to_odt_bytes(html)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("content.xml").decode("utf-8")
        assert "MIT" in xml

    @pytest.mark.asyncio
    async def test_export_without_libreoffice_returns_docx(self):
        from unittest.mock import patch

        from api.cv_optimizer import _export_optimized_cv_file

        with patch("api.cv_optimizer._resolve_soffice_path", return_value=None):
            data, media_type, filename = await _export_optimized_cv_file(
                SAMPLE_CV, user_api_key=None
            )

        assert filename == "optimized-cv.docx"
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "Jane Smith" in xml


class TestHtmlCvToOdtEdgeCases:
    def test_inline_bold_and_italic_markdown(self):
        html = """<!DOCTYPE html><html><body>
<p>Skills include <strong>Python</strong> and <em>leadership</em>.</p>
</body></html>"""
        data = html_cv_to_odt_bytes(html)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("content.xml").decode("utf-8")
        assert "Python" in xml
        assert "InlineBold" in xml
        assert "InlineItalic" in xml

    def test_ordered_list_and_div_wrapper(self):
        html = """<!DOCTYPE html><html><body>
<div>
<ol><li>First task</li><li>Second task</li></ol>
</div>
</body></html>"""
        data = html_cv_to_odt_bytes(html)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("content.xml").decode("utf-8")
        assert "1. </text:span><text:span>First task" in xml
        assert "2. </text:span><text:span>Second task" in xml

    def test_date_and_role_paragraph_styles(self):
        html = """<!DOCTYPE html><html><body>
<p style="font-size:11px;font-style:italic;color:#555">2020–Present</p>
<p style="font-size:12px;font-weight:bold;color:#111">Engineer — ACME Corp</p>
</body></html>"""
        data = html_cv_to_odt_bytes(html)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("content.xml").decode("utf-8")
        assert "2020" in xml
        assert "ACME Corp" in xml

    def test_empty_paragraph_renders_blank_span(self):
        html = """<!DOCTYPE html><html><body><p></p></body></html>"""
        data = html_cv_to_odt_bytes(html)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("content.xml").decode("utf-8")
        assert "office:document-content" in xml


class TestMarkdownCvToOdtEdgeCases:
    def test_inline_markdown_and_wrapping_asterisks(self):
        cv = """# Jane Doe
**Senior Engineer**
jane@example.com

## Summary
Expert in **Python** and *communication*.
"""
        data = markdown_cv_to_odt_bytes(cv)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("content.xml").decode("utf-8")
        assert "InlineBold" in xml
        assert "InlineItalic" in xml

    def test_role_line_and_skill_category(self):
        cv = """# Jane Doe
jane@example.com

## Work Experience
Engineer — ACME Corp

## Skills
▪ **Languages:** Python, Go
"""
        data = markdown_cv_to_odt_bytes(cv)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("content.xml").decode("utf-8")
        assert "ACME Corp" in xml
        assert "Languages" in xml

    def test_star_bullet_and_invalid_skill_line(self):
        cv = """# Jane Doe
jane@example.com

## Skills
* Bullet via star prefix
Short:
"""
        data = markdown_cv_to_odt_bytes(cv)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("content.xml").decode("utf-8")
        assert "Bullet via star prefix" in xml

    def test_empty_inline_markdown_paragraph(self):
        cv = """# Jane Doe
jane@example.com

## Summary

"""
        data = markdown_cv_to_odt_bytes(cv)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("content.xml").decode("utf-8")
        assert "Jane Doe" in xml

    def test_html_walks_non_tag_nodes(self):
        html = """<!DOCTYPE html><html><body>
<p>Hello <!-- comment --> world</p>
</body></html>"""
        data = html_cv_to_odt_bytes(html)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("content.xml").decode("utf-8")
        assert "Hello" in xml
        assert "world" in xml
