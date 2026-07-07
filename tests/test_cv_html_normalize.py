"""Tests for utils.cv_html_normalize."""

from utils.cv_html_normalize import normalize_cv_export_html

SAMPLE_HTML_WITH_DUPES = """<!DOCTYPE html><html><body>
<h1 style="font-size:24px">Jane Smith</h1>
<p style="font-size:13px">Senior Engineer</p>
<p style="font-size:11px;color:#666">jane@example.com | Toronto</p>
<h2 style="text-transform:uppercase">Professional Summary</h2>
<p>Summary paragraph here.</p>
<h2>Work Experience</h2>
<h3>Cakewalk — Founding Engineer</h3>
<ul><li>Led Python migration</li></ul>
<p>Led Python migration</p>
</body></html>
"""

SAMPLE_HTML_LI_P = """<!DOCTYPE html><html><body>
<ul>
<li><p>Led Python migration</p></li>
<li><p>Built API layer</p></li>
</ul>
</body></html>
"""

SAMPLE_HTML_P_INSIDE_UL = """<!DOCTYPE html><html><body>
<ul>
<li>Led Python migration</li>
<p>Led Python migration</p>
<li>Built API layer</li>
<p>Built API layer</p>
</ul>
</body></html>
"""


class TestNormalizeCvExportHtml:
    def test_removes_duplicate_bullet_paragraphs(self):
        out = normalize_cv_export_html(SAMPLE_HTML_WITH_DUPES)
        assert out.count("Led Python migration") == 1

    def test_unwraps_paragraph_inside_list_item(self):
        out = normalize_cv_export_html(SAMPLE_HTML_LI_P)
        assert out.count("Led Python migration") == 1
        assert out.count("Built API layer") == 1
        assert "<li><p>" not in out
        assert "• Led Python migration" in out

    def test_removes_paragraph_siblings_inside_list(self):
        out = normalize_cv_export_html(SAMPLE_HTML_P_INSIDE_UL)
        assert out.count("Led Python migration") == 1
        assert out.count("Built API layer") == 1

    def test_converts_lists_to_bullet_paragraphs_for_libreoffice(self):
        out = normalize_cv_export_html(SAMPLE_HTML_LI_P)
        assert "<ul>" not in out
        assert "<ol>" not in out
        assert "• Led Python migration" in out
        assert "• Built API layer" in out

    def test_removes_professional_summary_heading(self):
        out = normalize_cv_export_html(SAMPLE_HTML_WITH_DUPES)
        assert "Professional Summary" not in out
        assert "Summary paragraph here." in out

    def test_renames_work_experience_section(self):
        out = normalize_cv_export_html(SAMPLE_HTML_WITH_DUPES)
        assert "RELEVANT EXPERIENCE" in out
        assert "Work Experience" not in out

    def test_splits_combined_role_heading(self):
        out = normalize_cv_export_html(SAMPLE_HTML_WITH_DUPES)
        assert "Founding Engineer" in out
        assert "Cakewalk" in out
        assert "Cakewalk — Founding Engineer" not in out

    def test_reorders_contact_before_title(self):
        out = normalize_cv_export_html(SAMPLE_HTML_WITH_DUPES)
        contact_pos = out.find("jane@example.com")
        title_pos = out.find("Senior Engineer")
        assert contact_pos != -1 and title_pos != -1
        assert contact_pos < title_pos


SAMPLE_HTML_EDUCATION = """<!DOCTYPE html><html><body>
<h1>Jane Smith</h1>
<h2>Education</h2>
<h3>MIT — Bachelor of Science in Computer Science</h3>
</body></html>
"""

SAMPLE_HTML_PREV_SIBLING_DUPES = """<!DOCTYPE html><html><body>
<ul><li>Built API layer</li></ul>
<p>Built API layer</p>
</body></html>
"""

SAMPLE_HTML_INSIDE_LIST_DUPES = """<!DOCTYPE html><html><body>
<ul>
<li>First item</li>
<p>First item</p>
</ul>
</body></html>
"""

SAMPLE_HTML_CONTACT_AFTER_TITLE = """<!DOCTYPE html><html><body>
<h1>Jane Smith</h1>
<p>Senior Engineer</p>
<p>jane@example.com | Toronto</p>
</body></html>
"""


class TestNormalizeCvExportHtmlExtended:
    def test_splits_education_degree_heading(self):
        out = normalize_cv_export_html(SAMPLE_HTML_EDUCATION)
        assert "MIT" in out
        assert "Bachelor" in out

    def test_removes_duplicate_paragraph_before_list(self):
        out = normalize_cv_export_html(SAMPLE_HTML_PREV_SIBLING_DUPES)
        assert out.count("Built API layer") == 1

    def test_removes_duplicate_paragraph_inside_list(self):
        out = normalize_cv_export_html(SAMPLE_HTML_INSIDE_LIST_DUPES)
        assert out.count("First item") == 1

    def test_reorders_contact_when_it_follows_title(self):
        out = normalize_cv_export_html(SAMPLE_HTML_CONTACT_AFTER_TITLE)
        contact_pos = out.find("jane@example.com")
        title_pos = out.find("Senior Engineer")
        assert contact_pos < title_pos


SAMPLE_HTML_FRAGMENT = """<body>
<h1>Jane Smith</h1>
<p>Summary only.</p>
</body>"""

SAMPLE_HTML_MULTI_NEXT_DUPES = """<!DOCTYPE html><html><body>
<ul><li>Duplicate item</li></ul>
<p>Duplicate item</p>
<p>Duplicate item</p>
<p>Not a duplicate</p>
</body></html>"""

SAMPLE_HTML_PREV_SIBLING = """<!DOCTYPE html><html><body>
<p>Built API layer</p>
<ul><li>Built API layer</li></ul>
</body></html>"""

SAMPLE_HTML_GLOBAL_LI_DUPE = """<!DOCTYPE html><html><body>
<ul><li>Shared bullet</li></ul>
<p>Shared bullet</p>
</body></html>"""

SAMPLE_HTML_EMPTY_LI = """<!DOCTYPE html><html><body>
<ul><li></li><li>Real bullet</li></ul>
</body></html>"""

SAMPLE_HTML_PREFixed_BULLET = """<!DOCTYPE html><html><body>
<ul><li>• Already prefixed</li></ul>
</body></html>"""

SAMPLE_HTML_PLAIN_H3 = """<!DOCTYPE html><html><body>
<h2>Work Experience</h2>
<h3>Senior Engineer</h3>
</body></html>"""

SAMPLE_HTML_EDUCATION_DEGREE_LEFT = """<!DOCTYPE html><html><body>
<h2>Education</h2>
<h3>Bachelor of Science — MIT</h3>
</body></html>"""

SAMPLE_HTML_EDUCATION_NO_HINT = """<!DOCTYPE html><html><body>
<h2>Education</h2>
<h3>MIT — Cambridge, MA</h3>
</body></html>"""

SAMPLE_HTML_PREV_SIBLING_BREAK = """<!DOCTYPE html><html><body>
<p>Unrelated paragraph</p>
<ul><li>Built API layer</li></ul>
</body></html>"""

SAMPLE_HTML_LI_WRAPPED_DUPE = """<!DOCTYPE html><html><body>
<ul><li><p>Shared bullet</p></li></ul>
<p>Shared bullet</p>
</body></html>"""

SAMPLE_HTML_EDUCATION_SKIP_SUMMARY = """<!DOCTYPE html><html><body>
<h2>Education</h2>
<h2>Professional Summary</h2>
<h3>MIT — Bachelor of Science</h3>
</body></html>"""


class TestNormalizeCvExportHtmlEdgeCases:
    def test_returns_body_only_when_no_html_wrapper(self):
        out = normalize_cv_export_html(SAMPLE_HTML_FRAGMENT)
        assert "<html>" not in out
        assert "Jane Smith" in out

    def test_removes_multiple_next_sibling_duplicate_paragraphs(self):
        out = normalize_cv_export_html(SAMPLE_HTML_MULTI_NEXT_DUPES)
        assert out.count("Duplicate item") == 1
        assert "Not a duplicate" in out

    def test_removes_previous_sibling_duplicate_paragraph(self):
        out = normalize_cv_export_html(SAMPLE_HTML_PREV_SIBLING)
        assert out.count("Built API layer") == 1

    def test_removes_global_paragraph_matching_any_li(self):
        out = normalize_cv_export_html(SAMPLE_HTML_GLOBAL_LI_DUPE)
        assert out.count("Shared bullet") == 1

    def test_skips_empty_list_items(self):
        out = normalize_cv_export_html(SAMPLE_HTML_EMPTY_LI)
        assert "Real bullet" in out

    def test_preserves_prefixed_bullet_text(self):
        out = normalize_cv_export_html(SAMPLE_HTML_PREFixed_BULLET)
        assert "• Already prefixed" in out

    def test_leaves_plain_h3_unsplit(self):
        out = normalize_cv_export_html(SAMPLE_HTML_PLAIN_H3)
        assert "Senior Engineer" in out
        assert "—" not in out

    def test_education_degree_on_left_side(self):
        out = normalize_cv_export_html(SAMPLE_HTML_EDUCATION_DEGREE_LEFT)
        assert "MIT" in out
        assert "Bachelor" in out

    def test_education_without_degree_hint(self):
        out = normalize_cv_export_html(SAMPLE_HTML_EDUCATION_NO_HINT)
        assert "MIT" in out
        assert "Cambridge" in out

    def test_stops_previous_sibling_scan_on_unrelated_paragraph(self):
        out = normalize_cv_export_html(SAMPLE_HTML_PREV_SIBLING_BREAK)
        assert "Unrelated paragraph" in out
        assert out.count("Built API layer") == 1

    def test_skips_li_wrapped_paragraph_for_global_dupe(self):
        out = normalize_cv_export_html(SAMPLE_HTML_LI_WRAPPED_DUPE)
        assert out.count("Shared bullet") == 1

    def test_education_skips_summary_section_when_finding_previous(self):
        out = normalize_cv_export_html(SAMPLE_HTML_EDUCATION_SKIP_SUMMARY)
        assert "MIT" in out
        assert "Bachelor" in out


SAMPLE_HTML_PREV_LI_GLOBAL_DUPE = """<!DOCTYPE html><html><body>
<ul><li>Match me</li></ul>
<p>Other text</p>
<p>Match me</p>
</body></html>"""


class TestNormalizeCvExportHtmlRemaining:
    def test_removes_global_paragraph_when_prev_li_matches(self):
        out = normalize_cv_export_html(SAMPLE_HTML_PREV_LI_GLOBAL_DUPE)
        assert out.count("Match me") == 1
        assert "Other text" in out
