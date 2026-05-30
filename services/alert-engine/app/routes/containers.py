"""REST API endpoint for container listing.

Exposes MONITORED containers from the Redis container registry.
Only containers with monitoring enabled are stored in the registry.
Data flows: Central monitoring toggle -> Redis Stream -> container_stream_consumer -> registry.

The authenticated local admin sees all monitored containers.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import UserContext, require_authenticated_user
from app.core.logging import get_logger
from app.schemas.container_schemas import (
    ContainerListResponse,
    ContainerResponse,
    GroupMember,
    GroupResponse,
)
from app.services.container_registry import get_container_registry
from app.services.container_service import ContainerService

logger = get_logger("alert-engine.routes.containers")

router = APIRouter(prefix="/containers", tags=["containers"])


@router.get(
    "",
    response_model=ContainerListResponse,
    summary="List monitored containers",
    description="List containers with monitoring enabled. Reads from Redis container registry (push-based, not query-time filtering).",
)
async def list_containers(
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
    include_containers: bool = Query(
        True, description="Include paged monitored containers in response."
    ),
    include_groups: bool = Query(
        True, description="Include paged groups in response."
    ),
    container_offset: int = Query(0, ge=0, description="Container pagination offset"),
    container_limit: int = Query(
        500, ge=1, le=2000, description="Container page size"
    ),
    group_offset: int = Query(0, ge=0, description="Group pagination offset"),
    group_limit: int = Query(200, ge=1, le=1000, description="Group page size"),
) -> ContainerListResponse:
    """
    List containers with monitoring enabled.

    Reads from the Redis container registry which is populated by
    monitoring_state_changed events from Central via Redis Stream.
    Only monitored containers exist in the registry.

    Falls back to empty list if registry is unavailable.

    Returns containers and their groups for monitored containers only.
    """
    # Read from Redis container registry (populated via stream).
    # Registry query is paged; callers can continue until has_more_containers is false.
    registry = get_container_registry()
    registry_total = await registry.count()
    registry_containers = []
    if include_containers:
        registry_containers = await registry.list_containers(
            offset=container_offset,
            limit=container_limit,
        )

    # Self-heal after cold starts where monitoring keys already exist but the
    # registry was initialized before those keys were restored.
    if include_containers and container_offset == 0 and not registry_containers:
        bootstrapped = await registry.bootstrap_from_monitoring_keys(clear_existing=False)
        if bootstrapped:
            registry_total = await registry.count()
            registry_containers = await registry.list_containers(
                offset=container_offset,
                limit=container_limit,
            )

    logger.debug(
        "Registry returned %d monitored containers (offset=%d page_size=%d total=%d)",
        len(registry_containers),
        container_offset,
        container_limit,
        registry_total,
    )

    # Build container responses from paged registry data.
    container_responses = []

    for c in registry_containers:
        host_id = c.get("host_id", "local") or "local"
        name = c.get("name", "unknown")
        container_id = c.get("container_id", "")
        short_id = container_id[:12] if container_id else ""
        identifier = f"{host_id}:{name}:{short_id}"
        last_seen = c.get("last_seen", datetime.now(timezone.utc).isoformat())

        container_responses.append(
            ContainerResponse(
                identifier=identifier,
                name=name,
                host_id=host_id if host_id != "local" else None,
                container_id=container_id,
                image_name=c.get("image", ""),
                last_seen=last_seen,
                status=c.get("status"),
                labels={},  # Labels not stored in registry (lightweight)
            )
        )

    group_responses = []
    groups_total = 0
    groups_page_count = 0

    if include_groups:
        # Group support: query PostgreSQL for paged groups and batch-fetch members.
        # Return every group regardless of whether its members are monitored,
        # so the frontend can display groups persistently. The monitored counts
        # let the UI show how many members are actively monitored.
        monitored_names = await registry.list_container_refs()

        try:
            service = ContainerService(session)
            groups, groups_total = await service.list_groups_paginated(
                offset=group_offset,
                limit=group_limit,
            )
            groups_page_count = len(groups)

            members_by_group = await service.get_group_members_for_groups(
                [g.id for g in groups]
            )

            for g in groups:
                all_members = members_by_group.get(g.id, [])
                if not all_members:
                    continue  # Skip empty groups (orphan rows)

                monitored_members = [
                    (h, n) for h, n in all_members if (h, n) in monitored_names
                ]

                container_ids = [f"{h}:{n}" for h, n in all_members]
                members = [
                    GroupMember(host_id=h, container_name=n) for h, n in all_members
                ]
                monitored_ids = [f"{h}:{n}" for h, n in monitored_members]

                group_responses.append(
                    GroupResponse(
                        groupId=g.id,
                        name=g.name or "",
                        containerIds=container_ids,
                        members=members if members else None,
                        monitoredContainerCount=len(monitored_members),
                        monitoredContainers=monitored_ids if monitored_ids else None,
                    )
                )
        except Exception as e:
            logger.warning("Failed to load groups: %s", str(e))

    logger.debug(
        "Listed %d containers, %d groups for user %s (groups_total=%d)",
        len(container_responses),
        len(group_responses),
        user.user_id,
        groups_total,
    )

    return ContainerListResponse(
        containers=container_responses if include_containers else [],
        groups=group_responses if include_groups else [],
        total_containers=registry_total,
        total_groups=groups_total if include_groups else 0,
        container_offset=container_offset if include_containers else 0,
        container_limit=container_limit if include_containers else 0,
        group_offset=group_offset if include_groups else 0,
        group_limit=group_limit if include_groups else 0,
        has_more_containers=(
            bool(include_containers)
            and (container_offset + len(container_responses) < registry_total)
        ),
        has_more_groups=(
            bool(include_groups)
            and (group_offset + groups_page_count < groups_total)
        ),
    )


__all__ = ["router"]
