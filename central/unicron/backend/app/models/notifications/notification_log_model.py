"""
NotificationLog model for delivery tracking and audit.

Tracks each notification delivery attempt with status,
retry information, and error details for debugging.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from sqlmodel import Field, SQLModel


class NotificationLog(SQLModel, table=True):
    """
    Notification delivery tracking log.

    Records each notification delivery attempt with status, retry count,
    and error information for debugging and audit purposes.
    """

    __tablename__ = "notificationlog"
    __table_args__ = (
        Index("ix_notificationlog_alert_id", "alert_id"),
        Index("ix_notificationlog_status", "status"),
        Index("ix_notificationlog_channel_id", "channel_id"),
        Index("ix_notificationlog_next_retry_at", "next_retry_at"),
        {"schema": "notifications"},
    )

    # Primary key using uuid4 hex string (32 chars)
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String, primary_key=True, index=True),
        description="Primary key; auto-generated uuid4 hex",
    )

    # Source reference
    alert_id: str = Field(
        sa_column=Column(String, nullable=False),
        description="Source alert ID that triggered this notification",
    )

    # Target channel
    channel_id: str = Field(
        sa_column=Column(String, nullable=False),
        description="Target notification channel ID",
    )
    channel_type: str = Field(
        sa_column=Column(String, nullable=False),
        description="Denormalized channel type for efficient filtering",
    )

    # Delivery status
    status: str = Field(
        default="pending",
        sa_column=Column(String, nullable=False, server_default="'pending'"),
        description="Delivery status: pending, sent, failed, retrying",
    )

    # Retry tracking
    attempt_count: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
        description="Number of delivery attempts",
    )
    last_attempt_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Timestamp of last delivery attempt",
    )
    next_retry_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Scheduled time for next retry (for retry worker queries)",
    )

    # Error tracking
    error_message: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="Last error message if delivery failed",
    )

    # Success tracking
    sent_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Timestamp when notification was successfully sent",
    )

    # Audit fields
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when the log entry was created",
    )


__all__ = ["NotificationLog"]
