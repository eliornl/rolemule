"""
Convert CV content to ODT bytes without LibreOffice.

Primary fallback: Gemini-styled HTML → ODT (same HTML as the LibreOffice path).
Last resort: markdown → ODT when HTML conversion is unavailable.
"""

from __future__ import annotations

import html
import io
import re
from typing import Optional, Union

from bs4 import BeautifulSoup, NavigableString, Tag
from odf.opendocument import OpenDocumentText
from odf.style import MasterPage, PageLayout, PageLayoutProperties, ParagraphProperties, Style, TextProperties
from odf.text import H, P, Span

# Inline markdown: **bold** and *italic* (non-greedy, no nesting)
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_BULLET_PREFIX_RE = re.compile(r"^[\-\u2022\u25AA]\s+(.+)$")
_ASTERISK_BULLET_RE = re.compile(r"^\*\s+(.+)$")
_CONTACT_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_ROLE_LINE_RE = re.compile(r"^[^\-•▪\*].+\s[—–-]\s.+$")
_SKILL_CATEGORY_RE = re.compile(
    r"^[\-\u2022\u25AA\*]\s*\*{0,2}([^*\n:]{3,}):\*{0,2}\s*(.+)$"
)


def _decode_text(text: str) -> str:
    """Decode HTML entities; repeat until stable (handles double-encoded ``&amp;``)."""
    prev = None
    current = text or ""
    while prev != current:
        prev = current
        current = html.unescape(current)
    return " ".join(current.split())


def _add_paragraph_style(
    doc: OpenDocumentText,
    name: str,
    *,
    font_size: str,
    font_weight: Optional[str] = None,
    font_style: Optional[str] = None,
    color: Optional[str] = None,
    margin_top: Optional[str] = None,
    margin_bottom: Optional[str] = None,
    margin_left: Optional[str] = None,
    text_indent: Optional[str] = None,
    line_height: Optional[str] = None,
    border_bottom: Optional[str] = None,
    padding_bottom: Optional[str] = None,
) -> None:
    """Register a named paragraph style on the document."""
    style = Style(name=name, family="paragraph")
    tp_kwargs: dict[str, str] = {"fontfamily": "Arial, Helvetica, sans-serif", "fontsize": font_size}
    if font_weight:
        tp_kwargs["fontweight"] = font_weight
    if font_style:
        tp_kwargs["fontstyle"] = font_style
    if color:
        tp_kwargs["color"] = color
    style.addElement(TextProperties(**tp_kwargs))

    pp_kwargs: dict[str, str] = {}
    if margin_top:
        pp_kwargs["margintop"] = margin_top
    if margin_bottom:
        pp_kwargs["marginbottom"] = margin_bottom
    if margin_left:
        pp_kwargs["marginleft"] = margin_left
    if text_indent:
        pp_kwargs["textindent"] = text_indent
    if line_height:
        pp_kwargs["lineheight"] = line_height
    if border_bottom:
        pp_kwargs["borderbottom"] = border_bottom
    if padding_bottom:
        pp_kwargs["paddingbottom"] = padding_bottom
    if pp_kwargs:
        style.addElement(ParagraphProperties(**pp_kwargs))
    doc.styles.addElement(style)


def _register_cv_styles(doc: OpenDocumentText) -> None:
    """Define shared CV paragraph and inline text styles."""
    _add_paragraph_style(
        doc, "CVName", font_size="24pt", font_weight="bold", margin_bottom="0.12cm", color="#111111"
    )
    _add_paragraph_style(
        doc, "CVSubtitle", font_size="13pt", margin_bottom="0.08cm", color="#555555"
    )
    _add_paragraph_style(
        doc, "CVContact", font_size="11pt", margin_bottom="0.55cm", color="#666666"
    )
    _add_paragraph_style(
        doc,
        "CVSection",
        font_size="12pt",
        font_weight="bold",
        margin_top="0.5cm",
        margin_bottom="0.12cm",
        color="#111111",
        border_bottom="0.06pt solid #444444",
        padding_bottom="0.08cm",
    )
    _add_paragraph_style(
        doc, "CVRole", font_size="12pt", font_weight="bold", margin_top="0.28cm", color="#111111"
    )
    _add_paragraph_style(
        doc, "CVDate", font_size="11pt", font_style="italic", margin_bottom="0.1cm", color="#555555"
    )
    _add_paragraph_style(
        doc,
        "CVBody",
        font_size="11pt",
        margin_bottom="0.06cm",
        color="#222222",
        line_height="140%",
    )
    _add_paragraph_style(
        doc,
        "CVBullet",
        font_size="11pt",
        margin_bottom="0.06cm",
        margin_left="0.75cm",
        text_indent="-0.35cm",
        color="#222222",
        line_height="140%",
    )
    _add_paragraph_style(
        doc,
        "CVSkill",
        font_size="11pt",
        margin_bottom="0.06cm",
        color="#222222",
        line_height="140%",
    )

    bold_span = Style(name="InlineBold", family="text")
    bold_span.addElement(TextProperties(fontweight="bold", fontfamily="Arial"))
    doc.styles.addElement(bold_span)

    italic_span = Style(name="InlineItalic", family="text")
    italic_span.addElement(TextProperties(fontstyle="italic", fontfamily="Arial"))
    doc.styles.addElement(italic_span)


def _configure_page_layout(doc: OpenDocumentText) -> None:
    """Set document page margins similar to the LibreOffice HTML export."""
    layout = PageLayout(name="CVPageLayout")
    layout.addElement(
        PageLayoutProperties(
            pageheight="29.7cm",
            pagewidth="21cm",
            marginleft="2.5cm",
            marginright="2.5cm",
            margintop="2.2cm",
            marginbottom="2.2cm",
        )
    )
    doc.automaticstyles.addElement(layout)
    master = MasterPage(name="Standard", pagelayoutname="CVPageLayout")
    doc.masterstyles.addElement(master)


def _paragraph_with_inline_markdown(text: str, stylename: str) -> P:
    """Build a paragraph, rendering simple **bold** and *italic* inline markers as spans."""
    paragraph = P(stylename=stylename)
    clean = _decode_text(text)
    if not clean:
        paragraph.addElement(Span(text=""))
        return paragraph

    segments: list[tuple[str, Optional[str]]] = [(clean, None)]

    def _apply_pattern(
        parts: list[tuple[str, Optional[str]]],
        pattern: re.Pattern[str],
        style: str,
    ) -> list[tuple[str, Optional[str]]]:
        out: list[tuple[str, Optional[str]]] = []
        for chunk, existing in parts:
            if existing is not None:
                out.append((chunk, existing))
                continue
            pos = 0
            for match in pattern.finditer(chunk):
                if match.start() > pos:
                    out.append((chunk[pos : match.start()], None))
                out.append((match.group(1), style))
                pos = match.end()
            if pos < len(chunk):
                out.append((chunk[pos:], None))
        return out

    segments = _apply_pattern(segments, _BOLD_RE, "bold")
    segments = _apply_pattern(segments, _ITALIC_RE, "italic")

    for segment_text, segment_style in segments:
        if not segment_text:
            continue
        if segment_style == "bold":
            paragraph.addElement(Span(stylename="InlineBold", text=segment_text))
        elif segment_style == "italic":
            paragraph.addElement(Span(stylename="InlineItalic", text=segment_text))
        else:
            paragraph.addElement(Span(text=segment_text))

    return paragraph


def _paragraph_from_tag(tag: Tag, stylename: str, *, prefix: str = "") -> P:
    """Convert an HTML node (and inline children) to an ODT paragraph."""
    paragraph = P(stylename=stylename)
    if prefix:
        paragraph.addElement(Span(text=prefix))

    def _walk(node: Union[Tag, NavigableString]) -> None:
        if isinstance(node, NavigableString):
            text = _decode_text(str(node))
            if text:
                paragraph.addElement(Span(text=text))
            return
        if not isinstance(node, Tag):
            return
        name = (node.name or "").lower()
        if name in ("strong", "b"):
            paragraph.addElement(Span(stylename="InlineBold", text=_decode_text(node.get_text())))
            return
        if name in ("em", "i"):
            paragraph.addElement(Span(stylename="InlineItalic", text=_decode_text(node.get_text())))
            return
        for child in node.children:
            _walk(child)

    _walk(tag)
    if not list(paragraph.childNodes):
        paragraph.addElement(Span(text=""))
    return paragraph


def _style_attr(tag: Tag) -> str:
    return (tag.get("style") or "").lower().replace(" ", "")


def _infer_paragraph_style(tag: Tag) -> str:
    """Map Gemini inline CSS on ``<p>`` elements to CV paragraph styles."""
    text = _decode_text(tag.get_text())
    css = _style_attr(tag)
    if "font-style:italic" in css and any(ch.isdigit() for ch in text):
        return "CVDate"
    if _CONTACT_RE.search(text) or "color:#666" in css:
        return "CVContact"
    if "font-size:13px" in css or "font-size:14px" in css:
        return "CVSubtitle"
    if "font-weight:bold" in css and "font-size:12px" in css:
        return "CVRole"
    return "CVBody"


def _append_html_element(doc: OpenDocumentText, element: Tag) -> None:
    """Append one HTML block element to the ODT document body."""
    name = (element.name or "").lower()

    if name == "h1":
        doc.text.addElement(
            H(outlinelevel=1, stylename="CVName", text=_decode_text(element.get_text()))
        )
    elif name == "h2":
        section = _decode_text(element.get_text()).upper()
        doc.text.addElement(_paragraph_with_inline_markdown(section, "CVSection"))
    elif name == "h3":
        doc.text.addElement(_paragraph_from_tag(element, "CVRole"))
    elif name == "ul":
        for li in element.find_all("li", recursive=False):
            doc.text.addElement(_paragraph_from_tag(li, "CVBullet", prefix="• "))
    elif name == "ol":
        for idx, li in enumerate(element.find_all("li", recursive=False), start=1):
            doc.text.addElement(_paragraph_from_tag(li, "CVBullet", prefix=f"{idx}. "))
    elif name == "p":
        style_name = _infer_paragraph_style(element)
        doc.text.addElement(_paragraph_from_tag(element, style_name))
    elif name == "div":
        for child in element.children:
            if isinstance(child, Tag):
                _append_html_element(doc, child)


def html_cv_to_odt_bytes(html_content: str) -> bytes:
    """
    Convert Gemini-generated CV HTML to ODT bytes.

    Uses the same HTML structure as the LibreOffice export path (h1/h2/h3/p/ul/li
    with inline CSS). Does not require LibreOffice.

    Args:
        html_content: Full HTML document string

    Returns:
        ODT file contents as bytes
    """
    doc = OpenDocumentText()
    _configure_page_layout(doc)
    _register_cv_styles(doc)

    soup = BeautifulSoup(html_content or "", "html.parser")
    body = soup.find("body") or soup

    for element in body.children:
        if isinstance(element, Tag):
            _append_html_element(doc, element)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _strip_wrapping_asterisks(text: str) -> str:
    """Remove a single pair of wrapping * or ** markers."""
    stripped = text.strip()
    if stripped.startswith("**") and stripped.endswith("**") and len(stripped) > 4:
        return stripped[2:-2].strip()
    if (
        stripped.startswith("*")
        and stripped.endswith("*")
        and not stripped.startswith("**")
        and len(stripped) > 2
    ):
        return stripped[1:-1].strip()
    return stripped


def _is_contact_line(text: str) -> bool:
    """Detect email / contact lines (e.g. name@example.com | City, ST)."""
    return bool(_CONTACT_RE.search(text))


def _is_date_line(text: str) -> bool:
    """Detect italic date ranges like *2020–Present*."""
    stripped = text.strip()
    return (
        stripped.startswith("*")
        and stripped.endswith("*")
        and not stripped.startswith("**")
        and any(ch.isdigit() for ch in stripped)
    )


def _parse_bullet_line(text: str) -> Optional[str]:
    """
    Return bullet body text when the line uses an explicit bullet prefix.

    Does **not** treat ``*italic*`` date wrappers as bullets.
    """
    stripped = text.strip()
    if _is_date_line(stripped):
        return None

    match = _BULLET_PREFIX_RE.match(stripped)
    if match:
        return match.group(1).strip() or None

    match = _ASTERISK_BULLET_RE.match(stripped)
    if match:
        return match.group(1).strip() or None

    return None


def _parse_skill_category_line(text: str) -> Optional[tuple[str, str]]:
    """Parse ``▪ Category: items`` skill lines into label + body."""
    stripped = text.strip()
    match = _SKILL_CATEGORY_RE.match(stripped)
    if not match:
        return None
    label = _decode_text(match.group(1).strip().rstrip(":"))
    body = _decode_text(match.group(2).strip())
    if not label or not body:
        return None
    return label, body


def _skill_category_paragraph(label: str, body: str) -> P:
    """Render a skills category line: bold label + body text."""
    paragraph = P(stylename="CVSkill")
    paragraph.addElement(Span(stylename="InlineBold", text=f"{label}: "))
    paragraph.addElement(Span(text=body))
    return paragraph


def markdown_cv_to_odt_bytes(cv_markdown: str) -> bytes:
    """
    Convert RoleMule markdown CV text to ODT file bytes (last-resort fallback).

    Args:
        cv_markdown: Markdown-formatted CV from the optimizer

    Returns:
        ODT file contents as bytes
    """
    doc = OpenDocumentText()
    _configure_page_layout(doc)
    _register_cv_styles(doc)

    lines = (cv_markdown or "").replace("\r\n", "\n").split("\n")

    for raw_line in lines:
        line = raw_line.rstrip()
        if not line:
            continue

        stripped = line.strip()

        if line.startswith("# "):
            doc.text.addElement(H(outlinelevel=1, stylename="CVName", text=line[2:].strip()))
            continue

        if line.startswith("## "):
            section_text = line[3:].strip().upper()
            doc.text.addElement(_paragraph_with_inline_markdown(section_text, "CVSection"))
            continue

        if line.startswith("### "):
            doc.text.addElement(_paragraph_with_inline_markdown(line[4:].strip(), "CVRole"))
            continue

        if _is_date_line(stripped):
            doc.text.addElement(
                _paragraph_with_inline_markdown(_strip_wrapping_asterisks(stripped), "CVDate")
            )
            continue

        if _is_contact_line(stripped):
            doc.text.addElement(_paragraph_with_inline_markdown(stripped, "CVContact"))
            continue

        skill_parts = _parse_skill_category_line(stripped)
        if skill_parts:
            label, body = skill_parts
            doc.text.addElement(_skill_category_paragraph(label, body))
            continue

        bullet_body = _parse_bullet_line(line)
        if bullet_body is not None:
            doc.text.addElement(
                _paragraph_with_inline_markdown(f"• {_decode_text(bullet_body)}", "CVBullet")
            )
            continue

        if stripped.startswith("**") or (stripped.startswith("*") and stripped.endswith("*")):
            subtitle = _strip_wrapping_asterisks(stripped)
            if subtitle and not any(ch.isdigit() for ch in subtitle):
                doc.text.addElement(_paragraph_with_inline_markdown(subtitle, "CVSubtitle"))
                continue

        if _ROLE_LINE_RE.match(stripped):
            doc.text.addElement(_paragraph_with_inline_markdown(stripped, "CVRole"))
            continue

        doc.text.addElement(_paragraph_with_inline_markdown(stripped, "CVBody"))

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
