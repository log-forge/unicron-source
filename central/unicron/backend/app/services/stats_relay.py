"""On-demand container stats relay service.

Manages browser subscriptions to per-container stats streams.
When a browser subscribes to a container's stats:
  1. If first subscriber, sends 'start_stats' command to the agent via AgentRegistry
  2. Relays stats frames from agent to all subscribed browsers
When last subscriber disconnects:
  3. Sends 'stop_stats' command to the agent (no orphaned goroutines)

Thread-safe with asyncio.Lock. Handles disconnected browsers gracefully.
"""

import asyncio
import json
from typing import Dict, List, Optional

from fastapi import WebSocket

from app.core.logging import get_logger

logger = get_logger("services.stats_relay")


class StatsRelay:
    """Singleton relay connecting browser stats subscriptions to agent streams.

    Lifecycle:
        subscribe()   -> browser opens container detail page
        relay_stats() -> agent sends stats frame, relay to all subscribers
        unsubscribe() -> browser navigates away or disconnects
    """

    _instance: Optional["StatsRelay"] = None
    _lock: asyncio.Lock

    def __new__(cls) -> "StatsRelay":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._lock = asyncio.Lock()
        # container_id -> list of subscribed browser WebSockets
        self._subscriptions: Dict[str, List[WebSocket]] = {}

    async def subscribe(
        self, container_id: str, browser_ws: WebSocket, host_id: str
    ) -> None:
        """Subscribe a browser WebSocket to stats for a container.

        If this is the first subscriber for the container, sends a
        'start_stats' command to the agent responsible for that host.

        Args:
            container_id: Docker container ID to stream stats for
            browser_ws: The browser's WebSocket connection
            host_id: The agent host_id that owns this container
        """
        async with self._lock:
            is_first = container_id not in self._subscriptions or len(
                self._subscriptions.get(container_id, [])
            ) == 0

            if container_id not in self._subscriptions:
                self._subscriptions[container_id] = []

            self._subscriptions[container_id].append(browser_ws)

        if is_first:
            await self._send_agent_command(host_id, "start_stats", container_id)
            logger.info(
                "Started stats stream for container",
                extra={"container_id": container_id, "host_id": host_id},
            )
        else:
            logger.debug(
                "Added subscriber to existing stats stream",
                extra={
                    "container_id": container_id,
                    "subscriber_count": len(self._subscriptions.get(container_id, [])),
                },
            )

    async def unsubscribe(
        self, container_id: str, browser_ws: WebSocket, host_id: str
    ) -> None:
        """Remove a browser WebSocket subscription for a container.

        If this was the last subscriber, sends a 'stop_stats' command
        to the agent to stop the stats goroutine.

        Args:
            container_id: Docker container ID to stop streaming
            browser_ws: The browser's WebSocket connection to remove
            host_id: The agent host_id that owns this container
        """
        send_stop = False

        async with self._lock:
            subs = self._subscriptions.get(container_id, [])
            if browser_ws in subs:
                subs.remove(browser_ws)

            # If no more subscribers, clean up and signal agent
            if len(subs) == 0:
                self._subscriptions.pop(container_id, None)
                send_stop = True

        if send_stop:
            await self._send_agent_command(host_id, "stop_stats", container_id)
            logger.info(
                "Stopped stats stream for container (no subscribers)",
                extra={"container_id": container_id, "host_id": host_id},
            )
        else:
            logger.debug(
                "Removed subscriber from stats stream",
                extra={
                    "container_id": container_id,
                    "remaining": len(self._subscriptions.get(container_id, [])),
                },
            )

    async def relay_stats(self, container_id: str, stats_data: dict) -> None:
        """Relay a stats frame from the agent to all subscribed browsers.

        Disconnected browsers are automatically removed from the subscription list.

        Args:
            container_id: The container this stats frame belongs to
            stats_data: The stats payload (cpu_percent, memory_usage, etc.)
        """
        async with self._lock:
            subs = self._subscriptions.get(container_id, [])
            if not subs:
                return
            # Copy list for iteration (may remove during send)
            subs_copy = list(subs)

        message = json.dumps(stats_data)
        disconnected: List[WebSocket] = []

        for ws in subs_copy:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)

        # Clean up disconnected sockets
        if disconnected:
            async with self._lock:
                subs = self._subscriptions.get(container_id, [])
                for ws in disconnected:
                    if ws in subs:
                        subs.remove(ws)
                if len(subs) == 0:
                    self._subscriptions.pop(container_id, None)

            logger.debug(
                "Removed disconnected subscribers",
                extra={
                    "container_id": container_id,
                    "removed_count": len(disconnected),
                },
            )

    async def _send_agent_command(
        self, host_id: str, action: str, container_id: str
    ) -> None:
        """Send a start_stats or stop_stats command to the agent.

        Args:
            host_id: The agent host_id to send the command to
            action: 'start_stats' or 'stop_stats'
            container_id: The container to start/stop stats for
        """
        from app.services.agent_registry import get_agent_registry

        registry = get_agent_registry()
        conn = registry.get_connection(host_id)

        if conn is None or not conn.online:
            logger.warning(
                "Cannot send stats command - agent not connected",
                extra={"host_id": host_id, "action": action, "container_id": container_id},
            )
            return

        command_envelope = json.dumps({
            "type": "command",
            "data": {
                "action": action,
                "container_id": container_id,
            },
        })

        try:
            await conn.websocket.send_text(command_envelope)
            logger.debug(
                "Sent stats command to agent",
                extra={"host_id": host_id, "action": action, "container_id": container_id},
            )
        except Exception:
            logger.exception(
                "Failed to send stats command to agent",
                extra={"host_id": host_id, "action": action, "container_id": container_id},
            )

    def get_subscriber_count(self, container_id: str) -> int:
        """Get the number of subscribers for a container (for diagnostics)."""
        return len(self._subscriptions.get(container_id, []))


def get_stats_relay() -> StatsRelay:
    """Get the singleton StatsRelay instance."""
    return StatsRelay()
