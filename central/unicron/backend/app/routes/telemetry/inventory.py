from datetime import datetime, timezone
from typing import List

from app.core.access.role_resolver import ActorContext, list_accessible_container_keys
from app.core.database import get_session
from app.core.deps import get_actor_context, require_permission
from app.models.container.container_model import Container
from app.models.container.crud.container_crud import list_containers_by_keys
from app.models.herald.herald_model import Herald
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import ContainerInventoryRecord, HeraldInventoryRecord, InventorySnapshotResponse

router = APIRouter(prefix="/inventory", tags=["telemetry", "inventory"])


def _map_heralds(heralds: List[Herald]) -> List[HeraldInventoryRecord]:
    records: List[HeraldInventoryRecord] = []
    for herald in heralds:
        data = {
            "herald_id": herald.id,
            "herald_name": herald.herald_name,
            "central_url": herald.central_url,
            "registered_at": herald.registered_at,
            "health_status": herald.health_status,
            "last_ping": herald.last_ping,
            "health_message": getattr(herald, "health_message", None),
            "check_in_interval": herald.check_in_interval,
            "region": getattr(herald, "region", None),
            "tags": sorted(list(getattr(herald, "tags", []) or [])),
            "socket_online": getattr(herald, "socket_online", False),
            "socket_last_seen": getattr(herald, "socket_last_seen", None),
            "hostname": getattr(herald, "hostname", None),
            "herald_os": getattr(herald, "herald_os", None),
            "os_version": getattr(herald, "os_version", None),
            "architecture": getattr(herald, "architecture", None),
            "cpu_count": getattr(herald, "cpu_count", None),
            "host_total_memory_bytes": getattr(herald, "host_total_memory_bytes", None),
            "herald_version": getattr(herald, "herald_version", None),
        }
        records.append(HeraldInventoryRecord.model_validate(data))
    return records


def _map_containers(containers: List[Container]) -> List[ContainerInventoryRecord]:
    records: List[ContainerInventoryRecord] = []
    for container in containers:
        group_obj = getattr(container, "group", None)
        group_name = getattr(group_obj, "name", None) if group_obj is not None else None

        data = {
            "name": container.name,
            "container_key": container.container_key,
            "docker_container_id": getattr(container, "docker_container_id", None),
            "status": getattr(container, "status", None),
            "started_at": getattr(container, "started_at", None),
            "monitoring_enabled": bool(getattr(container, "monitoring_enabled", False)),
            "group": group_name,
            "image": getattr(container, "image", None),
            "image_id": getattr(container, "image_id", None),
            "labels": dict(getattr(container, "labels", {}) or {}),
            "cpu_limit": getattr(container, "cpu_limit", None),
            "memory_limit_bytes": getattr(container, "memory_limit_bytes", None),
            "restart_policy": getattr(container, "restart_policy", None),
            "created_at": getattr(container, "created_at", None),
            "command": getattr(container, "command", None),
            "entrypoint": getattr(container, "entrypoint", None),
            "working_dir": getattr(container, "working_dir", None),
            "environment": list(getattr(container, "environment", []) or []),
            "mounts": list(getattr(container, "mounts", []) or []),
            "ports": dict(getattr(container, "ports", {}) or {}),
            "networks": dict(getattr(container, "networks", {}) or {}),
        }
        records.append(ContainerInventoryRecord.model_validate(data))
    return records


@router.get(
    "/herald",
    response_model=InventorySnapshotResponse,
    dependencies=[Depends(require_permission({"telemetry": ["read"]}))],
)
async def get_inventory_snapshot(
    session: AsyncSession = Depends(get_session),
    actor: ActorContext = Depends(get_actor_context),
) -> InventorySnapshotResponse:
    generated_at = datetime.now(timezone.utc)

    accessible_container_keys = await list_accessible_container_keys(session, actor, min_role="read_only")
    containers = await list_containers_by_keys(session, accessible_container_keys)

    herald_ids = sorted({container.herald_id for container in containers if container.herald_id})
    heralds: List[Herald] = []
    if herald_ids:
        herald_stmt = (
            select(Herald)
            .where(getattr(Herald, "id").in_(herald_ids))
            .where(getattr(Herald, "unregistered") == False)  # noqa: E712
            .order_by(getattr(Herald, "registered_at").asc())
        )
        herald_result = await session.execute(herald_stmt)
        heralds = list(herald_result.scalars().all())

    containers = sorted(containers, key=lambda container: (container.name or ""))

    return InventorySnapshotResponse(
        generated_at=generated_at,
        heralds=_map_heralds(heralds),
        containers=_map_containers(containers),
    )
