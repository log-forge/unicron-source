"""
Alert deduplication using Redis.

Prevents alert storms by caching fingerprints with TTL.
Fingerprint = hash(rule_id + scope + labels)
"""
import hashlib
import json
from typing import Any

from app.core.config import settings
from app.core.redis import get_redis


def compute_fingerprint(rule_id: str, scope: dict[str, Any], labels: dict[str, Any]) -> str:
    """
    Generate deterministic fingerprint for alert deduplication.

    Args:
        rule_id: The alert rule identifier
        scope: Container/group scope for the alert
        labels: Additional labels identifying the alert instance

    Returns:
        16-character hex fingerprint
    """
    data = json.dumps(
        {
            "rule_id": rule_id,
            "scope": scope,
            "labels": labels,
        },
        sort_keys=True,
    )
    return hashlib.sha256(data.encode()).hexdigest()[:16]


async def is_duplicate(fingerprint: str) -> bool:
    """
    Check if alert fingerprint exists in dedup cache.

    Args:
        fingerprint: The alert fingerprint to check

    Returns:
        True if fingerprint exists (duplicate), False otherwise
    """
    redis = await get_redis()
    key = f"alerting:dedup:{fingerprint}"
    return bool(await redis.exists(key))


async def mark_seen(fingerprint: str, ttl_seconds: int | None = None) -> None:
    """
    Mark fingerprint as seen with TTL.

    Args:
        fingerprint: The alert fingerprint to mark
        ttl_seconds: Optional custom TTL, defaults to REDIS_DEDUP_TTL_SECONDS
    """
    redis = await get_redis()
    key = f"alerting:dedup:{fingerprint}"
    ttl = ttl_seconds or settings.REDIS_DEDUP_TTL_SECONDS
    await redis.setex(key, ttl, "1")


async def clear_fingerprint(fingerprint: str) -> None:
    """
    Clear fingerprint for alerts that should be allowed to fire again.

    Args:
        fingerprint: The alert fingerprint to clear
    """
    redis = await get_redis()
    key = f"alerting:dedup:{fingerprint}"
    await redis.delete(key)


async def get_dedup_ttl(fingerprint: str) -> int | None:
    """
    Get remaining TTL for a fingerprint.

    Args:
        fingerprint: The alert fingerprint to check

    Returns:
        Remaining TTL in seconds, or None if not found
    """
    redis = await get_redis()
    key = f"alerting:dedup:{fingerprint}"
    ttl = await redis.ttl(key)
    return ttl if ttl > 0 else None
