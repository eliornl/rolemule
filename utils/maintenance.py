"""
Maintenance mode utilities.

Provides functionality to enable/disable maintenance mode and check status.
Uses Redis for distributed state across multiple instances.
"""

import logging
from typing import Optional

from utils.logging_config import sanitize_log_value

logger = logging.getLogger(__name__)

# Redis key for maintenance mode
MAINTENANCE_KEY = "app:maintenance_mode"
MAINTENANCE_MESSAGE_KEY = "app:maintenance_message"
MAINTENANCE_END_KEY = "app:maintenance_end"


async def is_maintenance_mode() -> bool:
    """
    Check if maintenance mode is enabled.
    
    Returns:
        True if maintenance mode is enabled, False otherwise
    """
    try:
        from utils.redis_client import get_redis_client
        redis_client = await get_redis_client()
        
        if redis_client:
            value = await redis_client.get(MAINTENANCE_KEY)
            return value == "true"
        return False
    except Exception as e:
        logger.error(f"Error checking maintenance mode: {e}", exc_info=True)
        return False


async def get_maintenance_info() -> dict:
    """
    Get maintenance mode information.
    
    Returns:
        Dictionary with enabled status, message, and estimated end time
    """
    try:
        from utils.redis_client import get_redis_client
        redis_client = await get_redis_client()
        
        if redis_client:
            enabled = await redis_client.get(MAINTENANCE_KEY) == "true"
            message = await redis_client.get(MAINTENANCE_MESSAGE_KEY)
            end_time = await redis_client.get(MAINTENANCE_END_KEY)
            
            return {
                "enabled": enabled,
                "message": message or "We're currently performing scheduled maintenance. Please check back soon.",
                "estimated_end": end_time,
            }
        
        return {
            "enabled": False,
            "message": None,
            "estimated_end": None,
        }
    except Exception as e:
        logger.error(f"Error getting maintenance info: {e}", exc_info=True)
        return {
            "enabled": False,
            "message": None,
            "estimated_end": None,
        }


async def enable_maintenance_mode(
    message: Optional[str] = None,
    estimated_end: Optional[str] = None,
) -> bool:
    """
    Enable maintenance mode.
    
    Args:
        message: Custom maintenance message to display
        estimated_end: Estimated end time (ISO format or human-readable)
        
    Returns:
        True if successfully enabled
    """
    try:
        from utils.redis_client import get_redis_client
        redis_client = await get_redis_client()
        
        if redis_client:
            await redis_client.set(MAINTENANCE_KEY, "true")
            
            if message:
                await redis_client.set(MAINTENANCE_MESSAGE_KEY, message)
            else:
                await redis_client.delete(MAINTENANCE_MESSAGE_KEY)
                
            if estimated_end:
                await redis_client.set(MAINTENANCE_END_KEY, estimated_end)
            else:
                await redis_client.delete(MAINTENANCE_END_KEY)
            
            logger.info(
                "Maintenance mode enabled. Message: %s, End: %s",
                sanitize_log_value(message or ""),
                sanitize_log_value(estimated_end or ""),
            )
            return True
        
        logger.warning("Redis not available - maintenance mode not enabled")
        return False
    except Exception as e:
        logger.error(f"Error enabling maintenance mode: {e}", exc_info=True)
        return False


async def disable_maintenance_mode() -> bool:
    """
    Disable maintenance mode.
    
    Returns:
        True if successfully disabled
    """
    try:
        from utils.redis_client import get_redis_client
        redis_client = await get_redis_client()
        
        if redis_client:
            await redis_client.delete(MAINTENANCE_KEY)
            await redis_client.delete(MAINTENANCE_MESSAGE_KEY)
            await redis_client.delete(MAINTENANCE_END_KEY)
            
            logger.info("Maintenance mode disabled")
            return True
        
        logger.warning("Redis not available - maintenance mode not disabled")
        return False
    except Exception as e:
        logger.error(f"Error disabling maintenance mode: {e}", exc_info=True)
        return False


# Paths that should bypass maintenance mode
MAINTENANCE_BYPASS_PATHS = [
    "/api/v1/admin/maintenance",           # Admin maintenance endpoint
    "/api/v1/auth/verify",                 # Token verification (for admin check)
    "/api/v1/internal/workflow/execute",           # Cloud Tasks callbacks must always reach the app
    "/api/v1/internal/workflow/continue",          # Cloud Tasks continuation callbacks
    "/api/v1/admin/internal/cleanup",              # Cloud Scheduler cleanup jobs
    "/api/health",                         # Health check
    "/api/ready",                          # Readiness check
    "/maintenance",                        # Maintenance page itself
    "/static/",                            # Static assets
    "/favicon.ico",                        # Favicon
]


def should_bypass_maintenance(path: str) -> bool:
    """
    Check if a path should bypass maintenance mode.
    
    Args:
        path: Request path
        
    Returns:
        True if the path should bypass maintenance
    """
    for bypass_path in MAINTENANCE_BYPASS_PATHS:
        if path.startswith(bypass_path):
            return True
    return False
