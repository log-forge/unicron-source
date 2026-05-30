from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from app.models.container.container_model import Container
from app.models.container.crud.container_crud import set_container_group, upsert_containers_batch
from app.services.container_identity import build_container_key
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from unicron_shared import ContainerState


@dataclass(frozen=True)
class InventorySyncResult:
    containers: list[Container]
    created_container_keys: list[str]
    removed_container_keys: list[str]
    monitoring_disabled_container_keys: list[str]
    processed_at: datetime


class InventorySyncService:
    async def sync_inventory(
        self,
        session: AsyncSession,
        *,
        herald_id: str,
        containers: Iterable[ContainerState],
    ) -> InventorySyncResult:
        processed_at = datetime.now(timezone.utc)
        seen_keys: set[str] = set()
        upsert_payloads: list[dict] = []
        group_by_key: dict[str, str | None] = {}

        for container_state in containers:
            name = str(container_state.name or "").strip()
            if not name:
                continue
            container_key = build_container_key(herald_id, name)
            if container_key in seen_keys:
                continue
            seen_keys.add(container_key)

            upsert_payloads.append(
                {
                    "name": name,
                    "docker_container_id": str(container_state.docker_container_id or "").strip() or None,
                    "herald_id": herald_id,
                    "status": container_state.status,
                    "started_at": container_state.started_at,
                    # Monitoring policy is Central-owned durable state. Agent
                    # inventory is observational and must not reset it.
                    "monitoring_enabled": None,
                    "static_metrics": container_state.static,
                    "last_inventory_at": processed_at,
                }
            )
            group_by_key[container_key] = container_state.group

        synced, created_keys = await upsert_containers_batch(session, upsert_payloads, commit=False)
        by_key = {container.container_key: container for container in synced}

        for container_key, group_name in group_by_key.items():
            container = by_key.get(container_key)
            if container is None:
                continue
            await set_container_group(session, container, group_name, commit=False)

        rows = list(
            (
                await session.execute(
                    select(Container).where(getattr(Container, "herald_id") == herald_id)
                )
            )
            .scalars()
            .all()
        )
        removed_keys: list[str] = []
        monitoring_disabled_keys: list[str] = []

        for container in rows:
            container_key = str(container.container_key or "").strip()
            if not container_key or container_key in seen_keys:
                continue

            changed = False
            if bool(container.monitoring_enabled):
                container.monitoring_enabled = False
                monitoring_disabled_keys.append(container_key)
                changed = True

            if container.status != "removed":
                container.status = "removed"
                removed_keys.append(container_key)
                changed = True

            if changed:
                session.add(container)

        if removed_keys or monitoring_disabled_keys:
            await session.flush()

        return InventorySyncResult(
            containers=synced,
            created_container_keys=created_keys,
            removed_container_keys=removed_keys,
            monitoring_disabled_container_keys=monitoring_disabled_keys,
            processed_at=processed_at,
        )


_SERVICE = InventorySyncService()


def get_inventory_sync_service() -> InventorySyncService:
    return _SERVICE


__all__ = ["InventorySyncResult", "InventorySyncService", "get_inventory_sync_service"]
