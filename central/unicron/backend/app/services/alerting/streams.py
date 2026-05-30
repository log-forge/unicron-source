"""
Redis Streams for alert and log pipelines.

Provides reliable message delivery with consumer groups
for horizontal scaling of workers.

Pipelines:
- Alerts: alert-engine -> Redis Stream -> notifier
- Logs: Herald -> Central -> Redis Stream -> alert-engine (real-time rule eval)
                          -> VictoriaLogs (parallel storage)
"""
import json
from typing import Any, AsyncGenerator

from app.core.config import settings
from app.core.redis import get_redis


class LogBatchPublishError(RuntimeError):
    """Raised when a scoped log batch fails to fully publish to Redis."""

    def __init__(self, published: int, total: int, reason: str):
        self.published = int(published)
        self.total = int(total)
        self.reason = reason
        super().__init__(
            f"log stream publish incomplete: published={self.published} total={self.total} reason={self.reason}"
        )


async def publish_alert(alert_data: dict[str, Any]) -> str:
    """
    Publish alert to Redis Stream.

    Args:
        alert_data: Alert payload to publish

    Returns:
        Stream message ID
    """
    redis = await get_redis()
    message_id = await redis.xadd(
        settings.REDIS_STREAM_ALERTS,
        {"data": json.dumps(alert_data)},
        maxlen=settings.REDIS_STREAM_MAX_LEN,
    )
    return message_id


async def publish_notification(notification_data: dict[str, Any]) -> str:
    """
    Publish notification request to Redis Stream.

    Args:
        notification_data: Notification payload to publish

    Returns:
        Stream message ID
    """
    redis = await get_redis()
    message_id = await redis.xadd(
        settings.REDIS_STREAM_NOTIFICATIONS,
        {"data": json.dumps(notification_data)},
        maxlen=settings.REDIS_STREAM_MAX_LEN,
    )
    return message_id


async def publish_log_batch(logs: list[dict[str, Any]]) -> int:
    """
    Publish batch of log entries to Redis Stream.

    More efficient than individual publish_log calls for batch ingestion.

    Args:
        logs: List of log entries to publish

    Returns:
        Number of logs successfully published
    """
    redis = await get_redis()
    if not logs:
        return 0

    # Pipeline writes to reduce per-entry RTT overhead under burst traffic.
    # Fail closed on partial publish so callers can return 5xx and force retry.
    try:
        async with redis.pipeline(transaction=False) as pipe:
            for log_data in logs:
                pipe.xadd(
                    settings.REDIS_STREAM_LOGS,
                    {"data": json.dumps(log_data)},
                    maxlen=settings.REDIS_LOG_STREAM_MAX_LEN,
                    approximate=True,
                )

            results = await pipe.execute(raise_on_error=False)
            published = sum(1 for result in results if not isinstance(result, Exception))
            if published != len(logs):
                raise LogBatchPublishError(
                    published=published,
                    total=len(logs),
                    reason="partial_pipeline_write",
                )
            return published
    except LogBatchPublishError:
        raise
    except Exception as exc:
        published = 0
        last_error = exc
        for log_data in logs:
            try:
                await redis.xadd(
                    settings.REDIS_STREAM_LOGS,
                    {"data": json.dumps(log_data)},
                    maxlen=settings.REDIS_LOG_STREAM_MAX_LEN,
                    approximate=True,
                )
                published += 1
            except Exception as item_exc:
                last_error = item_exc
                continue

        if published != len(logs):
            raise LogBatchPublishError(
                published=published,
                total=len(logs),
                reason=f"sequential_fallback_failed:{type(last_error).__name__}",
            ) from last_error
        return published


async def publish_container_event(event_data: dict[str, Any]) -> str:
    """
    Publish container event to Redis Stream for alert-engine registry updates.

    Used to notify alert-engine of monitoring state changes so it can
    update its Redis-based container registry in real-time.

    Args:
        event_data: Container event payload with type, host_id, name, etc.

    Returns:
        Stream message ID
    """
    redis = await get_redis()
    message_id = await redis.xadd(
        settings.REDIS_STREAM_CONTAINERS,
        {"data": json.dumps(event_data)},
        maxlen=settings.REDIS_CONTAINER_STREAM_MAX_LEN,
    )
    return message_id


async def publish_container_lifecycle_event(event_data: dict[str, Any]) -> str:
    """
    Publish container lifecycle event to unicron:events Redis Stream.

    Used for alert-engine stability template evaluation (restart loop,
    crash loop, failed start). Separate from unicron:containers which
    handles monitoring state and inventory updates.

    Events carry: container_name, host_id, event_type, timestamp,
    exit_code, image for rule evaluation. Container identity uses
    host_id:container_name (Docker IDs are unstable across restarts).

    Args:
        event_data: Lifecycle event with host_id, container_name,
                    event_type, timestamp, exit_code, image.

    Returns:
        Stream message ID
    """
    redis = await get_redis()
    message_id = await redis.xadd(
        settings.REDIS_STREAM_EVENTS,
        {"data": json.dumps(event_data)},
        maxlen=settings.REDIS_EVENT_STREAM_MAX_LEN,
        approximate=True,
    )
    return message_id


async def ensure_consumer_group(stream: str, group: str) -> bool:
    """
    Create consumer group if not exists.

    Args:
        stream: Stream name
        group: Consumer group name

    Returns:
        True if group was created, False if already exists
    """
    redis = await get_redis()
    try:
        await redis.xgroup_create(stream, group, id="0", mkstream=True)
        return True
    except Exception as e:
        if "BUSYGROUP" not in str(e):
            raise
        return False


async def consume_stream(
    stream: str,
    group: str,
    consumer: str,
    batch_size: int = 10,
    block_ms: int = 5000,
) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
    """
    Consume messages from stream with consumer group.

    Uses XREADGROUP with blocking for efficient message consumption.
    Messages must be acknowledged after processing using ack_message().

    Args:
        stream: Stream name
        group: Consumer group name
        consumer: Consumer name (unique per worker instance)
        batch_size: Maximum messages to read per call
        block_ms: Milliseconds to block waiting for messages

    Yields:
        (message_id, data) tuples
    """
    redis = await get_redis()

    while True:
        messages = await redis.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams={stream: ">"},
            count=batch_size,
            block=block_ms,
        )

        if not messages:
            continue

        for stream_name, stream_messages in messages:
            for message_id, fields in stream_messages:
                data = json.loads(fields.get("data", "{}"))
                yield message_id, data


async def read_pending_messages(
    stream: str,
    group: str,
    consumer: str,
    batch_size: int = 10,
) -> list[tuple[str, dict[str, Any]]]:
    """
    Read pending messages that were claimed but not acknowledged.

    Useful for recovering from crashes or reprocessing failed messages.

    Args:
        stream: Stream name
        group: Consumer group name
        consumer: Consumer name
        batch_size: Maximum messages to read

    Returns:
        List of (message_id, data) tuples
    """
    redis = await get_redis()
    messages = await redis.xreadgroup(
        groupname=group,
        consumername=consumer,
        streams={stream: "0"},
        count=batch_size,
    )

    result = []
    if messages:
        for stream_name, stream_messages in messages:
            for message_id, fields in stream_messages:
                if fields:  # Skip deleted messages
                    data = json.loads(fields.get("data", "{}"))
                    result.append((message_id, data))
    return result


async def ack_message(stream: str, group: str, message_id: str) -> int:
    """
    Acknowledge message processing complete.

    Args:
        stream: Stream name
        group: Consumer group name
        message_id: Message ID to acknowledge

    Returns:
        Number of messages acknowledged (0 or 1)
    """
    redis = await get_redis()
    return await redis.xack(stream, group, message_id)


async def get_stream_info(stream: str) -> dict[str, Any]:
    """
    Get stream info for monitoring.

    Args:
        stream: Stream name

    Returns:
        Dict with length, first_entry, last_entry
    """
    redis = await get_redis()
    try:
        info = await redis.xinfo_stream(stream)
        return {
            "length": info.get("length", 0),
            "first_entry": info.get("first-entry"),
            "last_entry": info.get("last-entry"),
            "groups": info.get("groups", 0),
        }
    except Exception:
        return {"length": 0, "first_entry": None, "last_entry": None, "groups": 0}


async def get_consumer_group_info(stream: str) -> list[dict[str, Any]]:
    """
    Get consumer group info for monitoring.

    Args:
        stream: Stream name

    Returns:
        List of group info dicts with name, consumers, pending, last_delivered_id
    """
    redis = await get_redis()
    try:
        groups = await redis.xinfo_groups(stream)
        return [
            {
                "name": g.get("name"),
                "consumers": g.get("consumers", 0),
                "pending": g.get("pending", 0),
                "last_delivered_id": g.get("last-delivered-id"),
            }
            for g in groups
        ]
    except Exception:
        return []


async def get_stream_length(stream: str) -> int:
    """
    Get current stream length.

    Args:
        stream: Stream name

    Returns:
        Number of messages in stream
    """
    redis = await get_redis()
    try:
        return await redis.xlen(stream)
    except Exception:
        return 0
