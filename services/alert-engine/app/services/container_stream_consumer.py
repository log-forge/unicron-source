"""Redis Streams consumer for real-time container inventory updates.

Consumes container inventory from Redis Stream (published by Central when
Herald reports inventory) and updates local state for real-time UI updates.

Pipeline flow:
    Herald -> Central -> PostgreSQL + Redis Stream -> container_stream_consumer
                                                   -> WebSocket broadcast
"""

import asyncio
import json
import socket
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.services.stream_reliability import extract_claimed_messages, publish_dlq

if TYPE_CHECKING:
    from app.services.rule_matcher import RuleMatcher

logger = get_logger("alert-engine.services.container_stream_consumer")


class ContainerStreamConsumer:
    """
    Redis Streams consumer for real-time container inventory updates.

    Uses consumer groups for reliable message processing.
    Triggers callbacks when container state changes are received.
    """

    def __init__(self):
        """Initialize the container stream consumer."""
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._consumer_name = f"alert-engine-container-{socket.gethostname()}"
        self._on_update_callback: Optional[Callable[[Dict[str, Any]], None]] = None
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

    def set_update_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Set callback function to be invoked on container updates.

        Args:
            callback: Function that receives container update payload.
                     Called with dict containing container_id, status, etc.
        """
        self._on_update_callback = callback

    async def start(self, rule_matcher=None) -> None:
        """Start the container stream consumer as a background task."""
        if self._running:
            logger.warning("Container stream consumer already running")
            return

        self._rule_matcher = rule_matcher

        # Ensure consumer group exists
        await self._ensure_consumer_group()

        # Start consumer loop as background task
        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
        logger.info(
            "Container stream consumer started: stream=%s, group=%s, consumer=%s",
            settings.REDIS_STREAM_CONTAINERS,
            settings.REDIS_CONTAINER_CONSUMER_GROUP,
            self._consumer_name,
        )

    async def stop(self, timeout: float = 10.0) -> None:
        """
        Stop the container stream consumer gracefully.

        Args:
            timeout: Maximum seconds to wait for graceful shutdown.
        """
        if not self._running:
            return

        logger.info("Stopping container stream consumer...")
        self._running = False

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning("Container stream consumer shutdown timed out, cancelling")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        logger.info("Container stream consumer stopped")

    async def _ensure_consumer_group(self) -> None:
        """Create consumer group if it doesn't exist."""
        redis = await get_redis()
        try:
            await redis.xgroup_create(
                settings.REDIS_STREAM_CONTAINERS,
                settings.REDIS_CONTAINER_CONSUMER_GROUP,
                id="0",
                mkstream=True,
            )
            logger.info(
                "Created container consumer group: %s",
                settings.REDIS_CONTAINER_CONSUMER_GROUP,
            )
        except Exception as e:
            if "BUSYGROUP" in str(e):
                logger.debug(
                    "Container consumer group already exists: %s",
                    settings.REDIS_CONTAINER_CONSUMER_GROUP,
                )
            else:
                raise

    async def _consume_loop(self) -> None:
        """Main consumption loop - reads and processes container inventory updates."""
        redis = await get_redis()

        while self._running:
            try:
                await self._maybe_reclaim(redis)

                # Read messages from stream using consumer group
                messages = await redis.xreadgroup(
                    groupname=settings.REDIS_CONTAINER_CONSUMER_GROUP,
                    consumername=self._consumer_name,
                    streams={settings.REDIS_STREAM_CONTAINERS: ">"},
                    count=settings.REDIS_CONTAINER_CONSUMER_BATCH_SIZE,
                    block=settings.REDIS_CONTAINER_CONSUMER_BLOCK_MS,
                )

                if not messages:
                    continue

                # Process batch of container updates
                for stream_name, stream_messages in messages:
                    await self._process_batch(redis, stream_messages)

            except asyncio.CancelledError:
                logger.info("Container consumer loop cancelled")
                break
            except Exception as e:
                logger.error("Error in container consumer loop: %s", str(e))
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
                settings.REDIS_STREAM_CONTAINERS,
                settings.REDIS_CONTAINER_CONSUMER_GROUP,
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
                    "Reclaimed %d pending container messages",
                    len(reclaimed),
                )
                await self._process_batch(redis, reclaimed, source="reclaimed")
        except Exception as e:
            logger.warning("Container reclaim failed: %s", str(e))

    async def _process_batch(
        self,
        redis,
        messages: List[tuple],
        source: str = "live",
    ) -> None:
        """
        Process a batch of container inventory messages.

        Args:
            redis: Redis client for acknowledgment.
            messages: List of (message_id, fields) tuples.
        """
        acked_ids = []

        for message_id, fields in messages:
            try:
                self._stats["processed_total"] += 1
                # Parse container update from message
                update_data = self._parse_container_update(fields)

                if update_data:
                    await self._handle_container_update(update_data)

                # Mark for acknowledgment
                acked_ids.append(message_id)

            except Exception as e:
                self._stats["failed_total"] += 1
                logger.error(
                    "Failed to process container message %s: %s",
                    message_id,
                    str(e),
                )
                if settings.REDIS_DLQ_ENABLED:
                    try:
                        await publish_dlq(
                            redis,
                            dlq_stream=settings.REDIS_STREAM_CONTAINERS_DLQ,
                            dlq_max_len=settings.REDIS_DLQ_MAX_LEN,
                            source_stream=settings.REDIS_STREAM_CONTAINERS,
                            consumer_group=settings.REDIS_CONTAINER_CONSUMER_GROUP,
                            consumer_name=self._consumer_name,
                            message_id=message_id,
                            fields=fields,
                            error=f"{source}: {str(e)}",
                        )
                        self._stats["dlq_published_total"] += 1
                    except Exception as dlq_err:
                        logger.warning(
                            "Failed to publish container message to DLQ: %s",
                            str(dlq_err),
                        )
                # Still ack to prevent infinite reprocessing
                # State is persisted in PostgreSQL anyway
                acked_ids.append(message_id)

        # Batch acknowledge processed messages
        if acked_ids:
            acked = await redis.xack(
                settings.REDIS_STREAM_CONTAINERS,
                settings.REDIS_CONTAINER_CONSUMER_GROUP,
                *acked_ids,
            )
            self._stats["acked_total"] += int(acked or 0)

    def _parse_container_update(self, fields: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Parse container update from stream message fields.

        Expected message format:
        {
            "data": JSON string with:
                - "type": "inventory_update" | "container_start" | "container_stop"
                - "herald_id": string
                - "containers": list of container states (for inventory_update)
                - "container_id": string (for single container events)
                - "status": string
                - "timestamp": ISO string
        }

        Args:
            fields: Raw message fields from Redis Stream.

        Returns:
            Parsed update dict or None if invalid.
        """
        try:
            data_str = fields.get("data", "{}")
            return json.loads(data_str)
        except json.JSONDecodeError as e:
            self._stats["parse_dropped_total"] += 1
            logger.warning("Invalid JSON in container message: %s", str(e))
            return None

    async def _sync_container_group_cache(self, host_id: str, name: str) -> None:
        """Re-sync Redis group caches for any groups this container belongs to.

        When monitoring state changes, group-scoped rules need to see
        the updated membership in ``alert-engine:group-containers:{group_id}``.
        """
        try:
            from app.core.database import get_session
            from app.services.group_cache import sync_container_groups

            async for session in get_session():
                await sync_container_groups(host_id, name, session)
                break
        except Exception as e:
            logger.warning(
                "Failed to sync group cache after monitoring change for %s:%s: %s",
                host_id, name, str(e),
            )

    async def _is_monitoring_enabled(self, host_id: str, name: str) -> bool:
        """Check if monitoring is enabled for a container via Central's Redis keys.

        Central stores monitoring state as: monitoring:{host_id}:{container_name}
        We first check the canonical key directly, then use the host monitoring
        index, and finally fall back to legacy key scans if needed.

        Args:
            host_id: The agent host identifier.
            name: Container name.

        Returns:
            True if any matching monitoring key has value "1".
        """
        try:
            redis = await get_redis()

            canonical_key = f"monitoring:{host_id}:{name}"
            value = await redis.get(canonical_key)
            if value is not None:
                value_str = value if isinstance(value, str) else value.decode()
                return value_str == "1"

            host_index_key = f"monitoring:index:host:{host_id}"
            indexed_container_keys = await redis.smembers(host_index_key)
            if indexed_container_keys:
                key_list = [
                    key if isinstance(key, str) else key.decode()
                    for key in indexed_container_keys
                ]
                matching_keys = [
                    container_key for container_key in key_list
                    if container_key == f"{host_id}:{name}"
                ]
                if matching_keys:
                    monitoring_keys = [f"monitoring:{container_key}" for container_key in matching_keys]
                    async with redis.pipeline(transaction=False) as pipe:
                        for monitoring_key in monitoring_keys:
                            await pipe.get(monitoring_key)
                        values = await pipe.execute()
                    for value in values:
                        value_str = (
                            value
                            if isinstance(value, str)
                            else value.decode() if value else "0"
                        )
                        if value_str == "1":
                            return True
                    return False

            # Legacy fallback.
            pattern = f"monitoring:{host_id}:{name}|*"
            async for key in redis.scan_iter(match=pattern):
                value = await redis.get(key)
                value_str = value if isinstance(value, str) else value.decode() if value else "0"
                if value_str == "1":
                    return True
            return False
        except Exception as e:
            logger.warning("Failed to check monitoring state for %s:%s: %s", host_id, name, str(e))
            return False

    async def _handle_container_update(self, update_data: Dict[str, Any]) -> None:
        """
        Handle a container inventory update.

        Processes monitoring_state_changed, container_start, container_stop, and
        inventory_update events to keep the container registry in sync. Delegates
        to the callback for WebSocket broadcast and other handlers.

        Registry lifecycle:
        - monitoring_state_changed(enabled=true): add to registry
        - monitoring_state_changed(enabled=false): remove from registry
        - container_stop: update status to "exited" (keep in registry -- still monitored)
        - container_start: re-add to registry if monitoring is enabled (restores after restart)
        - inventory_update: sync statuses for monitored containers

        Args:
            update_data: Parsed update with type, herald_id, containers, etc.
        """
        update_type = update_data.get("type", "unknown")
        herald_id = update_data.get("herald_id", "unknown")
        registry_changed = False

        logger.debug(
            "Processing container update: type=%s, herald=%s",
            update_type,
            herald_id,
        )

        # Update container registry for monitoring state changes
        if update_type == "monitoring_state_changed":
            try:
                from app.services.container_registry import get_container_registry

                registry = get_container_registry()
                host_id = update_data.get("host_id", "local")
                name = update_data.get("name", "")
                enabled = update_data.get("enabled", False)

                if enabled and name:
                    await registry.add_container(
                        host_id=host_id,
                        name=name,
                        container_id=update_data.get("container_id", ""),
                        image=update_data.get("image", ""),
                        status=update_data.get("status", "running"),
                    )
                    logger.info(
                        "Added container to registry: %s:%s",
                        host_id,
                        name,
                    )
                    registry_changed = True
                elif not enabled and name:
                    await registry.remove_container(host_id, name)
                    logger.info(
                        "Removed container from registry: %s:%s",
                        host_id,
                        name,
                    )
                    registry_changed = True

                # Re-sync group caches for any groups this container belongs to.
                # Ensures group-scoped rules pick up new/removed members.
                if name:
                    await self._sync_container_group_cache(host_id, name)
            except Exception as e:
                logger.error("Failed to update container registry: %s", str(e))

        # Container stopped: update status instead of removing.
        # The container is still being monitored (monitoring key persists in Redis).
        # Removing it would break the alerting containers list and lose monitoring
        # state on restart. Rules won't fire on stopped containers anyway (no logs).
        elif update_type == "container_stop":
            try:
                from app.services.container_registry import get_container_registry

                registry = get_container_registry()
                host_id = update_data.get("host_id") or update_data.get("herald_id", "local")
                name = update_data.get("name", "")
                if name:
                    # Check if container is in registry (i.e. was being monitored)
                    existing = await registry.get_container(host_id, name)
                    if existing:
                        # Update status to exited/stopped, keep in registry
                        await registry.add_container(
                            host_id=host_id,
                            name=name,
                            container_id=update_data.get("container_id", existing.get("container_id", "")),
                            image=update_data.get("image", existing.get("image", "")),
                            status=update_data.get("status", "exited"),
                        )
                        logger.debug(
                            "Updated stopped container status in registry: %s:%s",
                            host_id,
                            name,
                        )
                        registry_changed = True
            except Exception as e:
                logger.error("Failed to update stopped container in registry: %s", str(e))

        # Container started: re-add to registry if monitoring is enabled.
        # Handles container restarts (same name, new container_id) -- monitoring
        # and rules are automatically restored without user intervention.
        elif update_type == "container_start":
            try:
                from app.services.container_registry import get_container_registry

                registry = get_container_registry()
                host_id = update_data.get("host_id") or update_data.get("herald_id", "local")
                name = update_data.get("name", "")
                if name and await self._is_monitoring_enabled(host_id, name):
                    await registry.add_container(
                        host_id=host_id,
                        name=name,
                        container_id=update_data.get("container_id", ""),
                        image=update_data.get("image", ""),
                        status=update_data.get("status", "running"),
                    )
                    logger.info(
                        "Re-added restarted container to registry: %s:%s",
                        host_id,
                        name,
                    )
                    registry_changed = True
            except Exception as e:
                logger.error("Failed to re-add restarted container to registry: %s", str(e))

        # Inventory update: sync statuses for monitored containers.
        # Herald sends full inventory periodically -- update registry entries
        # with current statuses so the alerting tab stays accurate.
        elif update_type == "inventory_update":
            try:
                from app.services.container_registry import get_container_registry

                registry = get_container_registry()
                containers = update_data.get("containers", [])
                for c in containers:
                    c_host_id = c.get("host_id") or c.get("herald_id", "local") or "local"
                    c_name = c.get("name", "")
                    if not c_name:
                        continue
                    # Only update containers already in the registry (monitored)
                    existing = await registry.get_container(c_host_id, c_name)
                    if existing:
                        await registry.add_container(
                            host_id=c_host_id,
                            name=c_name,
                            container_id=(
                                c.get("docker_container_id")
                                or c.get("container_id")
                                or existing.get("container_id", "")
                            ),
                            image=c.get("image", existing.get("image", "")),
                            status=c.get("status", existing.get("status", "unknown")),
                        )
                        registry_changed = True
            except Exception as e:
                logger.error("Failed to sync inventory update to registry: %s", str(e))

        if registry_changed and self._rule_matcher:
            self._rule_matcher.invalidate()

        # Invoke callback if registered (for WebSocket broadcast etc.)
        if self._on_update_callback:
            try:
                # Callback may be sync or async
                result = self._on_update_callback(update_data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error("Container update callback error: %s", str(e))


# Module-level singleton
_consumer: Optional[ContainerStreamConsumer] = None


def get_container_stream_consumer() -> ContainerStreamConsumer:
    """Get or create the container stream consumer singleton."""
    global _consumer
    if _consumer is None:
        _consumer = ContainerStreamConsumer()
    return _consumer


__all__ = ["ContainerStreamConsumer", "get_container_stream_consumer"]
