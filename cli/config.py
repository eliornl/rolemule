# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import tomllib
except ImportError:  # pragma: no cover — Python < 3.11
    tomllib = None  # type: ignore[assignment]

try:
    import tomli_w
except ImportError:  # pragma: no cover — optional until [cli] installed
    tomli_w = None  # type: ignore[assignment]

CONFIG_DIR_ENV = "APPLYPILOT_CONFIG_DIR"
DEFAULT_CONFIG_DIR = Path.home() / ".applypilot"
CONFIG_FILENAME = "config.toml"
CREDENTIALS_FILENAME = "credentials.json"

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_POLL_INTERVAL = 3
DEFAULT_POLL_TIMEOUT = 600


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


@dataclass
class CliConfig:
    """Loaded CLI configuration."""

    base_url: str = DEFAULT_BASE_URL
    default_format: str = "human"
    color: bool = True
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL
    poll_timeout_seconds: int = DEFAULT_POLL_TIMEOUT


@dataclass
class Credentials:
    """Stored auth credentials."""

    access_token: str
    token_type: str = "bearer"
    email: Optional[str] = None
    saved_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "email": self.email,
            "saved_at": self.saved_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Credentials":
        token = data.get("access_token")
        if not token or not isinstance(token, str):
            raise ValueError("credentials file missing access_token")
        return cls(
            access_token=token,
            token_type=str(data.get("token_type") or "bearer"),
            email=data.get("email"),
            saved_at=data.get("saved_at"),
        )


def config_dir() -> Path:
    """Resolve config directory (~/.applypilot or APPLYPILOT_CONFIG_DIR)."""
    override = os.environ.get(CONFIG_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return DEFAULT_CONFIG_DIR


def config_path() -> Path:
    return config_dir() / CONFIG_FILENAME


def credentials_path() -> Path:
    return config_dir() / CREDENTIALS_FILENAME


def ensure_config_dir() -> Path:
    """Create config directory if missing."""
    path = config_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_config() -> CliConfig:
    """
    Load config.toml or return defaults.

    Returns:
        CliConfig instance
    """
    path = config_path()
    if not path.is_file() or tomllib is None:
        return CliConfig()

    with path.open("rb") as fh:
        data = tomllib.load(fh)

    server = data.get("server") or {}
    output = data.get("output") or {}
    cli = data.get("cli") or {}

    return CliConfig(
        base_url=str(server.get("base_url") or DEFAULT_BASE_URL).rstrip("/"),
        default_format=str(output.get("default_format") or "human"),
        color=bool(output.get("color", True)),
        poll_interval_seconds=int(cli.get("poll_interval_seconds") or DEFAULT_POLL_INTERVAL),
        poll_timeout_seconds=int(cli.get("poll_timeout_seconds") or DEFAULT_POLL_TIMEOUT),
    )


def save_config(cfg: CliConfig) -> None:
    """Write config.toml."""
    if tomli_w is None:
        raise RuntimeError("tomli-w is required to save config (pip install applypilot[cli])")

    ensure_config_dir()
    payload = {
        "server": {"base_url": cfg.base_url},
        "output": {
            "default_format": cfg.default_format,
            "color": cfg.color,
        },
        "cli": {
            "poll_interval_seconds": cfg.poll_interval_seconds,
            "poll_timeout_seconds": cfg.poll_timeout_seconds,
        },
    }
    with config_path().open("wb") as fh:
        tomli_w.dump(payload, fh)


def load_credentials() -> Optional[Credentials]:
    """Load credentials.json if present."""
    path = credentials_path()
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return Credentials.from_dict(data)


def save_credentials(creds: Credentials) -> None:
    """Write credentials.json with mode 0600."""
    ensure_config_dir()
    path = credentials_path()
    with path.open("w", encoding="utf-8") as fh:
        json.dump(creds.to_dict(), fh, indent=2)
        fh.write("\n")
    path.chmod(0o600)


def clear_credentials() -> None:
    """Remove credentials file if it exists."""
    path = credentials_path()
    if path.is_file():
        path.unlink()


def mask_token(token: str, visible: int = 4) -> str:
    """Return a masked token for display."""
    if len(token) <= visible * 2:
        return "***"
    return f"{token[:visible]}...{token[-visible:]}"
