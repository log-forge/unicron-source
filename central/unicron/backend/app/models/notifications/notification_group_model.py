"""
NotificationGroup model for delivery bundle notification routing.

Groups route alerts to named bundles of direct channels and presets.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class NotificationGroup(SQLModel, table=True):
    """
    Named deployment-local notification delivery bundle.
    """

    __tablename__ = "notificationgroup"
    __table_args__ = {"schema": "notifications"}

    # Primary key using uuid4 hex string (32 chars)
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String, primary_key=True, index=True),
        description="Primary key; auto-generated uuid4 hex",
    )

    # Group identification
    name: str = Field(
        sa_column=Column(String, nullable=False),
        description="Human-readable group name",
    )
    # Target configuration
    target_config: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
        description="Direct channel IDs and preset IDs for this delivery bundle",
    )

    # State
    enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true"),
        description="Whether the group is active",
    )

    # Audit fields
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when the group was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when the group was last updated",
    )


__all__ = ["NotificationGroup"]
