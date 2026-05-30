"""
NotificationChannel model for deployment-local delivery channels.

Supports multiple channel types (email, slack, teams, webhook) with
flexible JSONB configuration for channel-specific settings.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import Boolean, Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class NotificationChannel(SQLModel, table=True):
    """
    Deployment-local notification delivery channel.
    """

    __tablename__ = "notificationchannel"
    __table_args__ = (
        Index("ix_notificationchannel_channel_type", "channel_type"),
        {"schema": "notifications"},
    )

    # Primary key using uuid4 hex string (32 chars)
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String, primary_key=True, index=True),
        description="Primary key; auto-generated uuid4 hex",
    )

    # Channel configuration
    channel_type: str = Field(
        sa_column=Column(String, nullable=False),
        description="Type of channel: email, slack, teams, webhook",
    )
    label: str = Field(
        sa_column=Column(String, nullable=False),
        description="User-friendly name for this channel",
    )
    config: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
        description="Channel-specific configuration (sensitive data encrypted)",
    )

    # State
    enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true"),
        description="Whether the channel is active",
    )
    verified: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
        description="Whether the channel has been verified (email confirmation, etc.)",
    )

    # Audit fields
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when the channel was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when the channel was last updated",
    )


__all__ = ["NotificationChannel"]
