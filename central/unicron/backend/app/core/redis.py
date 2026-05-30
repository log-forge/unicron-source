"""
Redis connection management for alerting infrastructure.

Provides:
- Connection pooling for high concurrency
- Separate clients for different use cases (cache, streams, pubsub)
- Health check utilities
"""
import redis.asyncio as redis

from app.core.config import settings

# Connection pool for general operations (cache, rate limiting)
redis_pool: redis.ConnectionPool | None = None

# Dedicated client for Socket.IO adapter
socketio_redis: redis.Redis | None = None


async def init_redis() -> None:
    """Initialize Redis connections on startup."""
    global redis_pool, socketio_redis

    redis_pool = redis.ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        decode_responses=True,
    )

    # Socket.IO needs dedicated connection
    if settings.SOCKETIO_REDIS_URL:
        socketio_redis = redis.Redis.from_url(
            settings.SOCKETIO_REDIS_URL,
            decode_responses=True,
        )


async def get_redis() -> redis.Redis:
    """Get Redis client from pool."""
    if redis_pool is None:
        raise RuntimeError("Redis pool not initialized. Call init_redis() first.")
    return redis.Redis(connection_pool=redis_pool)


async def close_redis() -> None:
    """Close Redis connections on shutdown."""
    global redis_pool, socketio_redis

    if redis_pool:
        await redis_pool.disconnect()
        redis_pool = None

    if socketio_redis:
        await socketio_redis.close()
        socketio_redis = None
