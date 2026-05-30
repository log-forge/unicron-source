"""Dispatch API endpoint for triggering notifications."""

import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import UserContext, get_current_user
from app.services import dispatch_service, ChannelService, ChannelNotFoundError
from app.services.delivery_service import delivery_service
from app.services import log_service

router = APIRouter()


class DispatchRequest(BaseModel):
    """Request to dispatch a notification."""

    alert_id: str
    title: str
    message: str
    severity: str = "info"
    context: dict = {}
    channel_ids: Optional[List[str]] = None
    group_ids: Optional[List[str]] = None
    preset_ids: Optional[List[str]] = None


class TaskInfo(BaseModel):
    """Information about a queued task."""

    channel_id: str
    task_id: str


class DispatchResponse(BaseModel):
    """Response from dispatch endpoint."""

    alert_id: str
    channels_targeted: int
    tasks_queued: List[TaskInfo]


class TestNotificationResponse(BaseModel):
    """Response from test notification endpoint."""

    status: str  # "success" or "failed"
    message: str
    channel_type: Optional[str] = None


@router.post("/dispatch", response_model=DispatchResponse)
async def dispatch_notification(
    data: DispatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    """
    Dispatch notification to channels or groups.

    Queues notifications for explicitly supplied channels, groups, and presets.
    """
    alert_data = {
        "title": data.title,
        "message": data.message,
        "severity": data.severity,
        "alert_id": data.alert_id,
        "context": data.context,
    }

    result = await dispatch_service.dispatch_alert(
        db,
        data.alert_id,
        alert_data,
        channel_ids=data.channel_ids,
        group_ids=data.group_ids,
        preset_ids=data.preset_ids,
    )

    return result


@router.post("/channels/{channel_id}/test", response_model=TestNotificationResponse)
async def test_channel(
    channel_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
) -> TestNotificationResponse:
    """Send a test notification to a specific channel."""
    service = ChannelService(db)
    try:
        channel = await service.get_channel_or_raise(channel_id)
    except ChannelNotFoundError:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id} not found")

    alert_id = f"test_{channel_id}_{int(time.time())}"
    success = await delivery_service.deliver(
        db, channel, alert_id,
        title="Test Notification",
        body="Test notification from LogForge - this confirms your channel is configured correctly.",
    )
    if success:
        return TestNotificationResponse(
            status="success",
            message=f"Test notification sent successfully via {channel.channel_type}",
            channel_type=channel.channel_type,
        )

    # Query the delivery log for error details
    logs = await log_service.get_logs_by_alert(db, alert_id)
    error_detail = "Delivery failed - check channel configuration"
    if logs and logs[0].error_message:
        error_detail = f"Delivery failed: {logs[0].error_message}"
    return TestNotificationResponse(
        status="failed",
        message=error_detail,
        channel_type=channel.channel_type,
    )
