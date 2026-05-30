"""Redis Streams consumer for alert-to-notification pipeline.

Consumes alerts from Redis Stream (published by alert-engine) and
dispatches notifications through the notification delivery system.

Pipeline flow:
    alert-engine → Redis Stream → stream_consumer → explicit targets → dispatch → notify
"""

import asyncio
import json
import socket
import time
from typing import Any, Dict, List, Optional

from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.config import settings
from app.core.database import session_ctx
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.services.dispatch_service import dispatch_alert
from app.services.stream_reliability import extract_claimed_messages, publish_dlq

logger = get_logger("notifier.services.stream_consumer")


class StreamConsumer:
    """
    Redis Streams consumer for alert notifications.

    Uses consumer groups for reliable message processing and
    horizontal scaling across multiple notifier instances.
    """

    def __init__(self):
        """Initialize the stream consumer."""
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._consumer_name = f"notifier-{socket.gethostname()}"
        self._last_reclaim_at: float = 0.0
        self._reclaim_cursor: str = "0-0"
        self._stats: dict[str, int] = {
            "processed_total": 0,
            "acked_total": 0,
            "failed_total": 0,
            "parse_dropped_total": 0,
            "reclaimed_total": 0,
            "dlq_published_total": 0,
            "max_attempts_exhausted_total": 0,
            "duplicate_suppressed_total": 0,
        }

    @property
    def is_running(self) -> bool:
        """Check if consumer is currently running."""
        return self._running

    def get_stats_snapshot(self) -> dict[str, int]:
        """Return a point-in-time copy of runtime processing counters."""
        return dict(self._stats)

    async def start(self) -> None:
        """
        Start the stream consumer as a background task.

        Creates consumer group if needed and begins consuming messages.
        """
        if self._running:
            logger.warning("Stream consumer already running")
            return

        # Ensure consumer group exists
        await self._ensure_consumer_group()

        # Start consumer loop as background task
        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
        logger.info(
            "Stream consumer started: group=%s, consumer=%s",
            settings.REDIS_CONSUMER_GROUP,
            self._consumer_name,
        )

    async def stop(self, timeout: float = 10.0) -> None:
        """
        Stop the stream consumer gracefully.

        Args:
            timeout: Maximum seconds to wait for graceful shutdown.
        """
        if not self._running:
            return

        logger.info("Stopping stream consumer...")
        self._running = False

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning("Stream consumer shutdown timed out, cancelling")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        logger.info("Stream consumer stopped")

    async def _ensure_consumer_group(self) -> None:
        """Create consumer group if it doesn't exist."""
        redis = await get_redis()
        try:
            await redis.xgroup_create(
                settings.REDIS_STREAM_ALERTS,
                settings.REDIS_CONSUMER_GROUP,
                id="0",
                mkstream=True,
            )
            logger.info(
                "Created consumer group: %s", settings.REDIS_CONSUMER_GROUP
            )
        except Exception as e:
            if "BUSYGROUP" in str(e):
                logger.debug(
                    "Consumer group already exists: %s",
                    settings.REDIS_CONSUMER_GROUP,
                )
            else:
                raise

    async def _consume_loop(self) -> None:
        """Main consumption loop - reads and processes messages."""
        redis_client = await get_redis()

        while self._running:
            try:
                await self._maybe_reclaim(redis_client)

                # Read messages from stream using consumer group
                messages = await redis_client.xreadgroup(
                    groupname=settings.REDIS_CONSUMER_GROUP,
                    consumername=self._consumer_name,
                    streams={settings.REDIS_STREAM_ALERTS: ">"},
                    count=settings.REDIS_CONSUMER_BATCH_SIZE,
                    block=settings.REDIS_CONSUMER_BLOCK_MS,
                )

                if not messages:
                    continue

                # Process messages concurrently within bounded batch workers.
                for _stream_name, stream_messages in messages:
                    await self._process_batch(
                        redis_client,
                        stream_messages,
                        source="live",
                    )

            except asyncio.CancelledError:
                logger.info("Consumer loop cancelled")
                break
            except RedisTimeoutError:
                # Expected on idle long-poll reads; not a transport fault.
                logger.debug("Notifier stream read timed out while idle; continuing")
                continue
            except RedisConnectionError as e:
                logger.warning("Notifier consumer Redis connection issue: %s", str(e))
                await asyncio.sleep(1.0)
            except Exception as e:
                logger.error("Error in consumer loop: %s", str(e))
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
                settings.REDIS_STREAM_ALERTS,
                settings.REDIS_CONSUMER_GROUP,
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
                logger.info("Reclaimed %d pending notifier messages", len(reclaimed))
                await self._process_batch(
                    redis,
                    reclaimed,
                    source="reclaimed",
                )
        except Exception as e:
            logger.warning("Notifier reclaim failed: %s", str(e))

    async def _process_batch(
        self,
        redis,
        messages: List[tuple[str, Dict[str, Any]]],
        *,
        source: str,
    ) -> None:
        """Process a stream batch with bounded concurrency."""
        if not messages:
            return

        concurrency = max(1, int(settings.REDIS_CONSUMER_CONCURRENCY))
        semaphore = asyncio.Semaphore(concurrency)

        async def _run(message_id: str, fields: Dict[str, Any]) -> None:
            async with semaphore:
                await self._process_message(
                    redis,
                    message_id,
                    fields,
                    source=source,
                )

        tasks = [asyncio.create_task(_run(message_id, fields)) for message_id, fields in messages]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Notifier batch worker failed: %s", result)

    @staticmethod
    def _attempt_key(message_id: str) -> str:
        return f"notifier:attempts:{settings.REDIS_STREAM_ALERTS}:{settings.REDIS_CONSUMER_GROUP}:{message_id}"

    async def _increment_attempt(self, redis, message_id: str) -> int:
        key = self._attempt_key(message_id)
        attempts = await redis.incr(key)
        if attempts == 1:
            await redis.expire(key, settings.REDIS_ATTEMPT_TTL_SECONDS)
        return int(attempts)

    async def _clear_attempt(self, redis, message_id: str) -> None:
        await redis.delete(self._attempt_key(message_id))

    async def _process_message(
        self,
        redis,
        message_id: str,
        fields: Dict[str, Any],
        source: str = "live",
    ) -> None:
        """
        Process a single message from the stream.

        Parses alert data, dispatches notifications, and acknowledges.

        Args:
            redis: Redis client for acknowledgment.
            message_id: Stream message ID.
            fields: Message fields from stream.
        """
        try:
            self._stats["processed_total"] += 1
            # Parse alert data from message
            data_str = fields.get("data", "{}")
            alert_data = json.loads(data_str)

            alert_id = alert_data.get("alert_id", "unknown")
            logger.info(
                "Processing alert: message_id=%s, alert_id=%s",
                message_id,
                alert_id,
            )

            # Dispatch notifications through the notification system
            await self._dispatch_alert(alert_data)

            # Acknowledge message after successful processing
            acked = await redis.xack(
                settings.REDIS_STREAM_ALERTS,
                settings.REDIS_CONSUMER_GROUP,
                message_id,
            )
            self._stats["acked_total"] += int(acked or 0)
            await self._clear_attempt(redis, message_id)
            logger.debug(
                "Message acknowledged: message_id=%s, alert_id=%s",
                message_id,
                alert_id,
            )

        except json.JSONDecodeError as e:
            self._stats["parse_dropped_total"] += 1
            self._stats["failed_total"] += 1
            logger.error(
                "Invalid JSON in message %s: %s", message_id, str(e)
            )
            # ACK invalid messages to prevent infinite reprocessing
            acked = await redis.xack(
                settings.REDIS_STREAM_ALERTS,
                settings.REDIS_CONSUMER_GROUP,
                message_id,
            )
            self._stats["acked_total"] += int(acked or 0)
            await self._clear_attempt(redis, message_id)
            if settings.REDIS_DLQ_ENABLED:
                try:
                    await publish_dlq(
                        redis,
                        dlq_stream=settings.REDIS_STREAM_ALERTS_DLQ,
                        dlq_max_len=settings.REDIS_DLQ_MAX_LEN,
                        source_stream=settings.REDIS_STREAM_ALERTS,
                        consumer_group=settings.REDIS_CONSUMER_GROUP,
                        consumer_name=self._consumer_name,
                        message_id=message_id,
                        fields=fields,
                        error=f"{source}: invalid_json: {str(e)}",
                        attempts=1,
                    )
                    self._stats["dlq_published_total"] += 1
                except Exception as dlq_err:
                    logger.warning(
                        "Failed to publish invalid JSON message to DLQ: %s",
                        str(dlq_err),
                    )
        except Exception as e:
            self._stats["failed_total"] += 1
            attempts = await self._increment_attempt(redis, message_id)
            logger.error(
                "Failed to process message %s (%s attempt %d): %s",
                message_id,
                source,
                attempts,
                str(e),
            )

            if settings.REDIS_DLQ_ENABLED and attempts >= settings.REDIS_MAX_DELIVERY_ATTEMPTS:
                try:
                    await publish_dlq(
                        redis,
                        dlq_stream=settings.REDIS_STREAM_ALERTS_DLQ,
                        dlq_max_len=settings.REDIS_DLQ_MAX_LEN,
                        source_stream=settings.REDIS_STREAM_ALERTS,
                        consumer_group=settings.REDIS_CONSUMER_GROUP,
                        consumer_name=self._consumer_name,
                        message_id=message_id,
                        fields=fields,
                        error=f"{source}: {str(e)}",
                        attempts=attempts,
                    )
                    self._stats["dlq_published_total"] += 1
                    self._stats["max_attempts_exhausted_total"] += 1
                    acked = await redis.xack(
                        settings.REDIS_STREAM_ALERTS,
                        settings.REDIS_CONSUMER_GROUP,
                        message_id,
                    )
                    self._stats["acked_total"] += int(acked or 0)
                    await self._clear_attempt(redis, message_id)
                    logger.error(
                        "Moved message to DLQ after max attempts: message_id=%s attempts=%d",
                        message_id,
                        attempts,
                    )
                except Exception as dlq_err:
                    logger.warning(
                        "Failed to move message %s to DLQ: %s",
                        message_id,
                        str(dlq_err),
                    )
            # If attempts are below max, leave message pending for reclaim/retry.

    async def _dispatch_alert(self, alert_data: Dict[str, Any]) -> None:
        """
        Dispatch alert through the notification system using explicit targets.

        Args:
            alert_data: Parsed alert data from stream.
        """
        alert_id = alert_data.get("alert_id", "")
        rule_name = alert_data.get("rule_name", "Alert")
        severity = alert_data.get("severity", "warning")
        annotations = alert_data.get("annotations", {})
        labels = alert_data.get("labels", {})
        notification_targets = alert_data.get("notification_targets") or {}
        organization_id = str(
            alert_data.get("organization_id")
            or labels.get("organization_id")
            or "local"
        ).strip() or "local"

        # Build notification payload
        notification_data = {
            "title": f"[{severity.upper()}] {rule_name}",
            "rule_name": rule_name,
            "message": annotations.get("message", "Alert triggered"),
            "severity": severity,
            "fingerprint": alert_data.get("fingerprint")
            or labels.get("dedup_fingerprint")
            or "",
            "labels": labels,
            "annotations": annotations,
            "rule_id": alert_data.get("rule_id", ""),
            "organization_id": organization_id,
            "value": alert_data.get("value"),
            "triggered_at": alert_data.get("triggered_at", ""),
            # AI fields -- passed through from rule annotations
            "ai_preprompt": annotations.get("ai_preprompt"),
            "ai_regex_gate": annotations.get("ai_regex_gate"),
        }

        explicit_channel_ids = [
            str(value).strip()
            for value in notification_targets.get("channel_ids", []) or []
            if str(value).strip()
        ]
        explicit_group_ids = [
            str(value).strip()
            for value in notification_targets.get("group_ids", []) or []
            if str(value).strip()
        ]
        explicit_preset_ids = [
            str(value).strip()
            for value in notification_targets.get("preset_ids", []) or []
            if str(value).strip()
        ]
        has_explicit_targets = bool(
            explicit_channel_ids or explicit_group_ids or explicit_preset_ids
        )

        if not has_explicit_targets:
            logger.debug("Alert %s has no notification targets; no tasks queued", alert_id)

        async with session_ctx() as db:
            result = await dispatch_alert(
                db=db,
                alert_id=alert_id,
                alert_data=notification_data,
                channel_ids=explicit_channel_ids if explicit_channel_ids else None,
                group_ids=explicit_group_ids if explicit_group_ids else None,
                preset_ids=explicit_preset_ids if explicit_preset_ids else None,
            )
            logger.info(
                "Alert dispatched: alert_id=%s, channels=%d, tasks=%d, duplicates=%d, explicit_targets=%s",
                alert_id,
                result.get("channels_targeted", 0),
                len(result.get("tasks_queued", [])),
                int(result.get("duplicate_suppressed", 0) or 0),
                has_explicit_targets,
            )
            self._stats["duplicate_suppressed_total"] += int(
                result.get("duplicate_suppressed", 0) or 0
            )


# Module-level singleton for app-wide use
_consumer: Optional[StreamConsumer] = None


def get_stream_consumer() -> StreamConsumer:
    """Get or create the stream consumer singleton."""
    global _consumer
    if _consumer is None:
        _consumer = StreamConsumer()
    return _consumer


__all__ = ["StreamConsumer", "get_stream_consumer"]
