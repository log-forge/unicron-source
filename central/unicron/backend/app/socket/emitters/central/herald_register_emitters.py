import logging
from typing import Optional

from app.core.access.herald_visibility import list_visible_herald_ids
from app.core.access.role_resolver import ActorContext
from app.core.database import session_ctx
from app.socket.auth import require_socket_permissions
from app.socket.constants import GLOBAL_ROOM, HERALD_REGISTER_EVENT_NAME
from app.socket.emitters.schemas import HeraldRegisterEventFailData, HeraldRegisterEventSuccessData
from app.utils.socket_io_utils import get_room_participants
from fastapi import HTTPException
from unicron_shared import HeraldStatus

logger = logging.getLogger(__name__)


async def emit_herald_registered(sio, herald_id: str, herald_token, room: Optional[str] = None):
    """Emit a success 'herald:registered' event.

    Args:
        sio: socketio.AsyncServer
        herald_id: str
        herald_token: object with herald_name, group, tags
        room: room to emit to; defaults to GLOBAL_ROOM
    """
    try:
        payload = HeraldRegisterEventSuccessData(
            herald_id=herald_id,
            herald_name=herald_token.herald_name,
            group=getattr(herald_token, "group", None),
            tags=getattr(herald_token, "tags", []),
            status=HeraldStatus.healthy,
        ).model_dump()
        if room:
            await sio.emit(HERALD_REGISTER_EVENT_NAME, payload, room=room)
            return
        await _emit_visible_herald_event(sio, herald_id, payload)
    except Exception as emit_exc:
        logger.warning("Socket emit failed: %s", emit_exc)


async def emit_herald_registration_failed(
    sio,
    herald_id: str,
    herald_name: str,
    reason: str,
    room: Optional[str] = None,
    token_only: bool = False,
    failure: dict | None = None,
):
    """Emit a failure 'herald:registered' event.

    Args:
        sio: socketio.AsyncServer
        herald_id: str
        herald_name: str
        reason: str
        room: optional room override; defaults to GLOBAL_ROOM
        token_only: emit to readers without Herald visibility filtering when no active Herald row exists
        failure: optional structured failure details
    """
    try:
        payload = HeraldRegisterEventFailData(
            herald_id=herald_id,
            herald_name=herald_name,
            status=HeraldStatus.failed,
            reason=reason,
            failure=failure,
        ).model_dump(exclude_none=True)
        if room:
            await sio.emit(HERALD_REGISTER_EVENT_NAME, payload, room=room)
            return
        if token_only:
            await _emit_herald_event_to_readers(sio, payload)
            return
        await _emit_visible_herald_event(sio, herald_id, payload)
    except Exception as emit_exc:
        logger.warning("Socket emit failed: %s", emit_exc)


async def _emit_visible_herald_event(sio, herald_id: str, payload: dict) -> None:
    participants = await get_room_participants(sio, GLOBAL_ROOM)
    for sid in participants:
        try:
            ctx = await require_socket_permissions(sio, sid, {"herald": ["read"]})
        except HTTPException:
            logger.debug("herald register emit: skip sid", extra={"sid": sid})
            continue

        actor = ctx.get("actor")
        if not actor:
            continue
        async with session_ctx() as session:
            visible = await list_visible_herald_ids(session, ActorContext(**actor))
        if herald_id in visible:
            await sio.emit(HERALD_REGISTER_EVENT_NAME, payload, to=sid)


async def _emit_herald_event_to_readers(sio, payload: dict) -> None:
    participants = await get_room_participants(sio, GLOBAL_ROOM)
    for sid in participants:
        try:
            await require_socket_permissions(sio, sid, {"herald": ["read"]})
        except HTTPException:
            logger.debug("herald register emit: skip sid", extra={"sid": sid})
            continue

        await sio.emit(HERALD_REGISTER_EVENT_NAME, payload, to=sid)


__all__ = [
    "HERALD_REGISTER_EVENT_NAME",
    "emit_herald_registered",
    "emit_herald_registration_failed",
]
