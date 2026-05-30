from datetime import datetime, timezone

import socketio
from app.core.database import get_session
from app.core.deps.deps import get_socketio_server
from app.core.logging import get_logger
from app.models.herald.crud.herald_crud import set_socket_presence, update_herald_health
from app.models.herald.crud.herald_token_crud import (
    get_herald_token,
    get_latest_bootstrapped_go_streamer_token_by_name,
    update_herald_token_status,
)
from app.routes.herald.schemas import HeraldRegisterFailRequest, HeraldRegisterFailResponse
from app.socket.emitters.central.health import emit_herald_health_update
from app.socket.emitters.central.herald_register_emitters import emit_herald_registration_failed
from app.utils.herald_register_state import build_register_failure_message
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from unicron_shared import HeraldStatus

exception_router = APIRouter()
logger = get_logger(__name__)


@exception_router.post("/register/fail", response_model=HeraldRegisterFailResponse)
async def register_herald_fail(
    payload: HeraldRegisterFailRequest,
    sio: socketio.AsyncServer = Depends(get_socketio_server),
    session: AsyncSession = Depends(get_session),
):
    if not payload.herald_id:
        raise HTTPException(400, "Missing required field: herald_id")

    herald_id = payload.herald_id.strip()
    if not herald_id:
        raise HTTPException(400, "Missing required field: herald_id")

    raw_name = payload.herald_name or ""
    herald_name = raw_name.strip() or herald_id

    failure_payload = getattr(payload, "failure", None)
    if isinstance(failure_payload, dict):
        failure_details = failure_payload
    else:
        failure_details = failure_payload.model_dump(exclude_none=True) if failure_payload else None

    raw_reason = str(payload.reason or (failure_details or {}).get("message") or "unspecified")
    reason = raw_reason.strip() or "unspecified"

    herald_token = await get_herald_token(session, herald_id)
    if herald_token is None:
        herald_token = await get_latest_bootstrapped_go_streamer_token_by_name(session, herald_name)
    if herald_token is not None:
        await update_herald_token_status(session, str(herald_token.id), "expired", reason=reason)

    now = datetime.now(timezone.utc)
    updated = await update_herald_health(
        session,
        herald_id,
        HeraldStatus.failed,
        now,
        build_register_failure_message(reason),
    )
    if updated is not None:
        updated = await set_socket_presence(session, herald_id, False, at=now)

    logger.info("Herald registration failed: id=%s, name=%s, reason=%s", herald_id, herald_name, reason)

    if updated is not None:
        await emit_herald_health_update(updated, sio=sio)
    await emit_herald_registration_failed(
        sio,
        herald_id,
        herald_name,
        reason,
        failure=failure_details,
    )

    return HeraldRegisterFailResponse(
        success=True,
        status="expired",
        herald_id=herald_id,
        reason=reason,
    )
