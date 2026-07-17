"""Tests for cli.config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli.config import (
    CliConfig,
    Credentials,
    clear_credentials,
    config_path,
    credentials_path,
    load_config,
    load_credentials,
    mask_token,
    save_config,
    save_credentials,
)


def test_load_config_defaults(rolemule_home: Path) -> None:
    cfg = load_config()
    assert cfg.base_url == "http://localhost:8000"
    assert cfg.default_format == "human"
    assert cfg.poll_interval_seconds == 3


def test_save_and_load_config(rolemule_home: Path) -> None:
    pytest.importorskip("tomli_w")
    cfg = CliConfig(base_url="http://example.com:9000", default_format="json")
    save_config(cfg)
    loaded = load_config()
    assert loaded.base_url == "http://example.com:9000"
    assert loaded.default_format == "json"
    assert config_path().is_file()


def test_credentials_round_trip(rolemule_home: Path) -> None:
    creds = Credentials(access_token="abc.def.ghi", email="a@b.com", saved_at="2026-01-01T00:00:00Z")
    save_credentials(creds)
    path = credentials_path()
    assert path.is_file()
    assert oct(path.stat().st_mode & 0o777) == oct(0o600)

    loaded = load_credentials()
    assert loaded is not None
    assert loaded.access_token == "abc.def.ghi"
    assert loaded.email == "a@b.com"


def test_clear_credentials(rolemule_home: Path) -> None:
    save_credentials(Credentials(access_token="x"))
    clear_credentials()
    assert load_credentials() is None


def test_load_credentials_invalid(rolemule_home: Path) -> None:
    credentials_path().write_text(json.dumps({"email": "only"}), encoding="utf-8")
    with pytest.raises(ValueError, match="access_token"):
        load_credentials()


def test_mask_token() -> None:
    assert mask_token("short") == "***"
    assert mask_token("abcdefghijklmnopqrst") == "abcd...qrst"
