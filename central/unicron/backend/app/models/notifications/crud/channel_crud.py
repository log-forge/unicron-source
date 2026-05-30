"""CRUD operations for NotificationChannel model."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.notifications.channel_model import NotificationChannel


async def create_channel(
    session: AsyncSession,
    *,
    channel_type: str,
    label: str,
    config: Dict[str, Any],
    enabled: bool = True,
    verified: bool = False,
) -> NotificationChannel:
    """Create a new notification channel."""
    channel = NotificationChannel(
        channel_type=channel_type,
        label=label,
        config=config,
        enabled=enabled,
        verified=verified,
    )
    session.add(channel)
    await session.commit()
    await session.refresh(channel)
    return channel


async def get_channel(
    session: AsyncSession, channel_id: str
) -> Optional[NotificationChannel]:
    """Get a notification channel by ID."""
    stmt = select(NotificationChannel).where(NotificationChannel.id == channel_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_channels(
    session: AsyncSession,
    *,
    enabled_only: bool = False,
    channel_type: Optional[str] = None,
) -> List[NotificationChannel]:
    """Get all notification channels."""
    stmt = select(NotificationChannel)

    if enabled_only:
        stmt = stmt.where(NotificationChannel.enabled == True)

    if channel_type:
        stmt = stmt.where(NotificationChannel.channel_type == channel_type)

    stmt = stmt.order_by(NotificationChannel.label.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_channel(
    session: AsyncSession,
    channel: NotificationChannel,
    *,
    label: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    enabled: Optional[bool] = None,
) -> NotificationChannel:
    """Update a notification channel."""
    if label is not None:
        channel.label = label
    if config is not None:
        channel.config = config
    if enabled is not None:
        channel.enabled = enabled

    channel.updated_at = datetime.now(timezone.utc)

    session.add(channel)
    await session.commit()
    await session.refresh(channel)
    return channel


async def verify_channel(
    session: AsyncSession, channel: NotificationChannel
) -> NotificationChannel:
    """Mark a channel as verified."""
    channel.verified = True
    channel.updated_at = datetime.now(timezone.utc)

    session.add(channel)
    await session.commit()
    await session.refresh(channel)
    return channel


async def delete_channel(session: AsyncSession, channel: NotificationChannel) -> bool:
    """Delete a notification channel."""
    await session.delete(channel)
    await session.commit()
    return True
