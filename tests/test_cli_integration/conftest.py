"""Fixtures for CLI ASGI integration tests."""

from __future__ import annotations

import uuid
from typing import Generator

import pytest

_plugins = ["tests.test_cli.conftest"]
# test_api/conftest.py is auto-loaded when tests/test_api/ is collected; do not
# register it again here (pytest raises ValueError on duplicate plugin registration).
pytest_plugins = _plugins


@pytest.fixture
def patch_httpx_asgi(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route sync httpx.Client calls through Starlette TestClient (ASGI in-process)."""
    from starlette.testclient import TestClient

    from main import app

    test_client = TestClient(app, base_url="http://localhost", raise_server_exceptions=True)

    class _HttpxAsgiBridge:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def request(self, method: str, url: str, **kwargs):
            from urllib.parse import urlparse

            parsed = urlparse(url)
            path = parsed.path or "/"
            return test_client.request(
                method,
                path,
                headers=kwargs.get("headers"),
                json=kwargs.get("json"),
                params=kwargs.get("params"),
                data=kwargs.get("data"),
                files=kwargs.get("files"),
            )

    import httpx

    monkeypatch.setattr(httpx, "Client", _HttpxAsgiBridge)


@pytest.fixture
def cli_user_token() -> Generator[dict, None, None]:
    """Create a real DB user and JWT without dependency overrides."""
    import asyncio

    from sqlalchemy import delete

    from models.database import AuthMethod, User
    from tests.test_api.conftest import _NullSessionLocal, _make_test_jwt

    async def _create() -> dict:
        uid = uuid.uuid4()
        email = f"cliuser_{uid.hex[:8]}@example.com"
        async with _NullSessionLocal() as session:
            session.add(
                User(
                    id=uid,
                    email=email,
                    password_hash="$2b$12$placeholder",
                    auth_method=AuthMethod.LOCAL.value,
                    full_name="CLI Integration User",
                    profile_completed=False,
                    profile_completion_percentage=0,
                )
            )
            await session.commit()
        return {
            "id": uid,
            "email": email,
            "token": _make_test_jwt(str(uid), email),
        }

    async def _cleanup(uid: uuid.UUID) -> None:
        async with _NullSessionLocal() as session:
            await session.execute(delete(User).where(User.id == uid))
            await session.commit()

    loop = asyncio.get_event_loop()
    user = loop.run_until_complete(_create())
    try:
        yield user
    finally:
        loop.run_until_complete(_cleanup(user["id"]))
