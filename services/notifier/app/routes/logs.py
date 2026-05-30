"""Notification delivery logs API endpoint."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import UserContext, get_current_user
from app.models.notification_log_model import NotificationLog

router = APIRouter(prefix="/logs", tags=["logs"])

# Map delivery status to log levels the frontend expects
_STATUS_TO_LEVEL = {
    "sent": "INFO",
    "failed": "ERROR",
    "pending": "WARNING",
    "retrying": "WARNING",
}


def _format_log_entry(log: NotificationLog) -> dict:
    """Map a NotificationLog row to the frontend LogEntry shape.

    Frontend expects: { id, timestamp, level, message, channel_type?,
    channel_id?, status?, error? }
    """
    level = _STATUS_TO_LEVEL.get(log.status, "INFO")
    message = f"[{log.status.upper()}] Alert {log.alert_id} -> Channel {log.channel_id}"
    if log.error_message:
        message += f" | {log.error_message}"

    return {
        "id": log.id,
        "timestamp": log.created_at.isoformat() if log.created_at else "",
        "level": level,
        "message": message,
        "channel_type": log.channel_type,
        "channel_id": log.channel_id,
        "status": log.status,
        "error": log.error_message,
    }


@router.get("")
async def get_logs(
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
    status: Optional[str] = Query(None, description="Filter by delivery status"),
    channel_id: Optional[str] = Query(None, description="Filter by channel ID"),
    alert_id: Optional[str] = Query(None, description="Filter by alert ID"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """
    List notification delivery logs for this deployment.

    Returns logs in the shape the frontend Logs.tsx component expects:
    ``{ logs: [{ id, timestamp, level, message, ... }] }``
    """
    query = select(NotificationLog).order_by(NotificationLog.created_at.desc())

    # Apply optional filters
    if status is not None:
        query = query.where(NotificationLog.status == status)
    if channel_id is not None:
        query = query.where(NotificationLog.channel_id == channel_id)
    if alert_id is not None:
        query = query.where(NotificationLog.alert_id == alert_id)

    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    logs = list(result.scalars().all())

    return {"logs": [_format_log_entry(log) for log in logs]}
