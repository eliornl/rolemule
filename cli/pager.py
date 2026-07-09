# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

import os
import shutil
import subprocess
import sys


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def maybe_page(text: str, *, no_pager: bool = False, quiet: bool = False) -> None:
    """
    Print text, paging through $PAGER when output exceeds terminal height.

    Args:
        text: Content to display
        no_pager: Skip pager even for long output
        quiet: Unused hook for future; pager still runs unless no_pager
    """
    del quiet  # reserved
    if no_pager or not text:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        return

    line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    try:
        term_rows = os.get_terminal_size().lines
    except OSError:
        term_rows = 24

    if line_count <= max(term_rows - 2, 10):
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        return

    pager_cmd = os.environ.get("APPLYPILOT_PAGER") or os.environ.get("PAGER") or "less"
    parts = pager_cmd.split()
    executable = parts[0]
    if executable == "cat" or shutil.which(executable) is None:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        return

    try:
        subprocess.run(
            parts,
            input=text,
            text=True,
            check=False,
        )
    except OSError:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
