"""Redis-backed delivery rate limiting for notifier workers."""

from __future__ import annotations

import time
from typing import Iterable, Tuple

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.models.channel_model import NotificationChannel

logger = get_logger("notifier.services.rate_limit")


class NotificationRateLimitExceeded(RuntimeError):
    """Raised when notifier delivery limits are exceeded."""


def _rate_limit_entries(
    channel: NotificationChannel, window_bucket: int
) -> Iterable[Tuple[str, str, int]]:
    yield (
        "global",
        f"notifier:ratelimit:global:{window_bucket}",
        int(settings.NOTIFIER_RATE_LIMIT_GLOBAL_PER_WINDOW),
    )
    yield (
        "channel_type",
        f"notifier:ratelimit:type:{channel.channel_type}:{window_bucket}",
        int(settings.NOTIFIER_RATE_LIMIT_CHANNEL_TYPE_PER_WINDOW),
    )
    yield (
        "channel",
        f"notifier:ratelimit:channel:{channel.id}:{window_bucket}",
        int(settings.NOTIFIER_RATE_LIMIT_CHANNEL_PER_WINDOW),
    )


async def enforce_delivery_rate_limit(channel: NotificationChannel) -> None:
    """Raise if current delivery would exceed configured limits."""
    if not settings.NOTIFIER_RATE_LIMIT_ENABLED:
        return

    window_seconds = max(1, int(settings.NOTIFIER_RATE_LIMIT_WINDOW_SECONDS))
    window_bucket = int(time.time() // window_seconds)
    entries = list(_rate_limit_entries(channel, window_bucket))

    try:
        redis_client = await get_redis()
        async with redis_client.pipeline(transaction=False) as pipe:
            for _scope, key, _limit in entries:
                await pipe.incr(key)
                await pipe.expire(key, window_seconds + 5)
            raw_results = await pipe.execute()
    except redis.ConnectionError as exc:
        # Fail open: avoid dropping notifications when Redis is degraded.
        logger.warning("Rate limit check skipped due to Redis error: %s", exc)
        return
    except Exception as exc:
        logger.warning("Rate limit check skipped due to unexpected error: %s", exc)
        return

    for idx, (scope, _key, limit) in enumerate(entries):
        if limit <= 0:
            continue
        count = int(raw_results[idx * 2] or 0)
        if count > limit:
            raise NotificationRateLimitExceeded(
                f"rate_limit_exceeded scope={scope} count={count} limit={limit}"
            )

