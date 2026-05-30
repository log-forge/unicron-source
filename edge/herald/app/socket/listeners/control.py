"""Control-channel event handlers for the Herald client.

Handlers here attach to the Socket.IO AsyncClient used to maintain the
control connection to the backend. Keeping these separate makes it easy
to add more event groups and stay consistent with the backend layout.
"""

from typing import Any

import socketio
from app.core.logging import get_logger
from app.tasks.health.report_health import stop_socket_heartbeat

from unicron_shared import AckOk, PongData

logger = get_logger(__name__)


def register_control_events(sio: socketio.AsyncClient) -> None:
    """Register control channel events on the given client instance."""

    @sio.event
    async def connect():
        logger.info("[herald] control connected")

    @sio.event
    async def disconnect():
        logger.info("[herald] control disconnected")
        # stop scheduled heartbeat when disconnected
        stop_socket_heartbeat()

    # Server-initiated health/heartbeat message (optional)
    @sio.event
    async def beat(data: Any | None = None):
        # Respond with an AckOk so the server can treat this as an ACK flow if desired
        return AckOk[PongData](ok=True, data=PongData(msg="ok")).model_dump()

    # Simple ping/pong utility; mirrors backend AckOk[PongData]
    @sio.event
    async def ping(data: Any | None = None):
        return AckOk[PongData](ok=True, data=PongData(msg="pong")).model_dump()
