from typing import Optional

import socketio
from app.core.access.herald_visibility import list_visible_herald_ids
from app.core.access.role_resolver import ActorContext
from app.core.database import session_ctx
from app.core.logging import get_logger
from app.models.herald.herald_model import Herald
from app.socket.auth import require_socket_permissions
from app.socket.constants import GLOBAL_ROOM, HEALTH_EVENT_NAME
from app.socket.emitters.schemas import HeraldHealthEventPayload
from app.socket.socket_client import get_socket_server
from app.utils.socket_io_utils import get_room_participants
from fastapi import HTTPException
from unicron_shared import HeraldStatus

logger = get_logger("socket.telemetry.health")


def _coerce_status(raw_status: object) -> HeraldStatus:
    if isinstance(raw_status, HeraldStatus):
        return raw_status
    try:
        return HeraldStatus(str(raw_status))
    except Exception:  # pragma: no cover - defensive fallback
        return HeraldStatus.unknown


def build_health_payload(herald: Herald) -> HeraldHealthEventPayload:
    """Map a Herald ORM instance to a socket health payload."""
    return HeraldHealthEventPayload(
        herald_id=herald.id,
        herald_name=herald.herald_name,
        status=_coerce_status(getattr(herald, "health_status", HeraldStatus.unknown)),
        message=getattr(herald, "health_message", None) or None,
        last_ping=getattr(herald, "last_ping", None),
        registered_at=getattr(herald, "registered_at", None),
        check_in_interval=getattr(herald, "check_in_interval", None),
        socket_online=bool(getattr(herald, "socket_online", False)),
        socket_last_seen=getattr(herald, "socket_last_seen", None),
        region=getattr(herald, "region", None),
        tags=list(getattr(herald, "tags", []) or []),
        central_url=getattr(herald, "central_url", None),
        herald_version=getattr(herald, "herald_version", None),
        hostname=getattr(herald, "hostname", None),
        herald_os=getattr(herald, "herald_os", None),
        os_version=getattr(herald, "os_version", None),
        architecture=getattr(herald, "architecture", None),
        cpu_count=getattr(herald, "cpu_count", None),
        host_total_memory_bytes=getattr(herald, "host_total_memory_bytes", None),
    )


async def emit_herald_health_update(
    herald: Herald,
    *,
    sio: Optional[socketio.AsyncServer] = None,
    room: Optional[str] = None,
) -> None:
    """Broadcast a health update for a herald to interested clients."""
    server = sio or get_socket_server()
    if server is None:
        logger.debug("No socket server available; skipping health emit for herald %s", getattr(herald, "id", "?"))
        return

    try:
        payload = build_health_payload(herald)
        data = payload.model_dump(mode="json", exclude_none=True)
    except Exception:
        logger.warning("Failed to serialize health payload for herald %s", getattr(herald, "id", "?"), exc_info=True)
        return

    target_room = room or GLOBAL_ROOM
    if target_room != GLOBAL_ROOM:
        try:
            await server.emit(HEALTH_EVENT_NAME, data, room=target_room)
        except Exception:  # pragma: no cover - socket emit failure guard
            logger.warning(
                "Failed to emit herald health update for %s to room %s",
                getattr(herald, "id", "?"),
                target_room,
                exc_info=True,
            )
        return

    participants = await get_room_participants(server, GLOBAL_ROOM)
    for sid in participants:
        try:
            ctx = await require_socket_permissions(server, sid, {"herald": ["read"]})
        except HTTPException:
            logger.debug("health emit: skip sid", extra={"sid": sid})
            continue

        actor = ctx.get("actor")
        if not actor:
            continue
        async with session_ctx() as session:
            visible = await list_visible_herald_ids(session, ActorContext(**actor))
        if herald.id in visible:
            await server.emit(HEALTH_EVENT_NAME, data, to=sid)


__all__ = ["HEALTH_EVENT_NAME", "build_health_payload", "emit_herald_health_update"]
