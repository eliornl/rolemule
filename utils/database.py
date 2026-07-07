"""
Database utilities for the ApplyPilot.
Provides PostgreSQL connection management with SQLAlchemy async, health monitoring, and session management.
"""

import logging
from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy import text

from config.settings import get_settings, get_database_settings

# =============================================================================
# CONFIGURATION
# =============================================================================

# Module logger
logger: logging.Logger = logging.getLogger(__name__)

# =============================================================================
# GLOBAL VARIABLES
# =============================================================================

# Global database connection instances
# Using singleton pattern for efficient resource management
_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None

# =============================================================================
# CORE DATABASE FUNCTIONS
# =============================================================================


async def get_engine() -> AsyncEngine:
    """
    Get or create the SQLAlchemy async engine.

    Returns:
        AsyncEngine: SQLAlchemy async engine instance
    """
    global _engine

    if _engine is None:
        await connect_to_database()

    return _engine


async def get_database() -> AsyncSession:
    """
    Get database session dependency for FastAPI endpoints.

    This function provides a database session for use as a FastAPI
    dependency. It ensures efficient resource usage by using the
    session factory pattern.

    Returns:
        AsyncSession: Active PostgreSQL database session

    Raises:
        Exception: If database connection fails
    """
    global _async_session_factory

    if _async_session_factory is None:
        await connect_to_database()

    async with _async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Alternative session getter that yields a session.
    Used for background tasks and non-FastAPI contexts.

    Yields:
        AsyncSession: Database session
    """
    global _async_session_factory

    if _async_session_factory is None:
        await connect_to_database()

    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database sessions.
    Used in background tasks and standalone operations.

    Usage:
        async with get_session() as session:
            result = await session.execute(query)

    Yields:
        AsyncSession: Database session with auto-commit/rollback
    """
    global _async_session_factory

    if _async_session_factory is None:
        await connect_to_database()

    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def connect_to_database() -> None:
    """
    Establish PostgreSQL connection with proper configuration and validation.

    This function creates a new PostgreSQL connection using SQLAlchemy async
    with optimized connection parameters. It validates the connection and
    sets up global connection variables.

    Raises:
        Exception: If connection fails due to authentication, network, or configuration issues
    """
    global _engine, _async_session_factory

    get_settings()
    db_settings = get_database_settings()

    try:
        # Create async engine with connection pool
        _engine = create_async_engine(
            db_settings.async_database_url,
            echo=False,
            **db_settings.connection_pool_params,
        )

        # Create async session factory
        _async_session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

        # Validate connection with a simple query
        async with _engine.begin() as conn:
            await conn.execute(text("SELECT 1"))

        logger.info("Successfully connected to PostgreSQL database")

        # Import and create tables
        from models.database import Base
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("Database tables created/verified successfully")

    except Exception as e:
        logger.error(f"Database connection failed: {e}", exc_info=True)
        raise


async def check_database_health() -> bool:
    """
    Perform database health check and connection validation.

    This function validates the current database connection by executing
    a simple query. It's useful for health check endpoints and monitoring
    systems to verify database connectivity.

    Returns:
        bool: True if database is healthy and responsive, False otherwise
    """
    try:
        if _engine is None:
            logger.warning("Database health check failed: No active connection")
            return False

        async with _engine.begin() as conn:
            await conn.execute(text("SELECT 1"))

        return True

    except Exception as e:
        logger.error(f"Database health check failed: {e}", exc_info=True)
        return False


async def close_database_connection() -> None:
    """
    Close database connection and clean up resources.

    This function properly closes the PostgreSQL connection and resets global
    connection variables. It should be called during application shutdown
    to ensure graceful cleanup of database resources.
    """
    global _engine, _async_session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        logger.info("Database connection closed successfully")


# =============================================================================
# TRANSACTION HELPERS
# =============================================================================


async def execute_in_transaction(func, *args, **kwargs):
    """
    Execute a function within a database transaction.

    Args:
        func: Async function that takes a session as first argument
        *args: Additional positional arguments for func
        **kwargs: Additional keyword arguments for func

    Returns:
        Result of the function execution
    """
    async with get_session() as session:
        return await func(session, *args, **kwargs)
