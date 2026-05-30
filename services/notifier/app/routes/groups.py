"""Notification group API endpoints.

Groups are deployment-local delivery bundles. They contain direct channel and
preset targets, not users or members.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import UserContext, get_current_user
from app.schemas import (
    GroupTargets,
    NotificationGroupCreate,
    NotificationGroupListResponse,
    NotificationGroupResponse,
    NotificationGroupUpdate,
)
from app.services import group_service

router = APIRouter()


def _group_to_response(group) -> NotificationGroupResponse:
    """Map group model to response schema."""
    return NotificationGroupResponse(
        id=group.id,
        name=group.name,
        target_config=GroupTargets.model_validate(group.target_config or {}),
        enabled=group.enabled,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


@router.post(
    "/groups",
    response_model=NotificationGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_group(
    data: NotificationGroupCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
) -> NotificationGroupResponse:
    """Create a new notification delivery bundle."""
    group = await group_service.create_group(db, data)
    return _group_to_response(group)


@router.get("/groups", response_model=NotificationGroupListResponse)
async def list_groups(
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
) -> NotificationGroupListResponse:
    """List all notification delivery bundles."""
    groups = await group_service.get_groups(db)
    items = [_group_to_response(group) for group in groups]
    return NotificationGroupListResponse(items=items, total=len(items))


@router.get("/groups/{group_id}", response_model=NotificationGroupResponse)
async def get_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
) -> NotificationGroupResponse:
    """Get a notification group by ID."""
    group = await group_service.get_group_by_id(db, group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group {group_id} not found",
        )
    return _group_to_response(group)


@router.patch("/groups/{group_id}", response_model=NotificationGroupResponse)
async def update_group(
    group_id: str,
    data: NotificationGroupUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
) -> NotificationGroupResponse:
    """Update a notification delivery bundle."""
    group = await group_service.get_group_by_id(db, group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group {group_id} not found",
        )

    group = await group_service.update_group(db, group, data)
    return _group_to_response(group)


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
) -> None:
    """Delete a notification delivery bundle."""
    group = await group_service.get_group_by_id(db, group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group {group_id} not found",
        )

    await group_service.delete_group(db, group)


__all__ = ["router"]
