"""Unit tests for cli/context.py."""

from __future__ import annotations

from cli.config import CliConfig, save_config
from cli.context import build_context


def test_build_context_defaults(rolemule_home) -> None:
    ctx = build_context()
    assert ctx.base_url.startswith("http")
    assert ctx.output_format == "human"


def test_build_context_format_json(rolemule_home) -> None:
    ctx = build_context(output_format="json")
    assert ctx.output_format == "json"


def test_build_context_invalid_format_falls_back_human(rolemule_home) -> None:
    ctx = build_context(output_format="xml")
    assert ctx.output_format == "human"


def test_build_context_base_url_override(rolemule_home) -> None:
    ctx = build_context(base_url="http://custom:9000/")
    assert ctx.base_url == "http://custom:9000"


def test_build_context_loads_saved_config(rolemule_home) -> None:
    save_config(CliConfig(base_url="http://saved:8080", default_format="json"))
    ctx = build_context()
    assert ctx.base_url == "http://saved:8080"
    assert ctx.output_format == "json"


def test_build_context_loads_credentials(rolemule_home, write_credentials) -> None:
    write_credentials(token="my.jwt.token")
    ctx = build_context()
    assert ctx.access_token == "my.jwt.token"
