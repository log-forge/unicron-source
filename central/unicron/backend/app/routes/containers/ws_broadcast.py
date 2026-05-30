"""WebSocket broadcast endpoint for browser clients.

Manages a set of connected browser WebSocket clients and broadcasts
real-time container events, host status changes, and inventory updates.

Browser clients connect to /api/containers/ws and receive a read-only
stream of events. Authentication uses the local admin Better Auth cookie.

Message types sent to clients:
    - container_event: Single container state change (start/stop/die)
    - host_status: Host online/offline transition
    - inventory_update: Full container list refresh for a host
    - monitoring_state_changed: Container monitoring toggle confirmed
    - telemetry_health: Telemetry pipeline health status for a host
"""

import asyncio
import json
from typing import Any, Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette import status as ws_status

from app.core.logging import get_logger
from app.core.ws_auth import authenticate_browser_ws
from app.services.agent_registry import get_agent_registry

logger = get_logger("routes.containers.ws_broadcast")

router = APIRouter()


class ConnectionManager:
    """Manages connected browser WebSocket clients.

    Thread-safe with asyncio.Lock. Handles graceful disconnect
    cleanup during broadcast operations.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active_connections: List[WebSocket] = []

    async def register(self, websocket: WebSocket) -> None:
        """Register a browser WebSocket connection (must already be accepted)."""
        async with self._lock:
            self._active_connections.append(websocket)
        logger.debug(
            "Browser WebSocket connected",
            extra={"total_connections": len(self._active_connections)},
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a browser WebSocket connection."""
        async with self._lock:
            try:
                self._active_connections.remove(websocket)
            except ValueError:
                pass
        logger.debug(
            "Browser WebSocket disconnected",
            extra={"total_connections": len(self._active_connections)},
        )

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Send a JSON message to all connected browser clients.

        Automatically removes disconnected clients encountered during broadcast.
        """
        if not self._active_connections:
            return

        payload = json.dumps(message)
        disconnected: List[WebSocket] = []

        async with self._lock:
            connections = list(self._active_connections)

        for connection in connections:
            try:
                await connection.send_text(payload)
            except Exception:
                disconnected.append(connection)

        # Clean up disconnected clients
        if disconnected:
            async with self._lock:
                for conn in disconnected:
                    try:
                        self._active_connections.remove(conn)
                    except ValueError:
                        pass
            logger.debug(
                "Removed disconnected browser clients",
                extra={"removed": len(disconnected)},
            )


# Singleton connection manager
_manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """Get the singleton ConnectionManager instance."""
    return _manager


async def broadcast_container_event(event: Dict[str, Any]) -> None:
    """Broadcast a container event to all connected browser clients.

    Called by agent ws_handler when a container_event message arrives.

    Args:
        event: Container event dict with container_id, name, action, status, host_id
    """
    await _manager.broadcast({"type": "container_event", "data": event})


async def broadcast_host_status(host_id: str, online: bool) -> None:
    """Broadcast a host status change to all connected browser clients.

    Called when a host goes online (agent connects) or offline (heartbeat timeout).

    Args:
        host_id: The agent host identifier
        online: Whether the host is now online
    """
    await _manager.broadcast(
        {"type": "host_status", "data": {"host_id": host_id, "online": online}}
    )


async def broadcast_inventory_update(
    host_id: str, containers: List[Dict[str, Any]]
) -> None:
    """Broadcast a full inventory update for a host to browser clients.

    Called after processing an inventory message from an agent.

    Args:
        host_id: The agent host identifier
        containers: Full list of containers for this host
    """
    await _manager.broadcast(
        {"type": "inventory_update", "data": {"host_id": host_id, "containers": containers}}
    )


async def broadcast_monitoring_state(
    container_id: str, host_id: str, enabled: bool
) -> None:
    """Broadcast a monitoring state change to all connected browser clients.

    Called after agent acknowledges a monitoring toggle command.

    Args:
        container_id: The container identifier
        host_id: The agent host that owns the container
        enabled: New monitoring enabled state
    """
    await _manager.broadcast({
        "type": "monitoring_state_changed",
        "data": {
            "container_id": container_id,
            "host_id": host_id,
            "monitoring_enabled": enabled,
        },
    })


async def broadcast_telemetry_health(host_id: str, healthy: bool, timestamp: int) -> None:
    """Broadcast telemetry pipeline health status to browser clients.

    Called when agent reports OTel/Fluent Bit health transition.

    Args:
        host_id: The agent host identifier
        healthy: Whether the telemetry pipeline is healthy
        timestamp: Unix timestamp of the health change
    """
    await _manager.broadcast({
        "type": "telemetry_health",
        "data": {
            "host_id": host_id,
            "healthy": healthy,
            "timestamp": timestamp,
        },
    })


@router.websocket("/ws")
async def browser_container_websocket(websocket: WebSocket) -> None:
    """WebSocket endpoint for browser clients to receive container updates.

    Protocol:
        1. Browser connects to /api/containers/ws
        2. Server validates the local admin cookie before accepting
        3. Server sends initial state (hosts with online status)
        4. Server pushes events as they arrive (container_event, host_status, inventory_update)
        5. Connection is read-only from client perspective (client messages ignored)

    Authentication via local admin cookie is required.
    This endpoint is designed for browser tabs subscribing to live updates.
    """
    await websocket.accept()

    user_id = await authenticate_browser_ws(websocket)
    if not user_id:
        await websocket.send_json({"type": "error", "code": "AUTH_REQUIRED", "message": "Authentication required"})
        await websocket.close(code=ws_status.WS_1008_POLICY_VIOLATION)
        return

    await _manager.register(websocket)

    try:
        # Send initial state: current hosts with online status and monitoring states
        from app.services.container_cache import get_container_cache

        registry = get_agent_registry()
        hosts = registry.list_hosts()

        # Get all monitoring states
        cache = get_container_cache()
        monitoring_states = await cache.get_all_monitoring_states()

        initial_state = {
            "type": "initial_state",
            "data": {
                "hosts": [
                    {"host_id": hid, "online": conn.online}
                    for hid, conn in hosts.items()
                ],
                "monitoring_states": monitoring_states,
            },
        }
        await websocket.send_json(initial_state)

        # Keep connection alive - read-only stream (ignore client messages)
        while True:
            try:
                # Wait for messages (handles pings/pongs automatically)
                # We read but ignore any client data (read-only stream)
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("Browser WebSocket error", exc_info=True)
    finally:
        await _manager.disconnect(websocket)
