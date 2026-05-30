"""
AlertRule model for defining alert conditions and triggers.

Supports multiple trigger types (threshold, keyword, rate, absence) and
scoping to global, container, group, or herald level.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class AlertRule(SQLModel, table=True):
    """
    Alert rule definition with trigger configuration and scope targeting.

    Rules define conditions that trigger alerts when matched against
    incoming log data or metrics from monitored containers.
    """

    __tablename__ = "alertrule"
    __table_args__ = (
        Index("ix_alertrule_organization_id", "organization_id"),
        Index("ix_alertrule_enabled_organization_id", "enabled", "organization_id"),
        Index("ix_alertrule_scope_type_organization_id", "scope_type", "organization_id"),
        {"schema": "alerting"},
    )

    # Primary key using uuid4 hex string (32 chars)
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String, primary_key=True, index=True),
        description="Primary key; auto-generated uuid4 hex",
    )

    # Rule identification
    name: str = Field(
        sa_column=Column(String, nullable=False),
        description="Human-readable rule name",
    )
    description: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="Optional detailed description of the rule",
    )

    # Trigger configuration
    trigger_type: str = Field(
        sa_column=Column(String, nullable=False),
        description="Type of trigger: threshold, keyword, rate, absence",
    )
    trigger_config: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
        description="Trigger-specific parameters (thresholds, patterns, intervals)",
    )

    # Scope configuration
    scope_type: str = Field(
        default="global",
        sa_column=Column(String, nullable=False, server_default="'global'"),
        description="Scope type: global, container, group, herald",
    )
    scope_targets: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
        description="Target IDs for the scope (container IDs, group IDs, herald IDs)",
    )

    # Alert properties
    severity: str = Field(
        default="warning",
        sa_column=Column(String, nullable=False, server_default="'warning'"),
        description="Alert severity: critical, warning, info",
    )
    labels: Dict[str, str] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
        description="Additional labels for alert routing and filtering",
    )
    annotations: Dict[str, str] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
        description="Additional annotations for alert display",
    )

    # State
    enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true"),
        description="Whether the rule is active",
    )

    # Multi-tenancy
    organization_id: str = Field(
        sa_column=Column(String, nullable=False, index=True),
        description="Organization ID for multi-tenant isolation",
    )

    # Audit fields
    created_by: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="User ID who created the rule",
    )
    updated_by: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="User ID who last updated the rule",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when the rule was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when the rule was last updated",
    )


__all__ = ["AlertRule"]
