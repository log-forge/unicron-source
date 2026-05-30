"""
ChannelPreset model for notifier service.

This mirrors the ChannelPreset model from Central but is defined here
to keep notifier independent. Both services connect to the same
PostgreSQL database and share the notifications.channelpreset table.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import Boolean, Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class ChannelPreset(SQLModel, table=True):
    """
    Deployment-local channel template/preset.
    """

    __tablename__ = "channelpreset"
    __table_args__ = (
        Index("ix_channelpreset_channel_type", "channel_type"),
        {"schema": "notifications", "extend_existing": True},
    )

    # Primary key using uuid4 hex string (32 chars)
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String, primary_key=True, index=True),
        description="Primary key; auto-generated uuid4 hex",
    )

    # Preset configuration
    channel_type: str = Field(
        sa_column=Column(String, nullable=False),
        description="Type of channel: email, slack, teams, webhook",
    )
    label: str = Field(
        sa_column=Column(String, nullable=False),
        description="User-friendly name for this preset",
    )
    config: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
        description="Default channel configuration (sensitive data encrypted)",
    )

    # State
    enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true"),
        description="Whether the preset is available for use",
    )

    # Audit fields
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when the preset was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when the preset was last updated",
    )


__all__ = ["ChannelPreset"]
