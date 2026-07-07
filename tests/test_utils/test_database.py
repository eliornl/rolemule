"""Tests for utils/database.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import utils.database as db_mod


@pytest.fixture(autouse=True)
def reset_db_globals():
    db_mod._engine = None
    db_mod._async_session_factory = None
    yield
    db_mod._engine = None
    db_mod._async_session_factory = None


@pytest.mark.asyncio
async def test_check_database_health_no_engine() -> None:
    assert await db_mod.check_database_health() is False


@pytest.mark.asyncio
async def test_check_database_health_ok() -> None:
    conn = AsyncMock()
    conn.execute = AsyncMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    engine = MagicMock()
    engine.begin = MagicMock(return_value=cm)
    db_mod._engine = engine
    assert await db_mod.check_database_health() is True


@pytest.mark.asyncio
async def test_check_database_health_failure() -> None:
    engine = MagicMock()
    engine.begin = MagicMock(side_effect=RuntimeError("db down"))
    db_mod._engine = engine
    assert await db_mod.check_database_health() is False


@pytest.mark.asyncio
async def test_close_database_connection() -> None:
    engine = AsyncMock()
    engine.dispose = AsyncMock()
    db_mod._engine = engine
    db_mod._async_session_factory = MagicMock()
    await db_mod.close_database_connection()
    assert db_mod._engine is None
    engine.dispose.assert_awaited()


@pytest.mark.asyncio
async def test_get_engine_connects_when_missing() -> None:
    mock_engine = MagicMock()
    with patch.object(db_mod, "connect_to_database", AsyncMock()) as connect:
        db_mod._engine = mock_engine
        eng = await db_mod.get_engine()
        assert eng is mock_engine
        connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_session_commits_on_success() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    factory_cm = AsyncMock()
    factory_cm.__aenter__ = AsyncMock(return_value=session)
    factory_cm.__aexit__ = AsyncMock(return_value=False)
    db_mod._async_session_factory = MagicMock(return_value=factory_cm)

    async with db_mod.get_session() as s:
        assert s is session
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_get_session_rolls_back_on_error() -> None:
    session = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    factory_cm = AsyncMock()
    factory_cm.__aenter__ = AsyncMock(return_value=session)
    factory_cm.__aexit__ = AsyncMock(return_value=False)
    db_mod._async_session_factory = MagicMock(return_value=factory_cm)

    with pytest.raises(ValueError) as exc_info:
        async with db_mod.get_session():
            raise ValueError("boom")
    assert str(exc_info.value) == "boom"
    session.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_execute_in_transaction() -> None:
    async def fn(session, x):
        return x * 2

    with patch.object(db_mod, "get_session") as gs:
        session = AsyncMock()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=session)
        cm.__aexit__ = AsyncMock(return_value=False)
        gs.return_value = cm
        result = await db_mod.execute_in_transaction(fn, 21)
        assert result == 42


@pytest.mark.asyncio
async def test_get_engine_triggers_connect() -> None:
    with patch.object(db_mod, "connect_to_database", AsyncMock()) as connect:
        db_mod._engine = None
        await db_mod.get_engine()
        connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_to_database_success() -> None:
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    begin_cm = AsyncMock()
    begin_cm.__aenter__ = AsyncMock(return_value=mock_conn)
    begin_cm.__aexit__ = AsyncMock(return_value=False)
    mock_engine = MagicMock()
    mock_engine.begin = MagicMock(return_value=begin_cm)

    with patch.object(db_mod, "create_async_engine", return_value=mock_engine), \
         patch.object(db_mod, "async_sessionmaker", return_value=MagicMock()), \
         patch("models.database.Base.metadata.create_all", MagicMock()):
        await db_mod.connect_to_database()
        assert db_mod._engine is mock_engine
        assert db_mod._async_session_factory is not None


@pytest.mark.asyncio
async def test_connect_to_database_failure() -> None:
    with patch.object(db_mod, "create_async_engine", side_effect=RuntimeError("db fail")):
        with pytest.raises(RuntimeError, match="db fail"):
            await db_mod.connect_to_database()


@pytest.mark.asyncio
async def test_get_database_yields_session() -> None:
    session = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    factory_cm = AsyncMock()
    factory_cm.__aenter__ = AsyncMock(return_value=session)
    factory_cm.__aexit__ = AsyncMock(return_value=False)
    db_mod._async_session_factory = MagicMock(return_value=factory_cm)

    gen = db_mod.get_database()
    s = await gen.__anext__()
    assert s is session
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()
    await gen.aclose()
    session.close.assert_awaited()


@pytest.mark.asyncio
async def test_get_db_session_connects_when_factory_missing() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    factory_cm = AsyncMock()
    factory_cm.__aenter__ = AsyncMock(return_value=session)
    factory_cm.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=factory_cm)

    async def _connect():
        db_mod._async_session_factory = factory

    with patch.object(db_mod, "connect_to_database", AsyncMock(side_effect=_connect)):
        db_mod._async_session_factory = None
        gen = db_mod.get_db_session()
        s = await gen.__anext__()
        assert s is session
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
        await gen.aclose()
        session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_get_db_session_rolls_back_on_error() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    factory_cm = AsyncMock()
    factory_cm.__aenter__ = AsyncMock(return_value=session)
    factory_cm.__aexit__ = AsyncMock(return_value=False)
    db_mod._async_session_factory = MagicMock(return_value=factory_cm)

    gen = db_mod.get_db_session()
    await gen.__anext__()
    with pytest.raises(ValueError):
        await gen.athrow(ValueError("boom"))
    session.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_get_database_connects_when_factory_missing() -> None:
    session = AsyncMock()
    session.close = AsyncMock()
    factory_cm = AsyncMock()
    factory_cm.__aenter__ = AsyncMock(return_value=session)
    factory_cm.__aexit__ = AsyncMock(return_value=False)

    async def _connect() -> None:
        db_mod._async_session_factory = MagicMock(return_value=factory_cm)

    with patch.object(db_mod, "connect_to_database", AsyncMock(side_effect=_connect)) as connect:
        db_mod._async_session_factory = None
        gen = db_mod.get_database()
        s = await gen.__anext__()
        assert s is session
        connect.assert_awaited_once()
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
        await gen.aclose()


@pytest.mark.asyncio
async def test_get_database_rolls_back_on_error() -> None:
    session = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    factory_cm = AsyncMock()
    factory_cm.__aenter__ = AsyncMock(return_value=session)
    factory_cm.__aexit__ = AsyncMock(return_value=False)
    db_mod._async_session_factory = MagicMock(return_value=factory_cm)

    with pytest.raises(ValueError):
        gen = db_mod.get_database()
        await gen.__anext__()
        await gen.athrow(ValueError("boom"))
    session.rollback.assert_awaited()
