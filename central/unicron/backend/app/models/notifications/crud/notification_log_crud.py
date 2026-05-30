"""
CRUD operations for NotificationLog model.
"""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.notifications.notification_log_model import NotificationLog


async def create_log(
    session: AsyncSession,
    *,
    alert_id: str,
    channel_id: str,
    channel_type: str,
    status: str = "pending",
) -> NotificationLog:
    """Create a new notification log entry."""
    log = NotificationLog(
        alert_id=alert_id,
        channel_id=channel_id,
        channel_type=channel_type,
        status=status,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log


async def get_log(session: AsyncSession, log_id: str) -> Optional[NotificationLog]:
    """Get a notification log by ID."""
    stmt = select(NotificationLog).where(NotificationLog.id == log_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_logs_by_alert(
    session: AsyncSession,
    alert_id: str,
) -> List[NotificationLog]:
    """Get all notification logs for a specific alert."""
    stmt = select(NotificationLog).where(
        NotificationLog.alert_id == alert_id,
    ).order_by(NotificationLog.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_logs_by_status(
    session: AsyncSession,
    status: str,
    *,
    limit: int = 100,
) -> List[NotificationLog]:
    """Get notification logs by status."""
    stmt = select(NotificationLog).where(
        NotificationLog.status == status,
    ).order_by(NotificationLog.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_pending_retries(
    session: AsyncSession,
    before: datetime,
    *,
    limit: int = 100,
) -> List[NotificationLog]:
    """Get notification logs due for retry (next_retry_at <= before)."""
    stmt = select(NotificationLog).where(
        NotificationLog.status == "retrying",
        NotificationLog.next_retry_at <= before,
    ).order_by(NotificationLog.next_retry_at.asc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_log_status(
    session: AsyncSession,
    log: NotificationLog,
    *,
    status: str,
    error_message: Optional[str] = None,
    next_retry_at: Optional[datetime] = None,
    sent_at: Optional[datetime] = None,
) -> NotificationLog:
    """Update notification log status after delivery attempt."""
    log.status = status
    log.attempt_count += 1
    log.last_attempt_at = datetime.now(timezone.utc)

    if error_message is not None:
        log.error_message = error_message

    if next_retry_at is not None:
        log.next_retry_at = next_retry_at

    if sent_at is not None:
        log.sent_at = sent_at

    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log
