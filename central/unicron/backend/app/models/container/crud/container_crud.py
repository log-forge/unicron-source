from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.models.container.container_model import Container
from app.models.group.crud.group_crud import ensure_group
from app.models.group.group_model import Group
from app.models.herald.herald_model import Herald
from app.services.container_identity import (
    ResolvedContainerIdentity,
    get_container_identity_service,
)
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select
from unicron_shared import ContainerStaticMetrics


async def get_container(session: AsyncSession, container_pk: str) -> Optional[Container]:
    return await session.get(Container, container_pk)


async def get_container_by_key(session: AsyncSession, container_key: str) -> Optional[Container]:
    identity_service = get_container_identity_service()
    return await identity_service.get_by_container_key(session, container_key)


async def get_container_by_docker_id(session: AsyncSession, docker_container_id: str) -> Optional[Container]:
    stmt = select(Container).where(getattr(Container, "docker_container_id") == docker_container_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_containers(session: AsyncSession) -> List[Container]:
    stmt = select(Container).order_by(getattr(Container, "name").asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def list_active_containers(session: AsyncSession) -> List[Container]:
    """List present containers whose owning herald is still registered."""
    stmt = (
        select(Container)
        .join(Herald, getattr(Container, "herald_id") == getattr(Herald, "id"))
        .where(getattr(Herald, "unregistered") == False)  # noqa: E712
        .where(or_(getattr(Container, "status").is_(None), getattr(Container, "status") != "removed"))
        .order_by(getattr(Container, "name").asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_containers_by_keys(session: AsyncSession, container_keys: list[str]) -> List[Container]:
    if not container_keys:
        return []

    stmt = (
        select(Container)
        .where(getattr(Container, "container_key").in_(container_keys))
        .options(selectinload(getattr(Container, "group")))
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _apply_container_updates(
    container: Container,
    *,
    identity: ResolvedContainerIdentity,
    herald_id: Optional[str] = None,
    status: Optional[str] = None,
    started_at: Optional[datetime] = None,
    monitoring_enabled: Optional[bool] = None,
    static_metrics: Optional[ContainerStaticMetrics] = None,
    last_inventory_at: Optional[datetime] = None,
) -> None:
    container.name = identity.name
    container.container_key = identity.container_key
    container.docker_container_id = identity.docker_container_id

    if status is not None:
        container.status = status
    if started_at is not None:
        container.started_at = started_at
    if monitoring_enabled is not None:
        container.monitoring_enabled = monitoring_enabled
    if herald_id is not None:
        container.herald_id = herald_id
    if last_inventory_at is not None:
        container.last_inventory_at = last_inventory_at
    if static_metrics is not None:
        # Pydantic v2 tracks explicitly provided fields on model creation.
        # Honor that set so partial lifecycle updates (e.g. labels-only from
        # container_event) do not wipe existing static metadata.
        fields_set = getattr(static_metrics, "model_fields_set", None)
        if fields_set is None:
            fields_set = getattr(static_metrics, "__fields_set__", set())
        provided_fields = set(fields_set or ())

        if "image" in provided_fields:
            container.image = static_metrics.image or container.image
        if "image_id" in provided_fields:
            container.image_id = static_metrics.image_id or container.image_id
        if "labels" in provided_fields:
            container.labels = dict(static_metrics.labels or {})
        if "cpu_limit" in provided_fields:
            container.cpu_limit = static_metrics.cpu_limit
        if "memory_limit_bytes" in provided_fields:
            container.memory_limit_bytes = static_metrics.memory_limit_bytes
        if "restart_policy" in provided_fields:
            container.restart_policy = static_metrics.restart_policy or container.restart_policy
        if "created_at" in provided_fields:
            container.created_at = static_metrics.created_at or container.created_at
        if "command" in provided_fields:
            container.command = static_metrics.command or container.command
        if "entrypoint" in provided_fields:
            container.entrypoint = static_metrics.entrypoint or container.entrypoint
        if "working_dir" in provided_fields:
            container.working_dir = static_metrics.working_dir or container.working_dir
        if "environment" in provided_fields:
            container.environment = list(static_metrics.environment or [])
        if "mounts" in provided_fields:
            container.mounts = list(static_metrics.mounts or [])
        if "ports" in provided_fields:
            container.ports = dict(static_metrics.ports or {})
        if "networks" in provided_fields:
            container.networks = dict(static_metrics.networks or {})


async def upsert_container(
    session: AsyncSession,
    *,
    herald_id: str,
    name: str,
    docker_container_id: str | None = None,
    status: Optional[str] = None,
    started_at: Optional[datetime] = None,
    monitoring_enabled: Optional[bool] = None,
    static_metrics: Optional[ContainerStaticMetrics] = None,
    last_inventory_at: Optional[datetime] = None,
    commit: bool = True,
    refresh: bool = True,
) -> Tuple[Container, bool]:
    identity_service = get_container_identity_service()
    identity, container = await identity_service.find_inventory_match(
        session,
        herald_id=herald_id,
        name=name,
        docker_container_id=docker_container_id,
    )

    created = container is None
    if created:
        container = Container(
            name=identity.name,
            container_key=identity.container_key,
            docker_container_id=identity.docker_container_id,
            herald_id=herald_id,
            last_inventory_at=last_inventory_at or datetime.now(timezone.utc),
        )
        session.add(container)

    _apply_container_updates(
        container,
        identity=identity,
        herald_id=herald_id,
        status=status,
        started_at=started_at,
        monitoring_enabled=monitoring_enabled,
        static_metrics=static_metrics,
        last_inventory_at=last_inventory_at,
    )

    if commit:
        await session.commit()
    else:
        await session.flush()
    if refresh:
        await session.refresh(container)
    return container, created


async def upsert_containers_batch(
    session: AsyncSession,
    items: List[Dict[str, Any]],
    *,
    commit: bool = True,
) -> Tuple[List[Container], List[str]]:
    if not items:
        return [], []

    identity_service = get_container_identity_service()
    deduped: Dict[str, Dict[str, Any]] = {}
    for raw in items:
        herald_id = str(raw.get("herald_id") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not herald_id or not name:
            continue
        identity = identity_service.build_identity(
            herald_id=herald_id,
            name=name,
            docker_container_id=raw.get("docker_container_id"),
        )
        deduped[identity.container_key] = {**raw, "_identity": identity}

    if not deduped:
        return [], []

    herald_ids = sorted({str(payload.get("herald_id") or "").strip() for payload in deduped.values()})
    docker_ids = sorted(
        {
            str(payload.get("docker_container_id") or "").strip()
            for payload in deduped.values()
            if str(payload.get("docker_container_id") or "").strip()
        }
    )

    existing_by_key: Dict[str, Container] = {}
    stmt = select(Container).where(getattr(Container, "container_key").in_(list(deduped.keys())))
    existing_by_key.update(
        {container.container_key: container for container in (await session.execute(stmt)).scalars().all()}
    )

    existing_by_runtime: Dict[tuple[str, str], Container] = {}
    if herald_ids and docker_ids:
        runtime_stmt = (
            select(Container)
            .where(getattr(Container, "herald_id").in_(herald_ids))
            .where(getattr(Container, "docker_container_id").in_(docker_ids))
        )
        for container in (await session.execute(runtime_stmt)).scalars().all():
            if container.herald_id and container.docker_container_id:
                existing_by_runtime[(container.herald_id, container.docker_container_id)] = container

    created_keys: List[str] = []
    upserted: List[Container] = []

    for container_key, payload in deduped.items():
        identity: ResolvedContainerIdentity = payload["_identity"]
        container = existing_by_key.get(container_key)
        if container is None and identity.docker_container_id:
            container = existing_by_runtime.get((identity.herald_id, identity.docker_container_id))

        created = container is None
        if created:
            container = Container(
                name=identity.name,
                container_key=identity.container_key,
                docker_container_id=identity.docker_container_id,
                herald_id=identity.herald_id,
            )
            session.add(container)
            created_keys.append(identity.container_key)

        _apply_container_updates(
            container,
            identity=identity,
            herald_id=payload.get("herald_id"),
            status=payload.get("status"),
            started_at=payload.get("started_at"),
            monitoring_enabled=payload.get("monitoring_enabled"),
            static_metrics=payload.get("static_metrics"),
            last_inventory_at=payload.get("last_inventory_at"),
        )
        existing_by_key[identity.container_key] = container
        if identity.docker_container_id:
            existing_by_runtime[(identity.herald_id, identity.docker_container_id)] = container
        upserted.append(container)

    if commit:
        await session.commit()
    else:
        await session.flush()

    return upserted, created_keys


async def delete_container(session: AsyncSession, container_pk: str) -> bool:
    container = await session.get(Container, container_pk)
    if container is None:
        return False

    await session.delete(container)
    await session.commit()
    return True


async def clear_container_group(
    session: AsyncSession,
    container: Container,
    *,
    commit: bool = True,
) -> bool:
    previous_group = container.group_id
    if previous_group is None:
        return False

    container.group_id = None
    session.add(container)
    if commit:
        await session.commit()
        await session.refresh(container)
    else:
        await session.flush()
    return True


async def set_container_group(
    session: AsyncSession,
    container: Container,
    group_name: Optional[str],
    *,
    commit: bool = True,
) -> Optional[Group]:
    normalized = (group_name or "").strip()
    if not normalized:
        await clear_container_group(session, container, commit=commit)
        return None

    group = await ensure_group(session, normalized, commit=commit)

    if container.group_id != group.id:
        container.group_id = group.id
        session.add(container)
        if commit:
            await session.commit()
            await session.refresh(container)
        else:
            await session.flush()
    else:
        if commit:
            await session.refresh(container, attribute_names=["group"])

    return group


__all__ = [
    "clear_container_group",
    "delete_container",
    "get_container",
    "get_container_by_docker_id",
    "get_container_by_key",
    "list_containers",
    "list_containers_by_keys",
    "set_container_group",
    "upsert_container",
    "upsert_containers_batch",
]
