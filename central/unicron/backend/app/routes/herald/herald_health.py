from datetime import datetime, timezone

from app.core.database import get_session
from app.core.deps import require_spiffe_pair
from app.core.deps.herald import require_registered_herald
from app.core.logging import get_logger
from app.models.herald.crud.herald_crud import update_herald_health
from app.models.herald.herald_model import Herald
from app.socket.emitters.central.health import emit_herald_health_update
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.routes.herald.schemas import HeraldMtlsResponse
from unicron_shared import HeraldHealthRequest, HeraldHealthResponse

router = APIRouter()
logger = get_logger(__name__)


@router.post("/health", response_model=HeraldHealthResponse)
async def herald_health(
    payload: HeraldHealthRequest,
    session: AsyncSession = Depends(get_session),
    herald: Herald = Depends(require_registered_herald),
):
    # logger.debug("Incoming headers: %s", dict(request.headers))
    herald_name, status, timestamp, message = (
        payload.herald_name,
        payload.status or "unknown",
        payload.timestamp,
        payload.message or "",
    )
    if not timestamp:
        raise HTTPException(400, "Missing timestamp")

    # Parse timestamp to datetime
    try:
        last_ping = datetime.fromisoformat(timestamp)
        if last_ping.tzinfo is None:
            last_ping = last_ping.replace(tzinfo=timezone.utc)
    except Exception:
        last_ping = datetime.now(timezone.utc)

    updated = await update_herald_health(session, herald.id, status, last_ping, message)
    if not updated:
        logger.warning("Herald not found: name=%s, id=%s", herald_name, herald.id)
        raise HTTPException(404, "Herald not found")

    try:
        await emit_herald_health_update(updated)
    except Exception:
        logger.debug("herald:health: failed to emit socket update for herald %s", herald.id, exc_info=True)

    logger.info("Herald health updated: name=%s, id=%s, status=%s", herald_name, herald.id, status)
    return HeraldHealthResponse(success=True, herald_name=herald_name, herald_id=herald.id, status=status)


@router.get("/mtls", response_model=HeraldMtlsResponse)
def mtls_test(spiffe: tuple[str, str] = Depends(require_spiffe_pair)) -> HeraldMtlsResponse:
    """mTLS test endpoint. Returns a tuple of (herald_id, common_name)."""
    herald_id, common_name = spiffe
    logger.info("mTLS test successful for SPIFFE workload=%s common_name=%s", herald_id, common_name)
    return HeraldMtlsResponse(success=True, herald_id=herald_id, common_name=common_name)
