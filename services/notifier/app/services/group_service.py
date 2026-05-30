"""Service layer for notification delivery bundle management."""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification_group_model import NotificationGroup
from app.schemas import NotificationGroupCreate, NotificationGroupUpdate


async def create_group(
    db: AsyncSession,
    data: NotificationGroupCreate,
) -> NotificationGroup:
    """Create a new notification group."""
    group = NotificationGroup(
        id=uuid4().hex,
        name=data.name,
        target_config=data.target_config.model_dump(),
        enabled=data.enabled,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return group


async def get_groups(db: AsyncSession) -> List[NotificationGroup]:
    """Get all notification groups."""
    result = await db.execute(
        select(NotificationGroup)
        .order_by(NotificationGroup.name)
    )
    return list(result.scalars().all())


async def get_group_by_id(
    db: AsyncSession,
    group_id: str,
) -> Optional[NotificationGroup]:
    """Get a notification group by ID."""
    result = await db.execute(
        select(NotificationGroup).where(NotificationGroup.id == group_id)
    )
    return result.scalar_one_or_none()


async def update_group(
    db: AsyncSession,
    group: NotificationGroup,
    data: NotificationGroupUpdate,
) -> NotificationGroup:
    """Update a notification group."""
    update_data = data.model_dump(exclude_unset=True)
    if "target_config" in update_data and update_data["target_config"] is not None:
        update_data["target_config"] = update_data["target_config"]

    for field, value in update_data.items():
        setattr(group, field, value)

    group.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(group)
    return group


async def delete_group(
    db: AsyncSession,
    group: NotificationGroup,
) -> None:
    """Delete a notification delivery bundle."""
    await db.delete(group)
    await db.commit()


__all__ = [
    "create_group",
    "get_groups",
    "get_group_by_id",
    "update_group",
    "delete_group",
]
