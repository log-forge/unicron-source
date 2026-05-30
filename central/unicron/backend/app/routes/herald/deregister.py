from typing import Optional

import socketio
from app.core.database import get_session
from app.core.deps import get_socketio_server, require_permission
from app.core.deps.herald import require_registered_herald
from app.core.logging import get_logger
from app.models.herald.crud.herald_crud import mark_herald_unregistered
from app.models.herald.crud.herald_token_crud import update_herald_token_status
from app.models.herald.herald_model import Herald
from app.routes.herald.schemas import HeraldRegisterResponse
from app.services.agent_registry import get_agent_registry
from app.services.container_cache import get_container_cache
from app.services.realtime_event_bus import get_realtime_event_bus
from app.utils.socket_io_utils import disconnect_room
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["deregister"])
admin_router = APIRouter(tags=["deregister"])
logger = get_logger(__name__)


class AdminDeregisterBody(BaseModel):
    reason: Optional[str] = None


@router.post("/deregister", response_model=HeraldRegisterResponse)
async def self_deregister(
    session: AsyncSession = Depends(get_session),
    sio: Optional[socketio.AsyncServer] = Depends(get_socketio_server),
    herald: Herald = Depends(require_registered_herald),
):
    registry = get_agent_registry()
    cache = get_container_cache()

    updated = await mark_herald_unregistered(session, herald.id, reason="self", by="self")
    if not updated:
        raise HTTPException(status_code=404, detail="Herald not found")
    await update_herald_token_status(session, herald.id, "unregistered", reason="self")
    await registry.revoke(herald.id, reason="Herald self-deregistered")
    await cache.remove_host(herald.id)
    await get_realtime_event_bus().emit_host_status(
        host_id=herald.id,
        online=False,
        removed=True,
        reason="deregistered",
    )

    try:
        if sio:
            await disconnect_room(sio, f"herald:{herald.id}")
    except Exception:
        logger.debug("deregister: failed to disconnect socket for %s", herald.id, exc_info=True)

    return HeraldRegisterResponse(success=True, status="unregistered", herald_id=herald.id)


@admin_router.post(
    "/deregister/{target_herald_id}",
    response_model=HeraldRegisterResponse,
    dependencies=[Depends(require_permission({"herald": ["delete"]}))],
)
async def admin_deregister(
    target_herald_id: str,
    payload: AdminDeregisterBody,
    session: AsyncSession = Depends(get_session),
    sio: Optional[socketio.AsyncServer] = Depends(get_socketio_server),
):
    registry = get_agent_registry()
    cache = get_container_cache()

    reason = payload.reason or "admin"
    updated = await mark_herald_unregistered(session, target_herald_id, reason=reason, by="admin")
    if not updated:
        raise HTTPException(status_code=404, detail="Herald not found")
    await update_herald_token_status(session, target_herald_id, "unregistered", reason=reason)
    await registry.revoke(target_herald_id, reason=f"Herald deregistered: {reason}")
    await cache.remove_host(target_herald_id)
    await get_realtime_event_bus().emit_host_status(
        host_id=target_herald_id,
        online=False,
        removed=True,
        reason="deregistered",
    )

    try:
        if sio:
            await disconnect_room(sio, f"herald:{target_herald_id}")
    except Exception:
        logger.debug("deregister: failed to disconnect socket for %s", target_herald_id, exc_info=True)

    return HeraldRegisterResponse(success=True, status="unregistered", herald_id=target_herald_id)
