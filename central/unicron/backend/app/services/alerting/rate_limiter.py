"""
Rate limiting using Redis sliding window.

Prevents notification channel exhaustion during alert storms.
"""
from app.core.config import settings
from app.core.redis import get_redis


async def check_rate_limit(
    key: str,
    limit: int,
    window_seconds: int | None = None,
) -> tuple[bool, int]:
    """
    Check if rate limit exceeded using sliding window counter.

    Uses INCR + EXPIRE for simple but effective rate limiting.
    The window resets after the first request in a new window.

    Args:
        key: Rate limit key (will be prefixed with alerting:ratelimit:)
        limit: Maximum requests allowed per window
        window_seconds: Window duration, defaults to REDIS_RATE_LIMIT_WINDOW_SECONDS

    Returns:
        (allowed: bool, current_count: int)
    """
    redis = await get_redis()
    window = window_seconds or settings.REDIS_RATE_LIMIT_WINDOW_SECONDS
    redis_key = f"alerting:ratelimit:{key}"

    # Sliding window counter using INCR + EXPIRE
    pipe = redis.pipeline()
    pipe.incr(redis_key)
    pipe.expire(redis_key, window)
    results = await pipe.execute()

    current = results[0]
    allowed = current <= limit

    return allowed, current


async def get_rate_limit_status(key: str) -> int:
    """
    Get current count for rate limit key.

    Args:
        key: Rate limit key (will be prefixed with alerting:ratelimit:)

    Returns:
        Current count, or 0 if not found
    """
    redis = await get_redis()
    redis_key = f"alerting:ratelimit:{key}"
    count = await redis.get(redis_key)
    return int(count) if count else 0


async def get_rate_limit_ttl(key: str) -> int | None:
    """
    Get remaining TTL for rate limit window.

    Args:
        key: Rate limit key (will be prefixed with alerting:ratelimit:)

    Returns:
        Remaining TTL in seconds, or None if not found
    """
    redis = await get_redis()
    redis_key = f"alerting:ratelimit:{key}"
    ttl = await redis.ttl(redis_key)
    return ttl if ttl > 0 else None


async def reset_rate_limit(key: str) -> None:
    """
    Reset rate limit counter (for testing or admin override).

    Args:
        key: Rate limit key (will be prefixed with alerting:ratelimit:)
    """
    redis = await get_redis()
    redis_key = f"alerting:ratelimit:{key}"
    await redis.delete(redis_key)


class RateLimitKeys:
    """Rate limit key generators for consistent naming."""

    @staticmethod
    def channel(channel_id: str) -> str:
        """Generate rate limit key for notification channel."""
        return f"channel:{channel_id}"

    @staticmethod
    def user(user_id: str) -> str:
        """Generate rate limit key for user notifications."""
        return f"user:{user_id}"

    @staticmethod
    def organization(org_id: str) -> str:
        """Generate rate limit key for organization-wide alerts."""
        return f"org:{org_id}"

    @staticmethod
    def global_alerts() -> str:
        """Generate rate limit key for global alert throughput."""
        return "global:alerts"

    @staticmethod
    def rule(rule_id: str) -> str:
        """Generate rate limit key for specific alert rule."""
        return f"rule:{rule_id}"
