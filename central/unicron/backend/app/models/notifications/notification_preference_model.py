"""
NotificationPreference model for global delivery preferences.
"""
from datetime import datetime, time, timezone
from typing import List, Optional

from sqlalchemy import Column, DateTime, String, Time
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class NotificationPreference(SQLModel, table=True):
    """Singleton deployment-local notification preferences."""

    __tablename__ = "notificationpreference"
    __table_args__ = {"schema": "notifications"}

    id: str = Field(
        default="global",
        sa_column=Column(String, primary_key=True, index=True),
        description="Singleton preference row ID",
    )

    quiet_hours_start: Optional[time] = Field(
        default=None,
        sa_column=Column(Time, nullable=True),
        description="Start time of quiet period",
    )
    quiet_hours_end: Optional[time] = Field(
        default=None,
        sa_column=Column(Time, nullable=True),
        description="End time of quiet period",
    )
    quiet_hours_timezone: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="Timezone for quiet hours",
    )

    min_severity: str = Field(
        default="info",
        sa_column=Column(String, nullable=False, server_default="info"),
        description="Minimum severity to notify: critical, warning, info",
    )

    preferred_channels: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
        description="Ordered list of preferred channel types",
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when the preferences were created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when the preferences were last updated",
    )


__all__ = ["NotificationPreference"]
