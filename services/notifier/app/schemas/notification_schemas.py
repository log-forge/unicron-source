"""Pydantic schemas for notification dispatch and logging."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class NotificationStatus(str, Enum):
    """Status of a notification delivery."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    RETRYING = "retrying"


class NotificationDispatch(BaseModel):
    """Schema for dispatching a notification."""

    alert_id: str = Field(..., description="Source alert ID that triggered the notification")
    title: str = Field(..., min_length=1, max_length=500, description="Notification title")
    message: str = Field(..., min_length=1, description="Notification message body")
    severity: str = Field(
        default="warning", description="Alert severity (critical, warning, info)"
    )
    context: Dict[str, Any] = Field(
        default_factory=dict, description="Additional context data"
    )
    channel_ids: Optional[List[str]] = Field(
        default=None, description="Specific channel IDs to send to"
    )
    group_ids: Optional[List[str]] = Field(
        default=None, description="Notification group IDs to send to"
    )
    preset_ids: Optional[List[str]] = Field(
        default=None, description="Notification preset IDs to send to"
    )

    model_config = {"extra": "forbid"}


class NotificationLogResponse(BaseModel):
    """Schema for notification log entry in API responses."""

    id: str
    alert_id: str
    channel_id: str
    status: NotificationStatus
    attempt_count: int
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationLogQuery(BaseModel):
    """Schema for querying notification logs."""

    alert_id: Optional[str] = Field(
        default=None, description="Filter by alert ID"
    )
    channel_id: Optional[str] = Field(
        default=None, description="Filter by channel ID"
    )
    status: Optional[NotificationStatus] = Field(
        default=None, description="Filter by status"
    )
    limit: int = Field(
        default=50, ge=1, le=1000, description="Maximum number of results"
    )
    offset: int = Field(
        default=0, ge=0, description="Number of results to skip"
    )

    model_config = {"extra": "forbid"}


class NotificationLogListResponse(BaseModel):
    """Paginated list of notification logs."""

    items: List[NotificationLogResponse]
    total: int


__all__ = [
    "NotificationStatus",
    "NotificationDispatch",
    "NotificationLogResponse",
    "NotificationLogQuery",
    "NotificationLogListResponse",
]
