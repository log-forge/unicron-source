"""Container event emitters for alert services via internal namespace."""

from datetime import datetime, timezone
from typing import Optional

from app.core.logging import get_logger
from app.socket.constants import CONTAINER_EVENT, INTERNAL_NAMESPACE
from app.socket.socket_client import get_socket_server

logger = get_logger("socket.internal.alert_events")


async def emit_container_event(
    container_key: str,
    action: str,
    herald_id: str,
    organization_id: str,
    metadata: Optional[dict] = None,
) -> None:
    """Emit a container lifecycle event to the internal namespace.

    This event is consumed by alert-engine to trigger absence rules
    and update rule scopes dynamically.

    Args:
        container_key: The canonical container key
        action: Event type - one of: start, stop, die, create, destroy
        herald_id: The Herald agent that reported this container
        organization_id: The organization this container belongs to
        metadata: Optional additional metadata (container name, image, etc.)
    """
    server = get_socket_server()
    if server is None:
        logger.debug(
            "No socket server available; skipping container event emit",
            extra={"container_key": container_key, "action": action},
        )
        return

    payload = {
        "container_key": container_key,
        "action": action,
        "herald_id": herald_id,
        "organization_id": organization_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata or {},
    }

    try:
        await server.emit(CONTAINER_EVENT, payload, namespace=INTERNAL_NAMESPACE)
        logger.debug(
                "Emitted container event to internal namespace",
                extra={
                "container_key": container_key,
                "action": action,
                "herald_id": herald_id,
            },
        )
    except Exception:
        logger.warning(
            "Failed to emit container event",
            exc_info=True,
            extra={
                "container_key": container_key,
                "action": action,
                "herald_id": herald_id,
            },
        )


__all__ = ["emit_container_event"]
