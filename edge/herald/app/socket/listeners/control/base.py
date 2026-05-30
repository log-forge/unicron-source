from typing import Any

import socketio
from app.core.logging import get_logger
from app.tasks.health.report_health import stop_socket_heartbeat

from unicron_shared import AckOk, PongData

__all__ = ["register_base_control_events"]

logger = get_logger(__name__)


def register_base_control_events(sio: socketio.AsyncClient) -> None:
    """Attach fundamental control-channel event handlers."""

    @sio.event
    async def connect():
        logger.info("[herald] control connected")

    @sio.event
    async def disconnect():
        logger.info("[herald] control disconnected")
        stop_socket_heartbeat()

    @sio.event
    async def beat(data: Any | None = None):
        """Respond to a backend heartbeat with an AckOk payload."""

        return AckOk[PongData](ok=True, data=PongData(msg="ok")).model_dump()

    @sio.event
    async def ping(data: Any | None = None):
        """Classic ping/pong utility hook."""

        return AckOk[PongData](ok=True, data=PongData(msg="pong")).model_dump()
