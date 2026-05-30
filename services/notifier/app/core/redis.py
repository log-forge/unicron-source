"""Redis client module for notifier service.

Provides async Redis client for caching, deduplication, and Celery broker.

Connection Resilience:
- Retries with exponential backoff on startup
- Auto-reconnect on connection loss
- 2-minute timeout before giving up
"""

from typing import Optional

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger
from app.core.retry import retry_connection

logger = get_logger("notifier.core.redis")

# Module-level Redis pool (singleton pattern)
_redis_pool: Optional[redis.Redis] = None


def _read_socket_timeout_seconds() -> float:
    """Return a safe Redis read timeout for stream long-polling."""
    block_seconds = max(0.0, settings.REDIS_CONSUMER_BLOCK_MS / 1000.0)
    configured = max(0.0, float(settings.REDIS_SOCKET_TIMEOUT_SECONDS))
    # Keep read timeout slightly above BLOCK so idle polls don't raise spurious errors.
    return max(configured, block_seconds + 1.0)


async def _create_redis_client() -> redis.Redis:
    """Create and verify Redis connection."""
    read_timeout = _read_socket_timeout_seconds()
    client = redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        socket_timeout=read_timeout,
        socket_connect_timeout=float(settings.REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS),
        retry_on_timeout=True,
    )
    # Verify connection works
    await client.ping()
    return client


async def init_redis() -> redis.Redis:
    """
    Initialize Redis connection with retry logic.

    Called during application startup. Retries with exponential
    backoff if Redis isn't immediately available.

    Returns:
        Connected Redis client.

    Raises:
        ConnectionError: If connection cannot be established after 2 minutes.
    """
    global _redis_pool

    _redis_pool = await retry_connection(_create_redis_client, "Redis")
    logger.info("Redis connection pool initialized")
    return _redis_pool


async def get_redis() -> redis.Redis:
    """
    Get the shared Redis client instance.

    Returns:
        Async Redis client connected to configured REDIS_URL.

    Note:
        Creates connection pool on first call if not already initialized.
        For production, call init_redis() during startup instead.
    """
    global _redis_pool

    if _redis_pool is None:
        # Fallback for backward compatibility - init without retry
        read_timeout = _read_socket_timeout_seconds()
        _redis_pool = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            socket_timeout=read_timeout,
            socket_connect_timeout=float(settings.REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS),
            retry_on_timeout=True,
        )
        logger.info("Redis connection pool initialized (lazy)")

    return _redis_pool


async def close_redis() -> None:
    """
    Close the Redis connection pool.

    Called during application shutdown to gracefully release connections.
    """
    global _redis_pool

    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None
        logger.info("Redis connection pool closed")


__all__ = ["init_redis", "get_redis", "close_redis"]
