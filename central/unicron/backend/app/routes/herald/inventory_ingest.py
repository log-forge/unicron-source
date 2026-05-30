from datetime import datetime, timezone
from typing import List

from app.core.access.herald_visibility import list_visible_herald_ids
from app.core.access.role_resolver import ActorContext
from app.core.database import get_session
from app.core.deps import get_actor_context, get_socketio_server, require_permission
from app.core.deps.herald import require_registered_herald
from app.core.logging import get_logger
from app.models.herald.crud.herald_crud import update_herald_static_metrics
from app.models.herald.crud.herald_token_crud import get_herald_token
from app.models.herald.herald_model import Herald
from app.services.container_cache import get_container_cache
from app.services.inventory_sync import get_inventory_sync_service
from app.services.realtime_event_bus import get_realtime_event_bus
from app.socket.emitters.edge.inventory import request_inventory_refresh
from app.socket.emitters.internal.alert_events import emit_container_event
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from unicron_shared import HeraldInventoryPayload, HeraldInventoryResponse, InventoryTriggerAck

router = APIRouter()
admin_router = APIRouter()
logger = get_logger(__name__)


async def _emit_container_events(
    session: AsyncSession,
    herald_id: str,
    new_container_keys: List[str],
) -> None:
    """Emit container events for newly discovered containers."""
    if not new_container_keys:
        return

    # Get organization_id from herald token
    herald_token = await get_herald_token(session, herald_id)
    organization_id = herald_token.organization_id if herald_token else ""

    for container_key in new_container_keys:
        try:
            await emit_container_event(
                container_key=container_key,
                action="start",
                herald_id=herald_id,
                organization_id=organization_id,
            )
        except Exception:
            logger.warning(
                "Failed to emit container start event",
                exc_info=True,
                extra={"container_key": container_key, "herald_id": herald_id},
            )


def _container_name_from_key(container_key: str) -> str:
    return str(container_key or "").split(":", 1)[1] if ":" in str(container_key or "") else str(container_key or "")


async def _apply_inventory_reconciliation_side_effects(
    *,
    session: AsyncSession,
    herald_id: str,
    sync_result,
) -> None:
    removed_keys = list(dict.fromkeys(sync_result.removed_container_keys or []))
    disabled_keys = list(dict.fromkeys(sync_result.monitoring_disabled_container_keys or []))
    if not removed_keys and not disabled_keys:
        return

    cache = get_container_cache()
    realtime = get_realtime_event_bus()

    for container_key in removed_keys:
        await cache.remove_container(herald_id, container_key)

    for container_key in list(dict.fromkeys([*removed_keys, *disabled_keys])):
        await cache.clear_monitoring_state(container_key)
        await cache.clear_log_collection_state(herald_id, container_key)

    for container_key in disabled_keys:
        name = _container_name_from_key(container_key)
        try:
            from app.services.alerting.streams import publish_container_event

            await publish_container_event(
                {
                    "type": "monitoring_state_changed",
                    "herald_id": herald_id,
                    "host_id": herald_id,
                    "container_key": container_key,
                    "name": name,
                    "container_id": "",
                    "image": "",
                    "status": "removed" if container_key in removed_keys else "",
                    "enabled": False,
                }
            )
        except Exception:
            logger.warning(
                "Failed to publish monitoring disable from herald inventory reconciliation",
                exc_info=True,
                extra={"herald_id": herald_id, "container_key": container_key},
            )
        await realtime.emit_monitoring_state_changed(
            container_key=container_key,
            host_id=herald_id,
            monitoring_enabled=False,
        )

    if removed_keys:
        herald_token = await get_herald_token(session, herald_id)
        organization_id = herald_token.organization_id if herald_token else ""
        for container_key in removed_keys:
            name = _container_name_from_key(container_key)
            try:
                await emit_container_event(
                    container_key=container_key,
                    action="destroy",
                    herald_id=herald_id,
                    organization_id=organization_id,
                )
            except Exception:
                logger.warning(
                    "Failed to emit container destroy event",
                    exc_info=True,
                    extra={"container_key": container_key, "herald_id": herald_id},
                )
            await realtime.emit_container_event(
                {
                    "host_id": herald_id,
                    "container_key": container_key,
                    "name": name,
                    "docker_container_id": None,
                    "action": "destroy",
                    "status": "removed",
                }
            )


@router.post("/inventory", response_model=HeraldInventoryResponse)
async def ingest_inventory(
    payload: HeraldInventoryPayload,
    session: AsyncSession = Depends(get_session),
    herald: Herald = Depends(require_registered_herald),
) -> HeraldInventoryResponse:
    if payload.herald_id and payload.herald_id != herald.id:
        logger.warning(
            "Herald ID mismatch on inventory submission", extra={"payload": payload.herald_id, "spiffe": herald.id}
        )
        raise HTTPException(status_code=403, detail="Herald identity mismatch")

    processed_at = datetime.now(timezone.utc)

    if payload.herald_static is not None:
        try:
            await update_herald_static_metrics(session, herald.id, payload.herald_static)
        except Exception as exc:
            logger.error(
                "Failed to persist herald static metrics",
                exc_info=True,
                extra={"herald_id": herald.id},
            )

    sync_service = get_inventory_sync_service()
    realtime = get_realtime_event_bus()
    try:
        sync_result = await sync_service.sync_inventory(
            session,
            herald_id=herald.id,
            containers=payload.containers,
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.error(
            "Failed to persist container inventory",
            exc_info=True,
            extra={"herald_id": herald.id},
        )
        raise HTTPException(status_code=500, detail="Failed to persist container inventory") from exc

    # Emit container events for newly discovered containers
    # This is non-blocking - failures are logged but don't affect the response
    await _emit_container_events(session, herald.id, sync_result.created_container_keys)
    await _apply_inventory_reconciliation_side_effects(
        session=session,
        herald_id=herald.id,
        sync_result=sync_result,
    )
    await realtime.emit_inventory_update(
        {
            "host_id": herald.id,
            "containers": [
                {
                    "container_key": container.container_key,
                    "docker_container_id": container.docker_container_id,
                    "name": container.name,
                    "status": container.status,
                    "image": container.image,
                    "labels": container.labels or {},
                    "ports": container.ports or {},
                    "started_at": str(container.started_at) if container.started_at else None,
                    "monitoring_enabled": bool(container.monitoring_enabled),
                }
                for container in sync_result.containers
            ],
        }
    )

    return HeraldInventoryResponse(
        accepted=True,
        accepted_sequence=payload.sequence,
        processed_at=sync_result.processed_at,
    )


@admin_router.post(
    "/inventory/refresh/{target_herald_id}",
    response_model=InventoryTriggerAck,
    dependencies=[Depends(require_permission({"herald": ["update"]}))],
)
async def request_inventory_refresh_endpoint(
    target_herald_id: str,
    sio=Depends(get_socketio_server),
    session: AsyncSession = Depends(get_session),
    actor: ActorContext = Depends(get_actor_context),
) -> InventoryTriggerAck:
    visible = await list_visible_herald_ids(session, actor)
    if target_herald_id not in visible:
        raise HTTPException(status_code=403, detail="Herald not visible")

    ok, ack = await request_inventory_refresh(sio, target_herald_id)
    if not ok:
        raise HTTPException(status_code=503, detail="Herald did not acknowledge inventory refresh request")

    if ack is None:
        logger.info("Inventory refresh request acknowledged without payload", extra={"herald_id": target_herald_id})
        return InventoryTriggerAck()

    return ack
