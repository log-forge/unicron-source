"""WebSocket broadcast service for container updates.

Broadcasts container inventory updates to connected frontend clients.
Event types match what the frontend's useContainers hook expects:
- containers_updated: Full or partial container list update
- group_created: New group created
- group_updated: Group membership/name changed
- group_deleted: Group removed

This service publishes events to a custom Redis pub/sub channel.
Central's container_ws_relay service subscribes to the Redis pub/sub channel and
relays messages to browser WebSocket clients connected at /api/containers/ws.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from app.core.logging import get_logger

logger = get_logger("alert-engine.services.container_websocket")


class ContainerWebSocketService:
    """
    Service for broadcasting container updates via WebSocket.

    Uses Central's Socket.IO infrastructure by publishing to Redis channels
    that the Socket.IO AsyncRedisManager subscribes to.
    """

    def __init__(self):
        """Initialize the WebSocket service."""
        self._broadcast_queue: asyncio.Queue = asyncio.Queue()
        self._broadcaster_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start the WebSocket broadcaster."""
        if self._running:
            return

        self._running = True
        self._broadcaster_task = asyncio.create_task(self._broadcast_loop())
        logger.info("Container WebSocket service started")

    async def stop(self) -> None:
        """Stop the WebSocket broadcaster."""
        if not self._running:
            return

        self._running = False
        if self._broadcaster_task:
            self._broadcaster_task.cancel()
            try:
                await self._broadcaster_task
            except asyncio.CancelledError:
                pass

        logger.info("Container WebSocket service stopped")

    async def _broadcast_loop(self) -> None:
        """Process broadcast queue and send to connected clients."""
        while self._running:
            try:
                # Wait for messages with timeout to allow checking _running flag
                try:
                    message = await asyncio.wait_for(
                        self._broadcast_queue.get(),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    continue

                await self._send_to_clients(message)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in broadcast loop: %s", str(e))
                await asyncio.sleep(0.5)

    async def _send_to_clients(self, message: Dict[str, Any]) -> None:
        """
        Send message to all connected browser WebSocket clients via Redis pub/sub.

        Publishes to a custom channel that Central's container_ws_relay
        subscribes to. Central relays the message to browser WebSocket
        clients connected at /api/containers/ws.

        Channel: unicron:container-ws-updates (plain JSON, not Socket.IO format)
        """
        from app.core.redis import get_redis

        try:
            redis = await get_redis()
            channel = "unicron:container-ws-updates"
            await redis.publish(channel, json.dumps(message))

            logger.debug(
                "Published container event to Redis pub/sub: type=%s",
                message.get("type", "unknown"),
            )
        except Exception as e:
            logger.error("Failed to publish container event: %s", str(e))

    async def broadcast_containers_updated(
        self,
        containers: List[Dict[str, Any]],
        groups: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Broadcast containers_updated event.

        Args:
            containers: List of container info dicts
            groups: Optional list of group info dicts
        """
        message = {
            "type": "containers_updated",
            "data": {
                "containers": containers,
                "groups": groups or [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }
        await self._broadcast_queue.put(message)

    async def broadcast_group_created(self, group: Dict[str, Any]) -> None:
        """
        Broadcast group_created event.

        Args:
            group: Group info dict matching GroupInfo frontend type
        """
        message = {
            "type": "group_created",
            "data": group,
        }
        await self._broadcast_queue.put(message)

    async def broadcast_group_updated(self, group: Dict[str, Any]) -> None:
        """
        Broadcast group_updated event.

        Args:
            group: Group info dict matching GroupInfo frontend type
        """
        message = {
            "type": "group_updated",
            "data": group,
        }
        await self._broadcast_queue.put(message)

    async def broadcast_group_deleted(self, group_id: str) -> None:
        """
        Broadcast group_deleted event.

        Args:
            group_id: ID of deleted group
        """
        message = {
            "type": "group_deleted",
            "data": {"groupId": group_id},
        }
        await self._broadcast_queue.put(message)


def handle_container_stream_update(
    ws_service: ContainerWebSocketService,
) -> Callable[[Dict[str, Any]], Any]:
    """
    Create callback for container stream consumer updates.

    Returns a callback function that processes container inventory
    updates from Redis Stream and triggers WebSocket broadcasts.
    """

    async def callback(update_data: Dict[str, Any]) -> None:
        """Process container stream update and broadcast via WebSocket."""
        update_type = update_data.get("type", "unknown")

        if update_type == "inventory_update":
            # Full or partial inventory update from Herald
            containers = update_data.get("containers", [])

            # Transform to frontend format
            formatted_containers = []
            for c in containers:
                formatted_containers.append({
                    "identifier": _build_identifier(c),
                    "name": c.get("name", ""),
                    "host_id": c.get("herald_id"),
                    "container_id": c.get("container_id", ""),
                    "image_name": c.get("image", ""),
                    "last_seen": c.get("started_at", datetime.now(timezone.utc).isoformat()),
                    "status": c.get("status"),
                })

            await ws_service.broadcast_containers_updated(formatted_containers)

        elif update_type == "container_start":
            # Single container started
            container = {
                "identifier": _build_identifier(update_data),
                "name": update_data.get("name", ""),
                "host_id": update_data.get("herald_id"),
                "container_id": update_data.get("container_id", ""),
                "image_name": update_data.get("image", ""),
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "status": update_data.get("status", "running"),
            }
            await ws_service.broadcast_containers_updated([container])

        elif update_type == "container_stop":
            # Single container stopped
            container = {
                "identifier": _build_identifier(update_data),
                "name": update_data.get("name", ""),
                "host_id": update_data.get("herald_id"),
                "container_id": update_data.get("container_id", ""),
                "image_name": update_data.get("image", ""),
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "status": update_data.get("status", "exited"),
            }
            await ws_service.broadcast_containers_updated([container])

        elif update_type == "monitoring_state_changed":
            # Monitoring state toggled - broadcast as monitoring_state_changed event
            # Registry update already handled by stream consumer before this callback
            # Must NOT use containers_updated — that replaces the entire frontend
            # cache with partial data. Instead, send container info so the frontend
            # can add/remove this single container from the existing cache directly
            # (no HTTP refetch needed — avoids session validation + DB round-trip).
            host_id = update_data.get("host_id", "local") or "local"
            name = update_data.get("name", "")
            container_id = update_data.get("container_id", "")
            short_id = container_id[:12] if container_id else ""
            message = {
                "type": "monitoring_state_changed",
                "data": {
                    "enabled": update_data.get("enabled", False),
                    "container": {
                        "identifier": f"{host_id}:{name}:{short_id}",
                        "name": name,
                        "host_id": host_id,
                        "container_id": container_id,
                        "image_name": update_data.get("image", ""),
                        "last_seen": datetime.now(timezone.utc).isoformat(),
                        "status": update_data.get("status", "running"),
                    },
                },
            }
            await ws_service._broadcast_queue.put(message)

        elif update_type == "group_created":
            group = update_data.get("group", {})
            await ws_service.broadcast_group_created(group)

        elif update_type == "group_updated":
            group = update_data.get("group", {})
            await ws_service.broadcast_group_updated(group)

        elif update_type == "group_deleted":
            group_id = update_data.get("group_id", "")
            if group_id:
                await ws_service.broadcast_group_deleted(group_id)

    return callback


def _build_identifier(data: Dict[str, Any]) -> str:
    """Build frontend identifier from container data."""
    host_id = data.get("herald_id", "local") or "local"
    name = data.get("name", "unknown")
    short_id = (data.get("container_id", "") or "")[:12]
    return f"{host_id}:{name}:{short_id}"


# Module-level singleton
_ws_service: Optional[ContainerWebSocketService] = None


def get_container_websocket_service() -> ContainerWebSocketService:
    """Get or create the container WebSocket service singleton."""
    global _ws_service
    if _ws_service is None:
        _ws_service = ContainerWebSocketService()
    return _ws_service


__all__ = [
    "ContainerWebSocketService",
    "get_container_websocket_service",
    "handle_container_stream_update",
]
