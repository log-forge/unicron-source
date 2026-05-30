"""
RuleAction and ActionAuditLog models for alert-engine service.

These models support remediation action configuration and audit logging
for the action gatekeeper system.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class ActionType(str, Enum):
    """Supported remediation action types."""

    restart = "restart"
    stop = "stop"
    start = "start"
    kill = "kill"
    run_script = "run_script"
    notify = "notify"


class RuleAction(SQLModel, table=True):
    """
    Action configuration for an alert rule.

    Each alert rule can have multiple actions that execute in order when
    the rule fires. Actions are gated by the ActionGatekeeper for safety.
    """

    __tablename__ = "ruleaction"
    __table_args__ = (
        Index("ix_ruleaction_rule_id", "rule_id"),
        Index("ix_ruleaction_enabled", "enabled"),
        {"schema": "alerting", "extend_existing": True},
    )

    # Primary key using uuid4 hex string (32 chars)
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String, primary_key=True),
        description="Primary key; auto-generated uuid4 hex",
    )

    # Rule reference (foreign key to alert_rules)
    rule_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("alerting.alertrule.id", ondelete="CASCADE"),
            nullable=False,
        ),
        description="Reference to the alert rule",
    )

    # Action type and configuration
    action_type: str = Field(
        sa_column=Column(String, nullable=False),
        description="Action type: restart, stop, start, kill, run_script, notify",
    )
    action_config: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
        description="Type-specific action configuration",
    )

    # Execution ordering for multi-action rules
    order_index: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
        description="Execution order for multi-action rules (lower = first)",
    )

    # State
    enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true"),
        description="Whether this action is enabled",
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="When the action was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="When the action was last updated",
    )


class ActionAuditLog(SQLModel, table=True):
    """
    Audit log for action execution.

    Records every action attempt with outcome (allowed/blocked/success/failed)
    and relevant metadata for debugging and compliance.
    """

    __tablename__ = "actionauditlog"
    __table_args__ = (
        Index("ix_actionauditlog_rule_id", "rule_id"),
        Index("ix_actionauditlog_triggered_at", "triggered_at"),
        Index("ix_actionauditlog_rule_triggered", "rule_id", "triggered_at"),
        Index("ix_actionauditlog_container_id", "container_id"),
        Index("ix_actionauditlog_status", "status"),
        {"schema": "alerting", "extend_existing": True},
    )

    # Primary key using uuid4 hex string (32 chars)
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String, primary_key=True),
        description="Primary key; auto-generated uuid4 hex",
    )

    # Rule reference (denormalized for query efficiency)
    rule_id: str = Field(
        sa_column=Column(String, nullable=False),
        description="Reference to the alert rule",
    )
    rule_name: str = Field(
        sa_column=Column(String, nullable=False),
        description="Denormalized rule name at time of action",
    )

    # Action details
    action_type: str = Field(
        sa_column=Column(String, nullable=False),
        description="Action type executed",
    )

    # Target information
    container_id: str = Field(
        sa_column=Column(String, nullable=False),
        description="Target container ID",
    )
    herald_id: str = Field(
        sa_column=Column(String, nullable=False),
        description="Herald managing the container",
    )

    # Execution outcome
    status: str = Field(
        sa_column=Column(String, nullable=False),
        description="Outcome: allowed, blocked, success, failed",
    )
    block_reason: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="Reason for blocking (if status=blocked)",
    )
    error_message: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="Error message (if status=failed)",
    )
    duration_ms: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
        description="Execution duration in milliseconds",
    )

    # Context
    initiated_by: str = Field(
        sa_column=Column(String, nullable=False),
        description="Initiator: rule_evaluation, manual, etc.",
    )

    # Timestamp
    triggered_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="When the action was triggered",
    )


__all__ = ["ActionType", "RuleAction", "ActionAuditLog"]
