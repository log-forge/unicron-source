"""Container Overview REST API endpoint.

Serves container inventory data (hosts + containers) from Redis cache
with PostgreSQL fallback for the Container Overview UI page.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.logging import get_logger
from app.models.container.crud.container_crud import list_active_containers
from app.models.herald.crud.herald_crud import list_registered_herald_ids_by_ids
from app.services.container_cache import get_container_cache

logger = get_logger("routes.container.overview")

containers_overview_router = APIRouter()


def _epoch_to_iso(epoch_seconds: Optional[int]) -> Optional[str]:
    """Convert epoch seconds to ISO-8601 UTC string."""
    if epoch_seconds is None:
        return None
    try:
        return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat()
    except Exception:
        return None


# ── Response schemas ────────────────────────────────────────────────────────


class HostInfo(BaseModel):
    host_id: str
    online: bool
    container_count: int
    last_seen: Optional[str] = None


class ContainerOverviewItem(BaseModel):
    container_key: str
    docker_container_id: Optional[str] = None
    name: str
    status: Optional[str] = None
    image: Optional[str] = None
    host_id: Optional[str] = None
    labels: Dict[str, str] = {}
    ports: List[dict] = []
    started_at: Optional[str] = None
    monitoring_enabled: bool = False
    log_collection_status: Optional[str] = None
    log_collection_issue: Optional[str] = None


class ContainerOverviewResponse(BaseModel):
    hosts: List[HostInfo]
    containers: List[ContainerOverviewItem]


def _log_collection_state_for_container(
    host_id: str,
    container_key: str,
    log_collection_states: Dict[str, Dict[str, Dict[str, Any]]],
) -> tuple[Optional[str], Optional[str]]:
    if not host_id or not container_key:
        return None, None

    state = log_collection_states.get(host_id, {}).get(container_key)
    if not isinstance(state, dict):
        return None, None

    status = state.get("log_collection_status")
    issue = state.get("log_collection_issue")
    status_value = str(status).strip() if isinstance(status, str) else None
    issue_value = str(issue).strip() if isinstance(issue, str) and issue.strip() else None
    return status_value or None, issue_value


def _resolve_monitoring_enabled(
    container_key: str,
    cached_value: bool,
    monitoring_states: Dict[str, bool],
) -> bool:
    if container_key in monitoring_states:
        return bool(monitoring_states[container_key])
    return bool(cached_value)


def _build_overview_item(
    *,
    host_id: str,
    container_key: str,
    docker_container_id: Optional[str],
    name: str,
    status: Optional[str],
    image: Optional[str],
    labels: Dict[str, str],
    ports: List[dict],
    started_at: Optional[str],
    monitoring_enabled: bool,
    monitoring_states: Dict[str, bool],
    log_collection_states: Dict[str, Dict[str, Dict[str, Any]]],
) -> ContainerOverviewItem:
    log_status, log_issue = _log_collection_state_for_container(
        host_id,
        container_key,
        log_collection_states,
    )
    kwargs: Dict[str, Any] = {
        "container_key": container_key,
        "docker_container_id": docker_container_id,
        "name": name,
        "status": status,
        "image": image,
        "host_id": host_id,
        "labels": labels,
        "ports": ports,
        "started_at": started_at,
        "monitoring_enabled": _resolve_monitoring_enabled(
            container_key,
            monitoring_enabled,
            monitoring_states,
        ),
    }
    if log_status is not None:
        kwargs["log_collection_status"] = log_status
    if log_issue is not None:
        kwargs["log_collection_issue"] = log_issue
    return ContainerOverviewItem(**kwargs)


def _container_to_cache_payload(container: Any, host_id: str) -> Dict[str, Any]:
    return {
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
    }


def _group_db_containers_by_host(containers: List[Any]) -> Dict[str, List[Any]]:
    grouped: Dict[str, List[Any]] = {}
    for container in containers:
        host_id = container.herald_id or "local"
        grouped.setdefault(host_id, []).append(container)
    return grouped


def _cached_payload_needs_db_backfill(payload: Dict[str, Any]) -> bool:
    return any(
        key not in payload
        for key in ("labels", "ports", "started_at", "monitoring_enabled")
    )


def _filter_response(
    response: ContainerOverviewResponse,
    visible_keys: Optional[set[str]],
) -> ContainerOverviewResponse:
    if visible_keys is None:
        return response

    containers = [container for container in response.containers if container.container_key in visible_keys]
    counts_by_host: dict[str, int] = {}
    for container in containers:
        if container.host_id:
            counts_by_host[container.host_id] = counts_by_host.get(container.host_id, 0) + 1

    hosts = [
        HostInfo(
            host_id=host.host_id,
            online=host.online,
            container_count=counts_by_host.get(host.host_id, 0),
            last_seen=host.last_seen,
        )
        for host in response.hosts
        if counts_by_host.get(host.host_id, 0) > 0
    ]
    return ContainerOverviewResponse(hosts=hosts, containers=containers)


async def _filter_registered_cache_hosts(
    session: AsyncSession,
    cache: Any,
    host_ids: list[str],
) -> list[str]:
    """Keep cache-backed host projections aligned with active herald lifecycle."""
    if not host_ids:
        return []

    registered_ids = set(await list_registered_herald_ids_by_ids(session, host_ids))
    stale_ids = [host_id for host_id in host_ids if host_id not in registered_ids]
    if stale_ids:
        await asyncio.gather(
            *(cache.remove_host(host_id) for host_id in stale_ids),
            return_exceptions=True,
        )
    return [host_id for host_id in host_ids if host_id in registered_ids]


# ── Endpoint ────────────────────────────────────────────────────────────────


@containers_overview_router.get("/overview", response_model=ContainerOverviewResponse)
async def get_container_overview(
    session: AsyncSession = Depends(get_session),
) -> ContainerOverviewResponse:
    """Get container overview data from Redis cache with PostgreSQL fallback.

    Strategy:
      1. Try Redis cache first (fast path): get all hosts, then containers per host.
      2. If cache is empty or Redis unavailable, fall back to PostgreSQL.
      3. Build response with host online status and container details.
    """
    cache = get_container_cache()
    visible_keys: Optional[set[str]] = None

    # ── Try Redis cache first ───────────────────────────────────────────────
    host_ids_raw = await cache.get_all_hosts()
    host_ids = [
        host_id.decode("utf-8") if isinstance(host_id, bytes) else str(host_id)
        for host_id in host_ids_raw
    ]
    host_ids = await _filter_registered_cache_hosts(session, cache, host_ids)

    if host_ids:
        (
            host_statuses,
            host_last_seen,
            host_status_changed_at,
            host_containers,
            empty_online_hosts,
        ) = await cache.get_overview_snapshot(host_ids)
        _, _, _, host_container_counts = await cache.get_host_status_snapshot(host_ids)
        monitoring_states = await cache.get_all_monitoring_states()
        log_collection_states = await cache.get_log_collection_states_for_hosts(host_ids)

        if empty_online_hosts:
            await asyncio.gather(
                *(cache.request_inventory_if_empty(host_id) for host_id in empty_online_hosts),
                return_exceptions=True,
            )

        hosts_needing_recovery = [
            host_id
            for host_id in host_ids
            if host_container_counts.get(host_id, 0) > len(host_containers.get(host_id, []))
        ]
        hosts_with_incomplete_payloads = {
            host_id
            for host_id in host_ids
            if any(
                _cached_payload_needs_db_backfill(container_payload)
                for container_payload in host_containers.get(host_id, [])
            )
        }
        hosts_needing_db = sorted(set(hosts_needing_recovery) | hosts_with_incomplete_payloads)
        db_containers_by_host: Dict[str, List[Any]] = {}
        if hosts_needing_db:
            db_containers_by_host = _group_db_containers_by_host(await list_active_containers(session))

        hosts: List[HostInfo] = []
        all_containers: List[ContainerOverviewItem] = []
        recovered_count = 0
        repaired_payload_count = 0
        cache_repair_tasks: List[Any] = []

        for host_id in host_ids:
            merged_containers: List[ContainerOverviewItem] = []
            seen_container_keys: set[str] = set()
            db_containers_for_host = {
                container.container_key: container
                for container in db_containers_by_host.get(host_id, [])
            }

            for c in host_containers.get(host_id, []):
                if _cached_payload_needs_db_backfill(c):
                    db_container = db_containers_for_host.get(c.get("container_key", ""))
                    if db_container is not None:
                        c = _container_to_cache_payload(db_container, host_id)
                        cache_repair_tasks.append(
                            cache.cache_single_container(
                                host_id,
                                c,
                            )
                        )
                        repaired_payload_count += 1

                item = _build_overview_item(
                    host_id=host_id,
                    container_key=c.get("container_key", ""),
                    docker_container_id=c.get("docker_container_id"),
                    name=c.get("name", ""),
                    status=c.get("status"),
                    image=c.get("image"),
                    labels=c.get("labels") or {},
                    ports=c.get("ports") or [],
                    started_at=str(c["started_at"]) if c.get("started_at") else None,
                    monitoring_enabled=bool(c.get("monitoring_enabled", False)),
                    monitoring_states=monitoring_states,
                    log_collection_states=log_collection_states,
                )
                merged_containers.append(item)
                if item.container_key:
                    seen_container_keys.add(item.container_key)

            if host_id in hosts_needing_recovery:
                for container in db_containers_for_host.values():
                    if container.container_key in seen_container_keys:
                        continue

                    merged_containers.append(
                        _build_overview_item(
                            host_id=host_id,
                            container_key=container.container_key,
                            docker_container_id=container.docker_container_id,
                            name=container.name,
                            status=container.status,
                            image=container.image,
                            labels=container.labels or {},
                            ports=container.ports or [],
                            started_at=str(container.started_at) if container.started_at else None,
                            monitoring_enabled=bool(container.monitoring_enabled),
                            monitoring_states=monitoring_states,
                            log_collection_states=log_collection_states,
                        )
                    )
                    cache_repair_tasks.append(
                        cache.cache_single_container(
                            host_id,
                            _container_to_cache_payload(container, host_id),
                        )
                    )
                    recovered_count += 1

            host_online = host_statuses.get(host_id)

            hosts.append(
                HostInfo(
                    host_id=host_id,
                    online=host_online if host_online is not None else False,
                    container_count=len(merged_containers),
                    last_seen=_epoch_to_iso(host_last_seen.get(host_id) or host_status_changed_at.get(host_id)),
                )
            )

            all_containers.extend(merged_containers)

        if cache_repair_tasks:
            await asyncio.gather(*cache_repair_tasks, return_exceptions=True)

        logger.debug(
            "Served overview from Redis cache",
            extra={
                "hosts": len(hosts),
                "containers": len(all_containers),
                "recovered_from_db": recovered_count,
                "repaired_payloads": repaired_payload_count,
            },
        )
        return _filter_response(ContainerOverviewResponse(hosts=hosts, containers=all_containers), visible_keys)

    # ── PostgreSQL fallback ─────────────────────────────────────────────────
    logger.debug("Redis cache empty, falling back to PostgreSQL")

    db_containers = await list_active_containers(session)

    # Group containers by herald_id (host)
    hosts_map: Dict[str, List[ContainerOverviewItem]] = {}
    for host_id in _group_db_containers_by_host(db_containers).keys():
        hosts_map[host_id] = []

    monitoring_states = await cache.get_all_monitoring_states()
    log_collection_states = await cache.get_log_collection_states_for_hosts(list(hosts_map.keys()))

    for container in db_containers:
        host_id = container.herald_id or "local"
        hosts_map[host_id].append(
            _build_overview_item(
                host_id=host_id,
                container_key=container.container_key,
                docker_container_id=container.docker_container_id,
                name=container.name,
                status=container.status,
                image=container.image,
                labels=container.labels or {},
                ports=container.ports or [],
                started_at=str(container.started_at) if container.started_at else None,
                monitoring_enabled=bool(container.monitoring_enabled),
                monitoring_states=monitoring_states,
                log_collection_states=log_collection_states,
            )
        )

    # Build host info from grouped data (status unknown from DB)
    fallback_hosts = [
        HostInfo(
            host_id=hid,
            online=False,  # Cannot determine from DB alone
            container_count=len(containers),
        )
        for hid, containers in hosts_map.items()
    ]

    fallback_containers = [c for containers in hosts_map.values() for c in containers]

    return _filter_response(ContainerOverviewResponse(hosts=fallback_hosts, containers=fallback_containers), visible_keys)
