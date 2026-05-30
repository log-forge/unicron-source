"""
NotificationLog model for tracking notification delivery status.

This model records all notification delivery attempts, including
retries and final status.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from sqlmodel import Field, SQLModel


class NotificationLog(SQLModel, table=True):
    """
    Tracks notification delivery attempts and status.

    Each notification sent to a channel creates a log entry.
    Failed notifications may be retried, with attempt_count
    and next_retry_at tracking retry state.
    """

    __tablename__ = "notificationlog"
    __table_args__ = (
        Index("ix_notificationlog_alert_id", "alert_id"),
        Index("ix_notificationlog_status", "status"),
        Index("ix_notificationlog_channel_id", "channel_id"),
        Index("ix_notificationlog_next_retry", "next_retry_at"),
        {"schema": "notifications", "extend_existing": True},
    )

    # Primary key using uuid4 hex string (32 chars)
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String(32), primary_key=True),
        description="Primary key; auto-generated uuid4 hex",
    )

    # Alert reference
    alert_id: str = Field(
        sa_column=Column(String(32), nullable=False),
        description="ID of the alert that triggered this notification",
    )

    # Channel reference
    channel_id: str = Field(
        sa_column=Column(String, nullable=False),
        description="ID of the channel this notification was sent to",
    )
    channel_type: str = Field(
        sa_column=Column(String, nullable=False),
        description="Denormalized channel type for efficient filtering",
    )

    # Delivery status: pending, sent, failed, retrying
    status: str = Field(
        default="pending",
        sa_column=Column(String(20), nullable=False, server_default="pending"),
        description="Delivery status: pending, sent, failed, retrying",
    )

    # Retry tracking
    attempt_count: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
        description="Number of delivery attempts made",
    )
    last_attempt_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Timestamp of the last delivery attempt",
    )
    next_retry_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Timestamp for next retry attempt",
    )

    # Error tracking
    error_message: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="Error message from last failed attempt",
    )

    # Success timestamp
    sent_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Timestamp when notification was successfully sent",
    )

    # Audit
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when log entry was created",
    )


__all__ = ["NotificationLog"]
