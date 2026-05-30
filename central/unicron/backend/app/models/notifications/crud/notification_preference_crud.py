"""CRUD operations for NotificationPreference model."""
from datetime import datetime, time, timezone
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.notifications.notification_preference_model import NotificationPreference

GLOBAL_PREFERENCE_ID = "global"


async def create_preference(
    session: AsyncSession,
    *,
    quiet_hours_start: Optional[time] = None,
    quiet_hours_end: Optional[time] = None,
    quiet_hours_timezone: Optional[str] = None,
    min_severity: str = "info",
    preferred_channels: Optional[List[str]] = None,
) -> NotificationPreference:
    """Create global notification preferences."""
    preference = NotificationPreference(
        id=GLOBAL_PREFERENCE_ID,
        quiet_hours_start=quiet_hours_start,
        quiet_hours_end=quiet_hours_end,
        quiet_hours_timezone=quiet_hours_timezone,
        min_severity=min_severity,
        preferred_channels=preferred_channels or [],
    )
    session.add(preference)
    await session.commit()
    await session.refresh(preference)
    return preference


async def get_preference(
    session: AsyncSession,
) -> Optional[NotificationPreference]:
    """Get global notification preferences."""
    stmt = select(NotificationPreference).where(
        NotificationPreference.id == GLOBAL_PREFERENCE_ID
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_preference(
    session: AsyncSession,
    preference: NotificationPreference,
    *,
    quiet_hours_start: Optional[time] = None,
    quiet_hours_end: Optional[time] = None,
    quiet_hours_timezone: Optional[str] = None,
    min_severity: Optional[str] = None,
    preferred_channels: Optional[List[str]] = None,
) -> NotificationPreference:
    """Update global notification preferences."""
    if quiet_hours_start is not None:
        preference.quiet_hours_start = quiet_hours_start
    if quiet_hours_end is not None:
        preference.quiet_hours_end = quiet_hours_end
    if quiet_hours_timezone is not None:
        preference.quiet_hours_timezone = quiet_hours_timezone
    if min_severity is not None:
        preference.min_severity = min_severity
    if preferred_channels is not None:
        preference.preferred_channels = preferred_channels

    preference.updated_at = datetime.now(timezone.utc)

    session.add(preference)
    await session.commit()
    await session.refresh(preference)
    return preference


async def delete_preference(
    session: AsyncSession, preference: NotificationPreference
) -> bool:
    """Delete global notification preferences."""
    await session.delete(preference)
    await session.commit()
    return True
