# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from cli.formatters.workflow import VALID_SECTIONS, format_workflow_results


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def _section_filename(section: str) -> str:
    return section.replace("-", "_") + ".md"


def _extract_section_text(data: Dict[str, Any], section: str) -> str:
    if section == "all":
        parts = []
        for name in sorted(VALID_SECTIONS - {"all"}):
            part = format_workflow_results(data, section=name)
            if part.strip():
                parts.append(part)
        return "\n\n".join(parts)
    return format_workflow_results(data, section=section)


def write_workflow_results(
    data: Dict[str, Any],
    *,
    section: str,
    out: Optional[Path] = None,
    out_dir: Optional[Path] = None,
    as_json: bool = False,
) -> Dict[str, Any]:
    """
    Write workflow results to file(s).

    Returns:
        Summary dict with paths written
    """
    written: Dict[str, Any] = {}

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        if as_json:
            path = out_dir / "results.json"
            path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            written["results_json"] = str(path)
        else:
            if section == "all":
                for name in sorted(VALID_SECTIONS - {"all"}):
                    text = _extract_section_text(data, name)
                    if text.strip():
                        path = out_dir / _section_filename(name)
                        path.write_text(text + "\n", encoding="utf-8")
                        written[name] = str(path)
            else:
                path = out_dir / _section_filename(section)
                path.write_text(_extract_section_text(data, section) + "\n", encoding="utf-8")
                written[section] = str(path)
        return {"saved_to": written}

    if out is not None:
        if as_json:
            out.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        else:
            out.write_text(_extract_section_text(data, section) + "\n", encoding="utf-8")
        return {"saved_to": str(out), "size_bytes": out.stat().st_size}

    return {}
