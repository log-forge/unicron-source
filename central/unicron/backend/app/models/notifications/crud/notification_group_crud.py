"""CRUD operations for NotificationGroup models."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.notifications.notification_group_model import NotificationGroup


async def create_group(
    session: AsyncSession,
    *,
    name: str,
    target_config: Optional[Dict[str, Any]] = None,
    enabled: bool = True,
) -> NotificationGroup:
    """Create a new notification delivery bundle."""
    group = NotificationGroup(
        name=name,
        target_config=target_config or {},
        enabled=enabled,
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def get_group(
    session: AsyncSession, group_id: str
) -> Optional[NotificationGroup]:
    """Get a notification group by ID."""
    stmt = select(NotificationGroup).where(NotificationGroup.id == group_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_groups(
    session: AsyncSession,
    *,
    enabled_only: bool = False,
) -> List[NotificationGroup]:
    """Get all notification groups."""
    stmt = select(NotificationGroup)

    if enabled_only:
        stmt = stmt.where(NotificationGroup.enabled == True)

    stmt = stmt.order_by(NotificationGroup.name.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_group(
    session: AsyncSession,
    group: NotificationGroup,
    *,
    name: Optional[str] = None,
    target_config: Optional[Dict[str, Any]] = None,
    enabled: Optional[bool] = None,
) -> NotificationGroup:
    """Update a notification group."""
    if name is not None:
        group.name = name
    if target_config is not None:
        group.target_config = target_config
    if enabled is not None:
        group.enabled = enabled

    group.updated_at = datetime.now(timezone.utc)

    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def delete_group(session: AsyncSession, group: NotificationGroup) -> bool:
    """Delete a notification group."""
    await session.delete(group)
    await session.commit()
    return True
