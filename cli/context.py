# =============================================================================
# GLOBAL VARIABLES
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from cli.config import CliConfig, Credentials, load_config, load_credentials


@dataclass
class CliContext:
    """Runtime context shared across commands."""

    base_url: str
    output_format: str = "human"
    quiet: bool = False
    verbose: bool = False
    no_color: bool = False
    no_pager: bool = False
    config: CliConfig = field(default_factory=CliConfig)
    credentials: Optional[Credentials] = None

    @property
    def access_token(self) -> Optional[str]:
        if self.credentials is None:
            return None
        return self.credentials.access_token


def build_context(
    base_url: Optional[str] = None,
    output_format: Optional[str] = None,
    quiet: bool = False,
    verbose: bool = False,
    no_color: bool = False,
    no_pager: bool = False,
) -> CliContext:
    """
    Build CLI context from config file and CLI flags.

    Args:
        base_url: Override server URL
        output_format: human | json
        quiet: Suppress non-essential output
        verbose: Extra diagnostic output
        no_color: Disable Rich styling

    Returns:
        CliContext ready for command handlers
    """
    cfg = load_config()
    creds = load_credentials()

    fmt = output_format or cfg.default_format
    if fmt not in ("human", "json"):
        fmt = "human"

    return CliContext(
        base_url=(base_url or cfg.base_url).rstrip("/"),
        output_format=fmt,
        quiet=quiet,
        verbose=verbose,
        no_color=no_color or not cfg.color,
        no_pager=no_pager,
        config=cfg,
        credentials=creds,
    )
