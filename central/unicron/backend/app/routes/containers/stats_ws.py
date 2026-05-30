"""Browser-facing WebSocket endpoint for on-demand container stats streaming.

When a browser opens a container detail page, it connects here with the
container_id and host_id as query parameters. The StatsRelay service
subscribes the browser and signals the agent to start streaming stats.

When the browser disconnects (navigates away), the subscription is removed.
If no more browsers are watching, the agent is told to stop the stream.

Endpoint: /stats/ws (under /api/containers prefix)
Query params:
    - container_id (required): Docker container ID to stream stats for
    - host_id (required): Agent host ID that owns the container
"""

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette import status as ws_status

from app.core.logging import get_logger
from app.core.ws_auth import authenticate_browser_ws
from app.services.stats_relay import get_stats_relay

logger = get_logger("routes.container.stats_ws")

stats_ws_router = APIRouter()


@stats_ws_router.websocket("/stats/ws")
async def container_stats_websocket(
    websocket: WebSocket,
    container_id: str = Query(..., description="Container ID to stream stats for"),
    host_id: str = Query(..., description="Agent host ID owning the container"),
) -> None:
    """WebSocket endpoint for browser stats subscriptions.

    Protocol:
        1. Browser connects with container_id and host_id query params
        2. Server subscribes browser via StatsRelay (triggers start_stats on agent)
        3. Stats frames are pushed to browser as JSON messages
        4. On disconnect, server unsubscribes (triggers stop_stats if last viewer)

    Stats frame format (pushed to browser):
        {
            "container_id": "abc123",
            "cpu_percent": 12.5,
            "memory_usage": 134217728,
            "memory_limit": 536870912,
            "memory_percent": 25.0,
            "network_rx_bytes": 1048576,
            "network_tx_bytes": 524288,
            "block_read_bytes": 2097152,
            "block_write_bytes": 1048576,
            "timestamp": 1706000000
        }
    """
    await websocket.accept()

    user_id = await authenticate_browser_ws(websocket)
    if not user_id:
        await websocket.send_json({"type": "error", "code": "AUTH_REQUIRED", "message": "Authentication required"})
        await websocket.close(code=ws_status.WS_1008_POLICY_VIOLATION)
        return

    if not container_id or not host_id:
        await websocket.send_json({"type": "error", "code": "INVALID_REQUEST", "message": "container_id and host_id are required"})
        await websocket.close(code=1008)
        return

    relay = get_stats_relay()

    try:
        # Subscribe this browser to stats for the container
        await relay.subscribe(container_id, websocket, host_id)

        logger.debug(
            "Browser subscribed to container stats",
            extra={"container_id": container_id, "host_id": host_id},
        )

        # Keep the connection alive - read messages but ignore content
        # (browser doesn't send meaningful data, just keep-alives)
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception(
            "Error in container stats WebSocket",
            extra={"container_id": container_id, "host_id": host_id},
        )
    finally:
        # Always unsubscribe on disconnect
        await relay.unsubscribe(container_id, websocket, host_id)
        logger.debug(
            "Browser unsubscribed from container stats",
            extra={"container_id": container_id, "host_id": host_id},
        )
