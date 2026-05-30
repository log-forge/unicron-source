"""Redis Streams consumer for real-time log processing.

Consumes logs from Redis Stream (published by Central) and
evaluates alert rules in real-time for pattern matching.

Pipeline flow:
    Herald -> Central -> Redis Stream -> log_stream_consumer -> rule_matcher
                      -> VictoriaLogs (parallel, non-blocking)
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

logger = get_logger("alert-engine.services.log_stream_consumer")


class LogStreamConsumer:
    """
    Redis Streams consumer for real-time log rule evaluation.

    Uses consumer groups for reliable message processing and
    horizontal scaling across multiple alert-engine workers.
    """

    def __init__(self):
        """Initialize the log stream consumer."""
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._consumer_name = f"alert-engine-{socket.gethostname()}"
        self._rule_matcher: Optional["RuleMatcher"] = None  # Will be set on start
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
        Start the log stream consumer as a background task.

        Args:
            rule_matcher: Optional rule matcher instance for log evaluation.
                         If not provided, logs are consumed but not evaluated.
        """
        if self._running:
            logger.warning("Log stream consumer already running")
            return

        self._rule_matcher = rule_matcher

        # Ensure consumer group exists
        await self._ensure_consumer_group()

        # Start consumer loop as background task
        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
        logger.info(
            "Log stream consumer started: stream=%s, group=%s, consumer=%s",
            settings.REDIS_STREAM_LOGS,
            settings.REDIS_LOG_CONSUMER_GROUP,
            self._consumer_name,
        )

    async def stop(self, timeout: float = 10.0) -> None:
        """
        Stop the log stream consumer gracefully.

        Args:
            timeout: Maximum seconds to wait for graceful shutdown.
        """
        if not self._running:
            return

        logger.info("Stopping log stream consumer...")
        self._running = False

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning("Log stream consumer shutdown timed out, cancelling")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        logger.info("Log stream consumer stopped")

    async def _ensure_consumer_group(self) -> None:
        """Create consumer group if it doesn't exist."""
        redis = await get_redis()
        try:
            await redis.xgroup_create(
                settings.REDIS_STREAM_LOGS,
                settings.REDIS_LOG_CONSUMER_GROUP,
                id="0",
                mkstream=True,
            )
            logger.info(
                "Created log consumer group: %s", settings.REDIS_LOG_CONSUMER_GROUP
            )
        except Exception as e:
            if "BUSYGROUP" in str(e):
                logger.debug(
                    "Log consumer group already exists: %s",
                    settings.REDIS_LOG_CONSUMER_GROUP,
                )
            else:
                raise

    async def _consume_loop(self) -> None:
        """Main consumption loop - reads and processes log batches."""
        redis = await get_redis()

        while self._running:
            try:
                await self._maybe_reclaim(redis)

                # Read messages from stream using consumer group
                messages = await redis.xreadgroup(
                    groupname=settings.REDIS_LOG_CONSUMER_GROUP,
                    consumername=self._consumer_name,
                    streams={settings.REDIS_STREAM_LOGS: ">"},
                    count=settings.REDIS_LOG_CONSUMER_BATCH_SIZE,
                    block=settings.REDIS_LOG_CONSUMER_BLOCK_MS,
                )

                if not messages:
                    continue

                # Process batch of logs
                for stream_name, stream_messages in messages:
                    await self._process_batch(redis, stream_messages)

            except asyncio.CancelledError:
                logger.info("Log consumer loop cancelled")
                break
            except Exception as e:
                logger.error("Error in log consumer loop: %s", str(e))
                # Brief pause before retry to avoid tight error loops
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
                settings.REDIS_STREAM_LOGS,
                settings.REDIS_LOG_CONSUMER_GROUP,
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
                    "Reclaimed %d pending log messages",
                    len(reclaimed),
                )
                await self._process_batch(redis, reclaimed, source="reclaimed")
        except Exception as e:
            logger.warning("Log reclaim failed: %s", str(e))

    async def _process_batch(
        self,
        redis,
        messages: List[tuple],
        source: str = "live",
    ) -> None:
        """
        Process a batch of log messages.

        Args:
            redis: Redis client for acknowledgment.
            messages: List of (message_id, fields) tuples.
        """
        acked_ids = []

        for message_id, fields in messages:
            try:
                self._stats["processed_total"] += 1
                # Parse log entry from message
                log_data = self._parse_log_entry(fields)

                if log_data and self._rule_matcher:
                    # Evaluate rules against this log entry
                    message_id_str = (
                        message_id.decode("utf-8", errors="replace")
                        if isinstance(message_id, bytes)
                        else str(message_id)
                    )
                    await self._evaluate_log(log_data, stream_message_id=message_id_str)

                # Mark for acknowledgment
                acked_ids.append(message_id)

            except Exception as e:
                self._stats["failed_total"] += 1
                logger.error(
                    "Failed to process log message %s: %s", message_id, str(e)
                )
                if settings.REDIS_DLQ_ENABLED:
                    try:
                        await publish_dlq(
                            redis,
                            dlq_stream=settings.REDIS_STREAM_LOGS_DLQ,
                            dlq_max_len=settings.REDIS_DLQ_MAX_LEN,
                            source_stream=settings.REDIS_STREAM_LOGS,
                            consumer_group=settings.REDIS_LOG_CONSUMER_GROUP,
                            consumer_name=self._consumer_name,
                            message_id=message_id,
                            fields=fields,
                            error=f"{source}: {str(e)}",
                        )
                        self._stats["dlq_published_total"] += 1
                    except Exception as dlq_err:
                        logger.warning(
                            "Failed to publish log message to DLQ: %s",
                            str(dlq_err),
                        )
                # Still ack to prevent infinite reprocessing
                # Log is not truly lost - it's in VictoriaLogs
                acked_ids.append(message_id)

        # Batch acknowledge processed messages
        if acked_ids:
            acked = await redis.xack(
                settings.REDIS_STREAM_LOGS,
                settings.REDIS_LOG_CONSUMER_GROUP,
                *acked_ids,
            )
            self._stats["acked_total"] += int(acked or 0)

    def _parse_log_entry(self, fields: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Parse log entry from stream message fields.

        Args:
            fields: Raw message fields from Redis Stream.

        Returns:
            Parsed log entry dict or None if invalid.
        """
        try:
            data_str = fields.get("data", "{}")
            return json.loads(data_str)
        except json.JSONDecodeError as e:
            self._stats["parse_dropped_total"] += 1
            logger.warning("Invalid JSON in log message: %s", str(e))
            return None

    async def _evaluate_log(
        self,
        log_data: Dict[str, Any],
        stream_message_id: Optional[str] = None,
    ) -> None:
        """
        Evaluate alert rules against a log entry.

        Delegates to RuleMatcher for real-time rule evaluation against
        the incoming log. RuleMatcher handles O(1) container lookup and
        concurrent rule evaluation.

        Args:
            log_data: Parsed log entry with container_id, message, etc.
            stream_message_id: Redis Stream message ID for replay diagnostics.
        """
        if self._rule_matcher:
            await self._rule_matcher.evaluate_log(
                log_data,
                stream_message_id=stream_message_id,
            )


# Module-level singleton
_consumer: Optional[LogStreamConsumer] = None


def get_log_stream_consumer() -> LogStreamConsumer:
    """Get or create the log stream consumer singleton."""
    global _consumer
    if _consumer is None:
        _consumer = LogStreamConsumer()
    return _consumer


__all__ = ["LogStreamConsumer", "get_log_stream_consumer"]
