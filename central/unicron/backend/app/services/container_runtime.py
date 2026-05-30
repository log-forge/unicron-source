from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.database import session_ctx
from app.core.logging import get_logger
from app.models.container.crud.container_crud import get_container_by_key, upsert_container
from app.services.alerting.streams import publish_container_event
from app.services.container_cache import get_container_cache
from app.services.container_identity import build_container_key, normalize_container_name
from app.services.realtime_event_bus import get_realtime_event_bus
from unicron_shared import ContainerStaticMetrics

logger = get_logger("services.container_runtime")


def _parse_event_started_at(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        dt = raw
    else:
        value = str(raw or "").strip()
        if not value:
            return None
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _coerce_event_labels(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}

    labels: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        if value is None:
            continue
        if isinstance(value, str):
            labels[key] = value
            continue
        if isinstance(value, (int, float, bool)):
            labels[key] = str(value)
    return labels


def _build_event_static_metrics(payload: dict[str, Any]) -> ContainerStaticMetrics | None:
    labels = _coerce_event_labels(payload.get("labels"))
    if not labels:
        return None

    image = str(payload.get("image") or "").strip() or None
    kwargs: dict[str, Any] = {"labels": labels}
    if image:
        kwargs["image"] = image
    return ContainerStaticMetrics(**kwargs)


@dataclass(frozen=True)
class ContainerRuntimeEvent:
    host_id: str
    container_key: str
    name: str
    docker_container_id: str | None
    action: str
    status: str | None


class ContainerRuntimeService:
    def build_runtime_event(self, host_id: str, payload: dict[str, Any]) -> ContainerRuntimeEvent:
        name = normalize_container_name(str(payload.get("name") or ""))
        return ContainerRuntimeEvent(
            host_id=host_id,
            container_key=build_container_key(host_id, name),
            name=name,
            docker_container_id=str(payload.get("docker_container_id") or payload.get("container_id") or "").strip() or None,
            action=str(payload.get("action") or "").strip(),
            status=str(payload.get("status") or "").strip() or None,
        )

    async def apply_lifecycle_event(self, host_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = self.build_runtime_event(host_id, payload)
        cache = get_container_cache()

        if event.action not in {
            "destroy",
            "die",
            "stop",
            "start",
            "create",
            "kill",
            "restart",
            "pause",
            "unpause",
        }:
            return {
                "host_id": event.host_id,
                "container_key": event.container_key,
                "name": event.name,
                "docker_container_id": event.docker_container_id,
                "action": event.action,
                "status": event.status,
            }

        # Docker emits `die` / `kill` when a container exits but still exists.
        # Only `destroy` means the container should disappear from overview.
        if event.action == "destroy":
            await cache.remove_container(host_id, event.container_key)
            await cache.clear_log_collection_state(host_id, event.container_key)
            container_name = event.name
            container_image = ""
            docker_container_id = event.docker_container_id or ""
            was_monitored = False

            async with session_ctx() as session:
                container = await get_container_by_key(session, event.container_key)
                if container is not None:
                    container_name = container.name or container_name
                    container_image = container.image or ""
                    docker_container_id = container.docker_container_id or docker_container_id
                    was_monitored = bool(container.monitoring_enabled)
                    container.status = "removed"
                    container.monitoring_enabled = False
                    session.add(container)
                    await session.commit()

            await cache.clear_monitoring_state(event.container_key)
            if was_monitored:
                event_payload = {
                    "type": "monitoring_state_changed",
                    "herald_id": host_id,
                    "host_id": host_id,
                    "container_key": event.container_key,
                    "name": container_name,
                    "container_id": docker_container_id,
                    "image": container_image,
                    "status": "removed",
                    "enabled": False,
                }
                try:
                    await publish_container_event(event_payload)
                except Exception:
                    logger.warning(
                        "Failed to publish monitoring disable from destroy event",
                        exc_info=True,
                        extra={"host_id": host_id, "container_key": event.container_key},
                    )
                await get_realtime_event_bus().emit_monitoring_state_changed(
                    container_key=event.container_key,
                    host_id=host_id,
                    monitoring_enabled=False,
                )
        else:
            started_at = _parse_event_started_at(payload.get("started_at"))
            static_metrics = _build_event_static_metrics(payload)
            async with session_ctx() as session:
                container, _ = await upsert_container(
                    session,
                    herald_id=host_id,
                    name=event.name,
                    docker_container_id=event.docker_container_id,
                    status=event.status,
                    started_at=started_at,
                    static_metrics=static_metrics,
                    last_inventory_at=datetime.now(timezone.utc),
                    commit=True,
                )
            await cache.cache_single_container(
                host_id,
                {
                    "container_key": container.container_key,
                    "docker_container_id": container.docker_container_id,
                    "name": container.name,
                    "status": container.status,
                    "image": container.image,
                    "host_id": host_id,
                    "labels": container.labels or {},
                    "ports": container.ports or [],
                    "started_at": str(container.started_at) if container.started_at else None,
                    "monitoring_enabled": bool(container.monitoring_enabled),
                },
            )

        browser_payload = {
            "host_id": event.host_id,
            "container_key": event.container_key,
            "name": event.name,
            "docker_container_id": event.docker_container_id,
            "action": event.action,
            "status": event.status,
        }
        await get_realtime_event_bus().emit_container_event(browser_payload)
        return browser_payload


_SERVICE = ContainerRuntimeService()


def get_container_runtime_service() -> ContainerRuntimeService:
    return _SERVICE


__all__ = ["ContainerRuntimeService", "ContainerRuntimeEvent", "get_container_runtime_service"]
