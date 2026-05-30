"""
AlertState model for tracking currently active alerts.

Provides deduplication via fingerprint-based uniqueness and supports
integration with Redis for real-time state management.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import Column, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class AlertState(SQLModel, table=True):
    """
    Active alert state tracking with deduplication support.

    Each unique alert (identified by fingerprint) has at most one active state
    record. The fingerprint is a hash of rule_id + scope + labels, enabling
    deduplication across multiple trigger events for the same condition.
    """

    __tablename__ = "alertstate"
    __table_args__ = (
        Index("ix_alertstate_fingerprint", "fingerprint", unique=True),
        Index("ix_alertstate_rule_id", "rule_id"),
        Index("ix_alertstate_status_organization_id", "status", "organization_id"),
        Index("ix_alertstate_organization_id", "organization_id"),
        Index("ix_alertstate_org_updated", "organization_id", "updated_at"),
        Index("ix_alertstate_org_status_updated", "organization_id", "status", "updated_at"),
        Index("ix_alertstate_stacking_key", "stacking_key"),
        {"schema": "alerting"},
    )

    # Primary key using uuid4 hex string (32 chars)
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String, primary_key=True, index=True),
        description="Primary key; auto-generated uuid4 hex",
    )

    # Rule reference
    rule_id: str = Field(
        sa_column=Column(String, nullable=False),
        description="Reference to the alert rule",
    )

    # Deduplication key
    fingerprint: str = Field(
        sa_column=Column(String, nullable=False),
        description="Unique deduplication key: hash of rule_id + scope + labels",
    )

    # Alert state
    status: str = Field(
        default="firing",
        sa_column=Column(String, nullable=False, server_default="'firing'"),
        description="Current status: firing, pending, acknowledged",
    )
    severity: str = Field(
        sa_column=Column(String, nullable=False),
        description="Current alert severity: critical, warning, info",
    )

    # Alert metadata
    labels: Dict[str, str] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
        description="Alert labels for matching and routing",
    )
    annotations: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
        description="Alert annotations for display and notification",
    )
    value: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="Current value that triggered the alert",
    )

    # Timing
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when alert started firing",
    )
    ends_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Expected end time (for time-bounded alerts)",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp of last state update",
    )

    # Stacking metadata
    count: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=True, server_default="1"),
        description="Number of trigger events folded into this alert state",
    )
    first_seen: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Timestamp when the stacked alert first appeared",
    )
    last_seen: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Timestamp when the stacked alert was most recently observed",
    )
    stacking_key: Optional[str] = Field(
        default="",
        sa_column=Column(String, nullable=True, server_default=""),
        description="Stable key used to fold repeated trigger events",
    )
    last_trigger_context: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
        description="Context from the most recent trigger event",
    )

    # Multi-tenancy
    organization_id: str = Field(
        sa_column=Column(String, nullable=False),
        description="Organization ID for multi-tenant isolation",
    )


__all__ = ["AlertState"]
