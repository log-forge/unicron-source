"""Deduplication service for alert-engine.

Provides fingerprint generation and Redis-backed deduplication cache
to suppress duplicate alerts within a configurable time window.
"""

import hashlib
import json
from typing import Any, Dict

import redis.asyncio as redis

from app.core.logging import get_logger

logger = get_logger("alert-engine.services.dedup")

# Default deduplication window in seconds (15 minutes)
DEFAULT_DEDUP_WINDOW_SECONDS = 900


def generate_fingerprint(
    rule_id: str,
    scope: str,
    labels: Dict[str, Any],
) -> str:
    """
    Generate SHA256[:16] fingerprint for deduplication.

    The fingerprint uniquely identifies an alert condition based on:
    - rule_id: The alert rule that triggered
    - scope: The scope type (global, container, group, herald)
    - labels: Alert labels that differentiate instances

    Args:
        rule_id: The unique identifier of the alert rule.
        scope: The scope type for the alert.
        labels: Dictionary of labels (sorted for consistency).

    Returns:
        16-character hex string (first 16 chars of SHA256 hash).
    """
    # Normalize labels: convert all values to strings and sort keys
    normalized_labels = {k: str(v) for k, v in sorted(labels.items())}

    data = {
        "rule_id": rule_id,
        "scope": scope,
        "labels": normalized_labels,
    }

    # Create deterministic JSON string
    json_str = json.dumps(data, sort_keys=True, separators=(",", ":"))

    # Return first 16 chars of SHA256 hash (matches Phase 1 AlertState.fingerprint)
    return hashlib.sha256(json_str.encode()).hexdigest()[:16]


class DeduplicationService:
    """
    Redis-backed deduplication for alert suppression.

    Uses Redis SET NX (set if not exists) with TTL expiration to
    implement a fixed-window deduplication cache. Duplicate alerts
    within the window are suppressed without extending the TTL.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        window_seconds: int = DEFAULT_DEDUP_WINDOW_SECONDS,
        enabled: bool = True,
    ):
        """
        Initialize the deduplication service.

        Args:
            redis_client: Async Redis client instance.
            window_seconds: Deduplication window in seconds (default 900 = 15 min).
            enabled: Whether deduplication suppression is enabled.
        """
        self.redis = redis_client
        self.window_seconds = max(1, int(window_seconds))
        self.enabled = bool(enabled)

    def _get_key(self, fingerprint: str) -> str:
        """Get Redis key for a fingerprint."""
        return f"alert:dedup:{fingerprint}"

    async def is_duplicate(self, fingerprint: str) -> bool:
        """
        Check if an alert with this fingerprint already exists.

        Args:
            fingerprint: The alert fingerprint to check.

        Returns:
            True if fingerprint exists in cache (duplicate), False otherwise.
        """
        if not self.enabled:
            return False

        key = self._get_key(fingerprint)
        exists = await self.redis.exists(key)
        return bool(exists)

    async def record_alert(self, fingerprint: str) -> None:
        """
        Record an alert fingerprint in the cache.

        Sets the fingerprint in Redis with TTL = window_seconds.

        Args:
            fingerprint: The alert fingerprint to record.
        """
        if not self.enabled:
            return

        key = self._get_key(fingerprint)
        await self.redis.set(key, "1", ex=self.window_seconds)
        logger.debug("Recorded alert fingerprint: %s (TTL: %ds)", fingerprint, self.window_seconds)

    async def check_and_record(self, fingerprint: str) -> bool:
        """
        Atomic check-and-set operation for deduplication.

        Uses Redis SET NX (set if not exists) with TTL for atomic
        deduplication. This prevents race conditions when multiple
        evaluation cycles could fire the same alert.

        Args:
            fingerprint: The alert fingerprint to check and record.

        Returns:
            True if this is a duplicate (already exists), False if new.
        """
        if not self.enabled:
            return False

        key = self._get_key(fingerprint)

        # SET NX returns True if key was set (new alert), False if existed (duplicate)
        was_set = await self.redis.set(key, "1", nx=True, ex=self.window_seconds)

        if was_set:
            logger.debug("New alert fingerprint recorded: %s", fingerprint)
            return False  # Not a duplicate
        else:
            logger.debug("Duplicate alert suppressed: %s", fingerprint)
            return True  # Is a duplicate

    async def clear(self, fingerprint: str) -> bool:
        """
        Clear a fingerprint from the deduplication cache.

        Useful when an alert is resolved and should fire again if
        the condition reoccurs.

        Args:
            fingerprint: The alert fingerprint to clear.

        Returns:
            True if fingerprint was cleared, False if it didn't exist.
        """
        key = self._get_key(fingerprint)
        deleted = await self.redis.delete(key)
        if deleted:
            logger.debug("Cleared alert fingerprint: %s", fingerprint)
        return bool(deleted)


__all__ = ["DeduplicationService", "generate_fingerprint", "DEFAULT_DEDUP_WINDOW_SECONDS"]
