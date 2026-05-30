"""
Silence model for maintenance windows and alert suppression.

Supports both one-time and recurring silences with label matchers
for flexible alert filtering during planned maintenance.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class Silence(SQLModel, table=True):
    """
    Alert silence configuration for maintenance windows.

    Silences suppress alert notifications (but not alert generation) based on
    label matchers during a specified time window. Supports recurring silences
    using RRULE format for scheduled maintenance windows.
    """

    __tablename__ = "silence"
    __table_args__ = (
        Index("ix_silence_organization_id", "organization_id"),
        Index("ix_silence_starts_at", "starts_at"),
        Index("ix_silence_ends_at", "ends_at"),
        Index(
            "ix_silence_active_window",
            "organization_id",
            "starts_at",
            "ends_at",
        ),
        {"schema": "alerting"},
    )

    # Primary key using uuid4 hex string (32 chars)
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String, primary_key=True, index=True),
        description="Primary key; auto-generated uuid4 hex",
    )

    # Matchers define which alerts are silenced
    matchers: List[Dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
        description="Label matchers: [{name, value, isRegex, isEqual}]",
    )

    # Time window
    starts_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Silence start time",
    )
    ends_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Silence end time",
    )

    # Audit fields
    created_by: str = Field(
        sa_column=Column(String, nullable=False),
        description="User ID who created the silence",
    )
    comment: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="Reason or context for the silence",
    )

    # Recurrence support
    recurring: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
        description="Whether this silence recurs",
    )
    recurrence_rule: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="RRULE string for recurring silences (RFC 5545)",
    )

    # State
    expired: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
        description="Whether the silence has been manually expired",
    )

    # Multi-tenancy
    organization_id: str = Field(
        sa_column=Column(String, nullable=False),
        description="Organization ID for multi-tenant isolation",
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when the silence was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when the silence was last updated",
    )


__all__ = ["Silence"]
