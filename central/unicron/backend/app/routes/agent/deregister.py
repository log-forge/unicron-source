"""Agent deregistration API endpoint for remote go-streamer agents.

Provides:
- DELETE /{agent_id}/deregister: Immediately disconnect and revoke an agent
"""

from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps.permissions import require_permission
from app.core.logging import get_logger
from app.models.herald.crud.herald_crud import mark_herald_unregistered
from app.models.herald.crud.herald_token_crud import (
    update_herald_token_status,
)
from app.services.agent_registry import get_agent_registry
from app.services.container_cache import get_container_cache
from app.services.realtime_event_bus import get_realtime_event_bus

logger = get_logger("routes.agent.deregister")

router = APIRouter()


class DeregisterResponse(BaseModel):
    """Response payload for agent deregistration."""
    ok: bool
    agent_id: str
    message: str


@router.delete("/{agent_id}/deregister", response_model=DeregisterResponse)
async def deregister_agent(
    agent_id: str,
    session: AsyncSession = Depends(get_session),
    _auth: None = Depends(require_permission({"herald": ["delete"]})),
) -> DeregisterResponse:
    """Deregister and disconnect a go-streamer agent immediately.

    This endpoint:
    1. Marks herald/token state as unregistered when records exist (durable revocation)
    2. Persists + broadcasts revocation via Redis so all replicas disconnect the agent
    3. Removes Redis host/cache projections so decommissioned agents disappear
    4. Broadcasts a removal event to connected browsers

    Args:
        agent_id: The agent host identifier to decommission
        session: Database session

    Returns:
        DeregisterResponse with success confirmation
    """
    registry = get_agent_registry()
    cache = get_container_cache()
    updated_herald = None

    # Mark durable herald/token state when available.
    try:
        updated_herald = await mark_herald_unregistered(session, agent_id, reason="admin", by="admin")
        if updated_herald:
            await update_herald_token_status(session, agent_id, "unregistered", reason="admin")
    except Exception:
        logger.warning(
            "Failed to persist herald unregistered status during agent deregistration",
            exc_info=True,
            extra={"agent_id": agent_id},
        )

    # Best-effort self-destruct command while connection is still available.
    decommission_request_id = uuid4().hex
    sent_decommission = await registry.send_command(
        agent_id,
        "agent_decommission",
        {
            "request_id": decommission_request_id,
            "reason": "Agent decommissioned by admin",
            "wipe_data": True,
        },
    )
    logger.info(
        "Issued agent decommission command",
        extra={
            "agent_id": agent_id,
            "request_id": decommission_request_id,
            "sent": sent_decommission,
        },
    )

    # Denylist last-known certificate identity so old certs cannot reconnect.
    cert_fingerprint_sha256, cert_serial_hex = await registry.revoke_cert_identity(
        agent_id,
        reason="Agent decommissioned by admin",
    )
    logger.info(
        "Applied certificate revocation for agent",
        extra={
            "agent_id": agent_id,
            "has_fingerprint": bool(cert_fingerprint_sha256),
            "has_serial": bool(cert_serial_hex),
        },
    )

    # Persist and broadcast revocation so all replicas enforce disconnect.
    await registry.revoke(agent_id, reason="Agent decommissioned by admin")
    logger.info("Agent revocation broadcasted", extra={"agent_id": agent_id})

    # Remove host cache state so it disappears from host/agent lists immediately.
    await cache.remove_host(agent_id)

    # Broadcast removal to browsers. A normal disconnect is different: it stays visible as offline.
    await get_realtime_event_bus().emit_host_status(
        host_id=agent_id,
        online=False,
        removed=True,
        reason="decommissioned",
    )

    logger.info(
        "Agent deregistered and disconnected",
        extra={"agent_id": agent_id}
    )

    return DeregisterResponse(
        ok=True,
        agent_id=agent_id,
        message=f"Agent {agent_id} decommissioned successfully",
    )
