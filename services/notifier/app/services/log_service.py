"""Notification log service for tracking delivery status."""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification_log_model import NotificationLog


async def create_log(
    db: AsyncSession,
    alert_id: str,
    channel_id: str,
    channel_type: str,
    status: str = "pending",
) -> NotificationLog:
    """
    Create a new notification log entry.

    Args:
        db: Database session
        alert_id: ID of the alert triggering this notification
        channel_id: ID of the channel to send to
        channel_type: Channel type for efficient filtering
        status: Initial status (default: pending)

    Returns:
        Created NotificationLog instance
    """
    log = NotificationLog(
        id=uuid4().hex,
        alert_id=alert_id,
        channel_id=channel_id,
        channel_type=channel_type,
        status=status,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


async def update_log_status(
    db: AsyncSession,
    log: NotificationLog,
    status: str,
    error_message: Optional[str] = None,
    next_retry_at: Optional[datetime] = None,
) -> NotificationLog:
    """
    Update notification log status after delivery attempt.

    Args:
        db: Database session
        log: NotificationLog to update
        status: New status (sent, failed, retrying)
        error_message: Error message if failed
        next_retry_at: Timestamp for next retry if retrying

    Returns:
        Updated NotificationLog instance
    """
    log.status = status
    log.attempt_count += 1
    log.last_attempt_at = datetime.now(timezone.utc)

    if status == "sent":
        log.sent_at = log.last_attempt_at

    if error_message:
        log.error_message = error_message

    if next_retry_at:
        log.next_retry_at = next_retry_at

    await db.commit()
    await db.refresh(log)
    return log


async def get_pending_retries(
    db: AsyncSession,
    before: datetime,
) -> List[NotificationLog]:
    """
    Get notification logs that are due for retry.

    Args:
        db: Database session
        before: Fetch logs with next_retry_at before this timestamp

    Returns:
        List of NotificationLog entries ready for retry
    """
    result = await db.execute(
        select(NotificationLog).where(
            and_(
                NotificationLog.status == "retrying",
                NotificationLog.next_retry_at <= before,
            )
        )
    )
    return list(result.scalars().all())


async def get_logs_by_alert(
    db: AsyncSession,
    alert_id: str,
) -> List[NotificationLog]:
    """
    Get all notification logs for a given alert.

    Args:
        db: Database session
        alert_id: Alert ID to filter by

    Returns:
        List of NotificationLog entries for the alert
    """
    result = await db.execute(
        select(NotificationLog).where(NotificationLog.alert_id == alert_id)
    )
    return list(result.scalars().all())


__all__ = [
    "create_log",
    "update_log_status",
    "get_pending_retries",
    "get_logs_by_alert",
]
