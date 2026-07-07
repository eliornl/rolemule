"""
Redis client utilities for the ApplyPilot.
Provides async Redis connection management with singleton pattern for caching and health monitoring.
"""

import logging
from typing import Optional
import redis.asyncio as redis
from redis.asyncio import Redis
from redis.exceptions import ConnectionError, TimeoutError
from config.settings import get_database_settings, get_settings

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

# Module logger
logger: logging.Logger = logging.getLogger(__name__)

# =============================================================================
# GLOBAL VARIABLES
# =============================================================================

# Global Redis connection instance
# Using singleton pattern for efficient resource management
_redis_client: Optional[Redis] = None

# =============================================================================
# CORE CONNECTION FUNCTIONS
# =============================================================================


async def get_redis_client() -> Redis:
    """
    Get Redis connection dependency for FastAPI endpoints.

    This function provides a singleton Redis connection for use as a FastAPI
    dependency. It ensures efficient resource usage by reusing existing connections
    and automatically initializes the connection if needed.

    Returns:
        Redis: Active Redis connection instance

    Raises:
        ConnectionError: If Redis connection fails
        TimeoutError: If connection establishment times out
        Exception: If connection fails for any other reason
    """
    global _redis_client

    # Initialize connection if not already established
    if _redis_client is None:
        await connect_to_redis()

    return _redis_client


async def connect_to_redis() -> Redis:
    """
    Establish Redis connection with proper configuration and validation.

    This function creates a new Redis connection using redis.asyncio
    with optimized connection parameters. It validates the connection
    and sets up global connection variables.

    Returns:
        Redis: Successfully connected Redis instance

    Raises:
        ConnectionError: If Redis connection fails
        TimeoutError: If connection establishment times out
        Exception: If connection fails due to configuration or network issues
    """
    global _redis_client

    settings = get_settings()
    db_settings = get_database_settings()

    try:
        # Parse Redis URL and create client
        redis_url: str = settings.redis_url

        # Create Redis client with connection parameters
        _redis_client = redis.from_url(redis_url, **db_settings.redis_connection_params)

        # Validate connection and perform health check
        health_check = await check_redis_health()
        if not health_check:
            raise ConnectionError("Redis health check failed")

        logger.info("Connected to Redis successfully and verified connectivity")

        return _redis_client

    except (ConnectionError, TimeoutError) as e:
        logger.error(f"Failed to connect to Redis: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Redis connection error: {e}", exc_info=True)
        raise


async def check_redis_health() -> bool:
    """
    Check Redis connection health and validate connectivity.

    This function performs a health check by attempting to ping the Redis
    server. It's useful for health check endpoints and monitoring systems
    to verify Redis connectivity.

    Returns:
        bool: True if Redis is healthy and responsive, False otherwise

    Raises:
        This function does not raise exceptions - all errors are caught
        and logged, returning False for any health check failures.
    """
    try:
        # Check if Redis client is available
        if not _redis_client:
            logger.warning("Redis health check failed: No active connection")
            return False

        # Ping Redis server to validate connection
        await _redis_client.ping()
        return True

    except Exception as e:
        logger.error(f"Redis health check failed: {e}", exc_info=True)
        return False


async def close_redis_connection() -> None:
    """
    Close Redis connection and clean up resources.

    This function properly closes the Redis connection and resets global
    connection variables. It should be called during application shutdown
    to ensure graceful cleanup of Redis resources.

    Implementation Details:
        - Closes Redis client connection if active
        - Resets global connection variables to None
        - Logs connection closure for monitoring
        - Safe to call multiple times (idempotent)

    Note:
        This function is typically called during application shutdown
        lifecycle events to ensure proper resource cleanup.
    """
    global _redis_client

    # Close client connection if it exists
    if _redis_client is not None:
        await _redis_client.close()
        # Reset global variables to None for clean state
        _redis_client = None
        logger.info("Redis connection closed successfully")
