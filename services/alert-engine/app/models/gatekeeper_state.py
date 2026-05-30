"""
ActionGatekeeperState and GatekeeperConfig models for alert-engine service.

These models track action execution state for rate limiting, cooldowns,
and backoff behavior. The gatekeeper prevents runaway actions from
overwhelming containers.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import Column, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class ActionGatekeeperState(SQLModel, table=True):
    """
    State tracking for action gatekeeper per container/rule/action combination.

    Tracks cooldowns, backoffs, failures, and temporary disables to prevent
    runaway remediation actions from overwhelming containers.
    """

    __tablename__ = "actiongatekeeperstate"
    __table_args__ = (
        Index("ix_actiongatekeeperstate_container_id", "container_id"),
        Index("ix_actiongatekeeperstate_rule_id", "rule_id"),
        Index(
            "ix_actiongatekeeperstate_container_rule",
            "container_id",
            "rule_id",
        ),
        {"schema": "alerting", "extend_existing": True},
    )

    # Composite primary key: container_id + rule_id + action_type
    id: str = Field(
        sa_column=Column(String, primary_key=True),
        description="Composite key: {container_id}_{rule_id}_{action_type}",
    )

    # Identity fields
    container_id: str = Field(
        sa_column=Column(String, nullable=False),
        description="Target container ID",
    )
    rule_id: str = Field(
        sa_column=Column(String, nullable=False),
        description="Alert rule ID",
    )
    action_type: str = Field(
        sa_column=Column(String, nullable=False),
        description="Action type: restart, stop, start, kill, run_script",
    )

    # State tracking timestamps
    last_attempt_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="When the last action attempt was made",
    )
    last_success_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="When the last successful action completed",
    )
    failure_count: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
        description="Consecutive failure count for backoff",
    )

    # Gatekeeper controls
    cooldown_until: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Cooldown expiry after successful action",
    )
    backoff_until: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Backoff expiry after failed action",
    )
    disabled_until: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Temporary disable after too many failures",
    )

    # Rate limiting tracking
    first_limit_hit_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="For hourly limit notification deduplication",
    )

    # Failure context for debugging
    last_error_context: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
        description="Docker errors, container logs from last failure",
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="When the state record was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="When the state was last updated",
    )


class GatekeeperConfig(SQLModel, table=True):
    """
    Persistent configuration for the action gatekeeper (single-row table).

    Stores all gatekeeper settings as a JSON blob for flexibility.
    Default values are applied at the application layer if not configured.

    Settings structure:
    {
        "cooldown_minutes": {"restart": 5, "stop": 10, "start": 2, ...},
        "backoff_delays": [1, 2, 5, 10, 30],  // minutes
        "max_backoff_minutes": 60,
        "disable_after_failures": 5,
        "disable_duration_minutes": 30,
        "max_actions_per_rule_per_hour": 10,
        "max_actions_per_container_per_hour": 20,
        "verification_delay_seconds": 5
    }
    """

    __tablename__ = "gatekeeperconfig"
    __table_args__ = ({"schema": "alerting", "extend_existing": True},)

    # Single-row table with fixed ID
    id: int = Field(
        default=1,
        sa_column=Column(Integer, primary_key=True),
        description="Fixed ID=1 for single-row table",
    )

    # Full settings blob as JSON
    settings: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
        description="Gatekeeper configuration settings",
    )

    # Timestamp
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="When the config was last updated",
    )


__all__ = ["ActionGatekeeperState", "GatekeeperConfig"]
