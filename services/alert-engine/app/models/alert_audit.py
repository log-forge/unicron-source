"""Audit log model for alert operations."""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from sqlalchemy import Column, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class AlertOperation(str, Enum):
    """Types of alert operations."""

    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SILENCE_CREATED = "silence_created"
    SILENCE_UPDATED = "silence_updated"
    SILENCE_DELETED = "silence_deleted"
    SILENCE_EXPIRED = "silence_expired"


class AlertOperationLog(SQLModel, table=True):
    """
    Audit log for alert operations.

    Tracks acknowledge, resolve, and silence operations with user context
    and timestamps for compliance.
    """

    __tablename__ = "alertoperationlog"
    __table_args__ = (
        Index("ix_alertoperationlog_alert_id", "alert_id"),
        Index("ix_alertoperationlog_silence_id", "silence_id"),
        Index("ix_alertoperationlog_user_id", "user_id"),
        Index("ix_alertoperationlog_organization_id", "organization_id"),
        Index("ix_alertoperationlog_operation", "operation"),
        Index("ix_alertoperationlog_timestamp", "timestamp"),
        {"schema": "alerting", "extend_existing": True},
    )

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String(32), primary_key=True),
    )

    # What was affected (one of these will be set)
    alert_id: Optional[str] = Field(
        default=None, sa_column=Column(String(32), nullable=True)
    )
    alert_fingerprint: Optional[str] = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    silence_id: Optional[str] = Field(
        default=None, sa_column=Column(String(32), nullable=True)
    )

    # Context
    rule_id: Optional[str] = Field(
        default=None, sa_column=Column(String(32), nullable=True)
    )
    rule_name: Optional[str] = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )
    container_id: Optional[str] = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )

    # Who did it
    user_id: str = Field(sa_column=Column(String(255), nullable=False))
    user_email: Optional[str] = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )
    organization_id: str = Field(sa_column=Column(String(255), nullable=False))

    # What operation
    operation: str = Field(sa_column=Column(String(30), nullable=False))

    # When
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        sa_column=Column(String(50), nullable=False),
    )

    # Details - stores operation-specific data
    details: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )


__all__ = ["AlertOperation", "AlertOperationLog"]
