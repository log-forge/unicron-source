"""
Health check utilities for infrastructure components.

Provides health status for Redis, database, and other services.
"""
import time
from typing import Any


async def check_redis_health() -> dict[str, Any]:
    """
    Check Redis connectivity and performance.

    Returns:
        Dict with status, latency_ms, and used_memory (if healthy)
        or status and error (if unhealthy)
    """
    try:
        from app.core.redis import get_redis

        redis = await get_redis()
        start = time.monotonic()
        await redis.ping()
        latency_ms = (time.monotonic() - start) * 1000

        info = await redis.info("memory")
        used_memory = info.get("used_memory_human", "unknown")

        return {
            "status": "healthy",
            "latency_ms": round(latency_ms, 2),
            "used_memory": used_memory,
        }
    except RuntimeError as e:
        # Redis pool not initialized
        return {
            "status": "not_initialized",
            "error": str(e),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }


async def check_redis_streams_health() -> dict[str, Any]:
    """
    Check Redis Streams health and statistics.

    Returns:
        Dict with stream info for alerts and notifications streams
    """
    try:
        from app.core.config import settings
        from app.services.alerting.streams import get_stream_info, get_consumer_group_info

        alerts_info = await get_stream_info(settings.REDIS_STREAM_ALERTS)
        notifications_info = await get_stream_info(settings.REDIS_STREAM_NOTIFICATIONS)

        alerts_groups = await get_consumer_group_info(settings.REDIS_STREAM_ALERTS)
        notifications_groups = await get_consumer_group_info(settings.REDIS_STREAM_NOTIFICATIONS)

        return {
            "status": "healthy",
            "streams": {
                "alerts": {
                    **alerts_info,
                    "consumer_groups": alerts_groups,
                },
                "notifications": {
                    **notifications_info,
                    "consumer_groups": notifications_groups,
                },
            },
        }
    except RuntimeError as e:
        return {
            "status": "not_initialized",
            "error": str(e),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }


async def get_infrastructure_health() -> dict[str, Any]:
    """
    Get health status of all infrastructure components.

    Returns:
        Dict with health status for each component
    """
    redis_health = await check_redis_health()
    streams_health = await check_redis_streams_health()

    # Overall status is healthy only if all components are healthy
    all_healthy = (
        redis_health.get("status") == "healthy"
        and streams_health.get("status") in ("healthy", "not_initialized")
    )

    return {
        "status": "healthy" if all_healthy else "degraded",
        "components": {
            "redis": redis_health,
            "redis_streams": streams_health,
        },
    }
