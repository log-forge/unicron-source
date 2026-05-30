"""
AlertHistory model for persisting triggered alert instances.

Designed for time-based partitioning by triggered_at timestamp to support
efficient storage and query performance at scale (5000+ containers).
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class AlertHistory(SQLModel, table=True):
    """
    Historical record of triggered alerts.

    Each row represents a single alert occurrence with denormalized rule
    information for query efficiency. The table is partitioned by triggered_at
    for efficient time-range queries and data retention management.
    """

    __tablename__ = "alerthistory"
    __table_args__ = (
        Index("ix_alerthistory_rule_id", "rule_id"),
        Index("ix_alerthistory_organization_id", "organization_id"),
        Index("ix_alerthistory_status", "status"),
        Index("ix_alerthistory_severity", "severity"),
        Index("ix_alerthistory_triggered_at", "triggered_at"),
        Index(
            "ix_alerthistory_org_triggered_at",
            "organization_id",
            "triggered_at",
        ),
        {
            "schema": "alerting",
            "postgresql_partition_by": "RANGE (triggered_at)",
        },
    )

    # Primary key using uuid4 hex string (32 chars)
    # Note: For partitioned tables, PK must include partition key
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String, nullable=False),
        description="Primary key; auto-generated uuid4 hex",
    )

    # Alert reference (denormalized for history queries without joins)
    rule_id: str = Field(
        sa_column=Column(String, nullable=False),
        description="Reference to the alert rule that triggered",
    )
    rule_name: str = Field(
        sa_column=Column(String, nullable=False),
        description="Denormalized rule name at time of trigger",
    )

    # Alert details
    severity: str = Field(
        sa_column=Column(String, nullable=False),
        description="Alert severity: critical, warning, info",
    )
    message: str = Field(
        sa_column=Column(Text, nullable=False),
        description="Alert message with template variables expanded",
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
        description="Alert context: container ID, labels, metric values, log excerpts",
    )

    # State transitions
    status: str = Field(
        default="triggered",
        sa_column=Column(String, nullable=False, server_default="'triggered'"),
        description="Alert status: triggered, acknowledged",
    )

    # Timestamps (triggered_at is partition key)
    triggered_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, primary_key=True),
        description="Timestamp when the alert was triggered (partition key)",
    )
    acknowledged_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Timestamp when the alert was acknowledged",
    )
    acknowledged_by: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="User ID who acknowledged the alert",
    )

    # Multi-tenancy
    organization_id: str = Field(
        sa_column=Column(String, nullable=False),
        description="Organization ID for multi-tenant isolation",
    )


__all__ = ["AlertHistory"]
