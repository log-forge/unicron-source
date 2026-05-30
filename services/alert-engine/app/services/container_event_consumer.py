"""Redis Streams consumer for container lifecycle event processing.

Consumes container lifecycle events from Redis Stream (published by Central
when go-streamer reports Docker events) and evaluates stability rules
(restart loop, crash loop, failed start) in real-time.

Pipeline flow:
    go-streamer -> Central WebSocket -> Redis Stream (unicron:events)
    -> ContainerEventConsumer -> RuleMatcher.evaluate_container_event()
    -> Stability template evaluation -> Alert triggering
"""

import asyncio
import json
import socket
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.services.stream_reliability import extract_claimed_messages, publish_dlq

if TYPE_CHECKING:
    from app.services.rule_matcher import RuleMatcher

logger = get_logger("alert-engine.services.container_event_consumer")


class ContainerEventConsumer:
    """
    Redis Streams consumer for container lifecycle event evaluation.

    Single consumer (not horizontally scaled) to enforce strict per-container
    event ordering. Container events are low-frequency (~100-1000/hour)
    so a single consumer is sufficient.
    """

    def __init__(self):
        """Initialize the container event consumer."""
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._consumer_name = f"alert-engine-event-{socket.gethostname()}"
        self._rule_matcher: Optional["RuleMatcher"] = None
        self._last_reclaim_at: float = 0.0
        self._reclaim_cursor: str = "0-0"
        self._stats: dict[str, int] = {
            "processed_total": 0,
            "acked_total": 0,
            "failed_total": 0,
            "parse_dropped_total": 0,
            "reclaimed_total": 0,
            "dlq_published_total": 0,
        }

    @property
    def is_running(self) -> bool:
        """Check if consumer is currently running."""
        return self._running

    def get_stats_snapshot(self) -> dict[str, int]:
        """Return a point-in-time copy of runtime processing counters."""
        return dict(self._stats)

    async def start(self, rule_matcher=None) -> None:
        """
        Start the container event consumer as a background task.

        Args:
            rule_matcher: RuleMatcher instance for container event evaluation.
        """
        if self._running:
            logger.warning("Container event consumer already running")
            return

        self._rule_matcher = rule_matcher

        # Ensure consumer group exists
        await self._ensure_consumer_group()

        # Start consumer loop as background task
        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
        logger.info(
            "Container event consumer started: stream=%s, group=%s, consumer=%s",
            settings.REDIS_STREAM_EVENTS,
            settings.REDIS_EVENT_CONSUMER_GROUP,
            self._consumer_name,
        )

    async def stop(self, timeout: float = 10.0) -> None:
        """
        Stop the container event consumer gracefully.

        Args:
            timeout: Maximum seconds to wait for graceful shutdown.
        """
        if not self._running:
            return

        logger.info("Stopping container event consumer...")
        self._running = False

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning("Container event consumer shutdown timed out, cancelling")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        logger.info("Container event consumer stopped")

    async def _ensure_consumer_group(self) -> None:
        """Create consumer group if it doesn't exist."""
        redis = await get_redis()
        try:
            await redis.xgroup_create(
                settings.REDIS_STREAM_EVENTS,
                settings.REDIS_EVENT_CONSUMER_GROUP,
                id="0",
                mkstream=True,
            )
            logger.info(
                "Created event consumer group: %s", settings.REDIS_EVENT_CONSUMER_GROUP
            )
        except Exception as e:
            if "BUSYGROUP" in str(e):
                logger.debug(
                    "Event consumer group already exists: %s",
                    settings.REDIS_EVENT_CONSUMER_GROUP,
                )
            else:
                raise

    async def _consume_loop(self) -> None:
        """Main consumption loop - reads and processes container events."""
        redis = await get_redis()

        while self._running:
            try:
                await self._maybe_reclaim(redis)

                messages = await redis.xreadgroup(
                    groupname=settings.REDIS_EVENT_CONSUMER_GROUP,
                    consumername=self._consumer_name,
                    streams={settings.REDIS_STREAM_EVENTS: ">"},
                    count=settings.REDIS_EVENT_CONSUMER_BATCH_SIZE,
                    block=settings.REDIS_EVENT_CONSUMER_BLOCK_MS,
                )

                if not messages:
                    continue

                for stream_name, stream_messages in messages:
                    await self._process_batch(redis, stream_messages)

            except asyncio.CancelledError:
                logger.info("Container event consumer loop cancelled")
                break
            except Exception as e:
                logger.error("Error in container event consumer loop: %s", str(e))
                await asyncio.sleep(1.0)

    async def _maybe_reclaim(self, redis) -> None:
        """Periodically reclaim stale pending messages with XAUTOCLAIM."""
        if not settings.REDIS_RECLAIM_ENABLED:
            return

        now = time.monotonic()
        if now - self._last_reclaim_at < settings.REDIS_RECLAIM_INTERVAL_SECONDS:
            return
        self._last_reclaim_at = now

        try:
            result = await redis.xautoclaim(
                settings.REDIS_STREAM_EVENTS,
                settings.REDIS_EVENT_CONSUMER_GROUP,
                self._consumer_name,
                settings.REDIS_RECLAIM_IDLE_MS,
                start_id=self._reclaim_cursor,
                count=settings.REDIS_RECLAIM_BATCH_SIZE,
            )
            if isinstance(result, (list, tuple)) and result:
                next_cursor = result[0]
                if isinstance(next_cursor, bytes):
                    next_cursor = next_cursor.decode("utf-8", errors="replace")
                if isinstance(next_cursor, str) and next_cursor:
                    self._reclaim_cursor = next_cursor
            reclaimed = extract_claimed_messages(result)
            if reclaimed:
                self._stats["reclaimed_total"] += len(reclaimed)
                logger.info(
                    "Reclaimed %d pending container event messages",
                    len(reclaimed),
                )
                await self._process_batch(redis, reclaimed, source="reclaimed")
        except Exception as e:
            logger.warning("Container event reclaim failed: %s", str(e))

    async def _process_batch(
        self,
        redis,
        messages: List[tuple],
        source: str = "live",
    ) -> None:
        """
        Process a batch of container event messages.

        Args:
            redis: Redis client for acknowledgment.
            messages: List of (message_id, fields) tuples.
        """
        acked_ids = []

        for message_id, fields in messages:
            try:
                self._stats["processed_total"] += 1
                event_data = self._parse_event(fields)

                if event_data and self._rule_matcher:
                    await self._rule_matcher.evaluate_container_event(event_data)

                acked_ids.append(message_id)

            except Exception as e:
                self._stats["failed_total"] += 1
                logger.error(
                    "Failed to process container event %s: %s", message_id, str(e)
                )
                if settings.REDIS_DLQ_ENABLED:
                    try:
                        await publish_dlq(
                            redis,
                            dlq_stream=settings.REDIS_STREAM_EVENTS_DLQ,
                            dlq_max_len=settings.REDIS_DLQ_MAX_LEN,
                            source_stream=settings.REDIS_STREAM_EVENTS,
                            consumer_group=settings.REDIS_EVENT_CONSUMER_GROUP,
                            consumer_name=self._consumer_name,
                            message_id=message_id,
                            fields=fields,
                            error=f"{source}: {str(e)}",
                        )
                        self._stats["dlq_published_total"] += 1
                    except Exception as dlq_err:
                        logger.warning(
                            "Failed to publish container event to DLQ: %s",
                            str(dlq_err),
                        )
                acked_ids.append(message_id)

        if acked_ids:
            acked = await redis.xack(
                settings.REDIS_STREAM_EVENTS,
                settings.REDIS_EVENT_CONSUMER_GROUP,
                *acked_ids,
            )
            self._stats["acked_total"] += int(acked or 0)

    def _parse_event(self, fields: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Parse container event from stream message fields.

        Args:
            fields: Raw message fields from Redis Stream.

        Returns:
            Parsed event dict or None if invalid.
        """
        try:
            data_str = fields.get("data", "{}")
            return json.loads(data_str)
        except json.JSONDecodeError as e:
            self._stats["parse_dropped_total"] += 1
            logger.warning("Invalid JSON in container event message: %s", str(e))
            return None


# Module-level singleton
_consumer: Optional[ContainerEventConsumer] = None


def get_container_event_consumer() -> ContainerEventConsumer:
    """Get or create the container event consumer singleton."""
    global _consumer
    if _consumer is None:
        _consumer = ContainerEventConsumer()
    return _consumer


__all__ = ["ContainerEventConsumer", "get_container_event_consumer"]
