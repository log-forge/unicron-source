"""
Socket.IO Redis adapter for horizontal scaling.

Enables multiple backend instances to share Socket.IO state
and broadcast messages across instances.
"""
from typing import Any

from app.core.config import settings


def create_socketio_manager() -> Any | None:
    """
    Create Redis-backed Socket.IO manager.

    Used when SOCKETIO_REDIS_URL is configured to enable horizontal
    scaling of Socket.IO across multiple backend instances.

    Returns:
        AsyncRedisManager if SOCKETIO_REDIS_URL is set, None otherwise
    """
    redis_url = settings.SOCKETIO_REDIS_URL
    if not redis_url:
        return None

    # Import here to avoid dependency when not using Redis adapter
    from socketio import AsyncRedisManager

    return AsyncRedisManager(redis_url, write_only=False)


def get_socketio_adapter_url() -> str | None:
    """
    Get the Redis URL for Socket.IO adapter.

    Returns:
        Redis URL string if configured, None otherwise
    """
    return settings.SOCKETIO_REDIS_URL or None


def is_socketio_clustered() -> bool:
    """
    Check if Socket.IO is configured for horizontal scaling.

    Returns:
        True if SOCKETIO_REDIS_URL is set
    """
    return bool(settings.SOCKETIO_REDIS_URL)
