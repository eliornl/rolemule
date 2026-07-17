# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

import os


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def admin_help_visible() -> bool:
    """Whether admin commands appear in top-level --help (requires ROLEMULE_ADMIN=1)."""
    return os.environ.get("ROLEMULE_ADMIN") == "1"
