"""Tests for rolemule extension formatters."""

from __future__ import annotations

from cli.formatters.extension import format_autofill_map


def test_format_autofill_map_includes_assignments_and_skipped() -> None:
    text = format_autofill_map(
        {
            "assignments": [{"field_uid": "0", "label_text": "Email", "value": "jane@example.com"}],
            "skipped": [{"field_uid": "5", "reason": "Resume file"}],
            "warnings": ["Review before applying."],
        }
    )
    assert "Email" in text
    assert "jane@example.com" in text
    assert "Resume file" in text
    assert "Review before applying." in text
