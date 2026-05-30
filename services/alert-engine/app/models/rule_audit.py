"""Audit log model for rule operations."""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from sqlalchemy import Column, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class RuleAuditAction(str, Enum):
    """Types of rule audit actions."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    ENABLED = "enabled"
    DISABLED = "disabled"


class RuleAuditLog(SQLModel, table=True):
    """
    Audit log for rule operations.

    Tracks all create/update/delete operations with user context,
    timestamps, and change details for compliance.
    """

    __tablename__ = "ruleauditlog"
    __table_args__ = (
        Index("ix_ruleauditlog_rule_id", "rule_id"),
        Index("ix_ruleauditlog_user_id", "user_id"),
        Index("ix_ruleauditlog_organization_id", "organization_id"),
        Index("ix_ruleauditlog_action", "action"),
        Index("ix_ruleauditlog_timestamp", "timestamp"),
        Index("ix_ruleauditlog_rule_timestamp", "rule_id", "timestamp"),
        {"schema": "alerting", "extend_existing": True},
    )

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String(32), primary_key=True),
    )

    # What was affected
    rule_id: str = Field(sa_column=Column(String(32), nullable=False, index=True))
    rule_name: str = Field(sa_column=Column(String(255), nullable=False))

    # Who did it
    user_id: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    user_email: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    organization_id: str = Field(
        sa_column=Column(String(255), nullable=False, index=True)
    )

    # What action
    action: RuleAuditAction = Field(sa_column=Column(String(20), nullable=False))

    # When
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        sa_column=Column(String(50), nullable=False),
    )

    # Details - stores rule snapshot or changed fields
    details: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, default={}),
    )

    # For updates: what changed (before/after)
    changes: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSONB),
    )


__all__ = ["RuleAuditAction", "RuleAuditLog"]
