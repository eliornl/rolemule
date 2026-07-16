"""Fixtures for CLI ASGI integration tests."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Generator
from urllib.parse import urlparse

import pytest

logger = logging.getLogger(__name__)

_plugins = ["tests.test_cli.conftest"]
# test_api/conftest.py is auto-loaded when tests/test_api/ is collected; do not
# register it again here (pytest raises ValueError on duplicate plugin registration).
pytest_plugins = _plugins


def _session_loop() -> asyncio.AbstractEventLoop:
    """
    Return the pytest-asyncio session loop when available.

    Do not create a new loop after async tests have bound the NullPool engine /
    asyncpg driver to the session loop - Starlette TestClient does that and
    causes "Event loop is closed" / "Future attached to a different loop".
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


def _run_on_session_loop(coro):
    loop = _session_loop()
    if loop.is_running():
        # Sync code called from inside a running loop (rare for these tests).
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:

            def _in_thread():
                fresh = asyncio.new_event_loop()
                try:
                    return fresh.run_until_complete(coro)
                finally:
                    fresh.close()

            return pool.submit(_in_thread).result()
    return loop.run_until_complete(coro)


@pytest.fixture
def patch_httpx_asgi(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Route sync httpx.Client through httpx.ASGITransport on the session event loop.

    Avoids Starlette TestClient's private anyio loop, which conflicts with
    pytest-asyncio's session-scoped loop after tests/test_api has run.
    """
    import httpx
    from httpx import ASGITransport, AsyncClient

    from main import app

    class _HttpxAsgiBridge:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def request(self, method: str, url: str, **kwargs):
            parsed = urlparse(url)
            path = parsed.path or "/"
            if parsed.query:
                path = f"{path}?{parsed.query}"

            async def _request():
                transport = ASGITransport(app=app)
                async with AsyncClient(
                    transport=transport, base_url="http://localhost"
                ) as ac:
                    return await ac.request(
                        method,
                        path,
                        headers=kwargs.get("headers"),
                        json=kwargs.get("json"),
                        params=kwargs.get("params"),
                        data=kwargs.get("data"),
                        files=kwargs.get("files"),
                    )

            return _run_on_session_loop(_request())

    monkeypatch.setattr(httpx, "Client", _HttpxAsgiBridge)


@pytest.fixture
def cli_user_token() -> Generator[dict, None, None]:
    """Create a real DB user and JWT without dependency overrides."""
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

    user = _run_on_session_loop(_create())
    try:
        yield user
    finally:
        try:
            _run_on_session_loop(_cleanup(user["id"]))
        except Exception:
            # Teardown must not fail the test if the user row is already gone.
            logger.debug("cli integration fixture cleanup failed", exc_info=True)
