"""REST API endpoints for container group management.

Provides CRUD operations for organizing containers into groups.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import UserContext, require_authenticated_user
from app.core.logging import get_logger
from app.schemas.group_schemas import (
    GroupCreate,
    GroupUpdate,
    GroupDetailResponse,
    GroupMemberInfo,
    GroupOperationResponse,
)
from app.services.container_websocket import get_container_websocket_service
from app.services.group_cache import sync_group_cache, delete_group_cache
from app.services.group_service import (
    GroupService,
    GroupNotFoundError,
    GroupValidationError,
)

logger = get_logger("alert-engine.routes.groups")

router = APIRouter(prefix="/groups", tags=["groups"])


async def _build_group_response(service: GroupService, group_id: str) -> GroupDetailResponse:
    """Build detailed group response with member info."""
    group = await service.get_group(group_id)
    if not group:
        raise GroupNotFoundError(f"Group {group_id} not found")

    members = await service.get_group_members(group_id)
    member_infos = [
        GroupMemberInfo(
            container_id=c.container_id,
            name=c.name,
            host_id=c.herald_id,
        )
        for c in members
    ]

    return GroupDetailResponse(
        id=group.id,
        name=group.name or "",
        member_count=len(members),
        members=member_infos,
    )


@router.post(
    "",
    response_model=GroupOperationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create container group",
    description="Create a new container group. Requires at least 2 containers.",
)
async def create_group(
    body: GroupCreate,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> GroupOperationResponse:
    """
    Create a new container group.

    If a group with the same name exists, containers are merged into it.
    """
    service = GroupService(session)

    try:
        group, created = await service.create_group(
            name=body.name,
            container_ids=body.container_ids,
        )
    except GroupValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    group_detail = await _build_group_response(service, group.id)
    action = "created" if created else "merged into existing"

    # Sync Redis group cache so RuleMatcher/Evaluator can resolve members
    await sync_group_cache(group.id, session)

    logger.info(
        "Group %s %s by user %s with %d containers",
        group.id,
        action,
        user.user_id,
        len(body.container_ids),
    )

    # Broadcast WebSocket event for group creation
    ws_service = get_container_websocket_service()
    await ws_service.broadcast_group_created({
        "groupId": group.id,
        "name": group_detail.name,
        "containerIds": [m.container_id for m in group_detail.members] if group_detail.members else [],
        "members": [
            {"host_id": m.host_id or "local", "container_name": m.name}
            for m in group_detail.members
        ] if group_detail.members else [],
    })

    return GroupOperationResponse(
        success=True,
        message=f"Group '{body.name}' {action} successfully",
        group=group_detail,
    )


@router.get(
    "/{group_id}",
    response_model=GroupDetailResponse,
    summary="Get group details",
    description="Get detailed information about a container group.",
)
async def get_group(
    group_id: str,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> GroupDetailResponse:
    """Get group details by ID."""
    service = GroupService(session)

    try:
        return await _build_group_response(service, group_id)
    except GroupNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group {group_id} not found",
        )


@router.patch(
    "/{group_id}",
    response_model=GroupOperationResponse,
    summary="Update container group",
    description="Update group name and/or membership.",
)
async def update_group(
    group_id: str,
    body: GroupUpdate,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> GroupOperationResponse:
    """
    Update a container group.

    Can modify name, add containers, or remove containers.
    Group is auto-dissolved if fewer than 2 members remain.
    """
    service = GroupService(session)

    try:
        group = await service.update_group(
            group_id=group_id,
            name=body.name,
            add_container_ids=body.add_container_ids,
            remove_container_ids=body.remove_container_ids,
        )
    except GroupNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group {group_id} not found",
        )
    except GroupValidationError as e:
        # Group was dissolved - clear Redis cache and broadcast deletion
        await delete_group_cache(group_id)
        ws_service = get_container_websocket_service()
        await ws_service.broadcast_group_deleted(group_id)
        return GroupOperationResponse(
            success=True,
            message=str(e),
            group=None,
        )

    group_detail = await _build_group_response(service, group.id)

    # Sync Redis group cache after membership/name change
    await sync_group_cache(group.id, session)

    logger.info("Group %s updated by user %s", group_id, user.user_id)

    # Broadcast WebSocket event for group update
    ws_service = get_container_websocket_service()
    await ws_service.broadcast_group_updated({
        "groupId": group_detail.id,
        "name": group_detail.name,
        "containerIds": [m.container_id for m in group_detail.members] if group_detail.members else [],
        "members": [
            {"host_id": m.host_id or "local", "container_name": m.name}
            for m in group_detail.members
        ] if group_detail.members else [],
    })

    return GroupOperationResponse(
        success=True,
        message="Group updated successfully",
        group=group_detail,
    )


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete container group",
    description="Delete a container group. Containers are ungrouped but not deleted.",
)
async def delete_group(
    group_id: str,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a container group."""
    service = GroupService(session)

    deleted = await service.delete_group(group_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group {group_id} not found",
        )

    # Clear Redis group cache
    await delete_group_cache(group_id)

    logger.info("Group %s deleted by user %s", group_id, user.user_id)

    # Broadcast WebSocket event for group deletion
    ws_service = get_container_websocket_service()
    await ws_service.broadcast_group_deleted(group_id)


__all__ = ["router"]
