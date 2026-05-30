"""
Rule service for alert-engine.

Provides business logic for alert rule CRUD operations.
This service is independent of Central and manages its own model definition
that maps to the shared alerting.alertrule table.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel

from app.core.logging import get_logger

logger = get_logger("alert-engine.services.rule")


class AlertRule(SQLModel, table=True):
    """
    Alert rule definition.

    This mirrors the AlertRule model from Central but is defined here
    to keep alert-engine independent. Both services connect to the same
    PostgreSQL database and share the alerting.alertrule table.
    """

    __tablename__ = "alertrule"
    __table_args__ = (
        Index("ix_alertrule_organization_id", "organization_id"),
        Index("ix_alertrule_enabled_organization_id", "enabled", "organization_id"),
        Index(
            "ix_alertrule_scope_type_organization_id", "scope_type", "organization_id"
        ),
        {"schema": "alerting", "extend_existing": True},
    )

    # Primary key using uuid4 hex string (32 chars)
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(String, primary_key=True, index=True),
    )

    # Rule identification
    name: str = Field(sa_column=Column(String, nullable=False))
    description: Optional[str] = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )

    # Trigger configuration
    trigger_type: str = Field(sa_column=Column(String, nullable=False))
    trigger_config: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )

    # Scope configuration
    scope_type: str = Field(
        default="global",
        sa_column=Column(String, nullable=False, server_default="'global'"),
    )
    scope_targets: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
    )

    # Alert properties
    severity: str = Field(
        default="warning",
        sa_column=Column(String, nullable=False, server_default="'warning'"),
    )
    labels: Dict[str, str] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )
    annotations: Dict[str, str] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )

    # State
    enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true"),
    )

    # Multi-tenancy
    organization_id: str = Field(
        sa_column=Column(String, nullable=False, index=True),
    )

    # Audit fields
    created_by: Optional[str] = Field(
        default=None, sa_column=Column(String, nullable=True)
    )
    updated_by: Optional[str] = Field(
        default=None, sa_column=Column(String, nullable=True)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class RuleNotFoundError(Exception):
    """Raised when a rule is not found in the database."""

    pass


class RuleService:
    """
    Service for alert rule operations.

    Provides CRUD operations with business logic and organization scoping.
    All operations are scoped to an organization for multi-tenant isolation.

    Organization Isolation Audit (verified):
    - list_rules: filters by organization_id
    - get_rule/get_rule_or_raise: checks both rule_id AND organization_id
    - create_rule: organization_id is required parameter (from user context)
    - update_rule: uses get_rule_or_raise for org-scoped fetch
    - delete_rule: uses get_rule_or_raise for org-scoped fetch
    - toggle_rule: delegates to update_rule with org scope
    """

    def __init__(self, session: AsyncSession):
        """Initialize the service with a database session."""
        self.session = session

    async def create_rule(
        self,
        *,
        name: str,
        trigger_type: str,
        trigger_config: Dict[str, Any],
        organization_id: str,
        scope_type: str = "global",
        scope_targets: Optional[List[str]] = None,
        severity: str = "warning",
        labels: Optional[Dict[str, str]] = None,
        annotations: Optional[Dict[str, str]] = None,
        description: Optional[str] = None,
        enabled: bool = True,
        created_by: Optional[str] = None,
    ) -> AlertRule:
        """
        Create a new alert rule.

        Args:
            name: Human-readable rule name.
            trigger_type: Type of trigger (threshold, keyword, rate, absence).
            trigger_config: Trigger-specific parameters.
            organization_id: Organization ID for multi-tenant isolation.
            scope_type: Scope type (global, container, group, herald).
            scope_targets: Target IDs for the scope.
            severity: Alert severity (critical, warning, info).
            labels: Additional labels for routing and filtering.
            annotations: Additional annotations for display.
            description: Optional detailed description.
            enabled: Whether the rule is active.
            created_by: User ID who created the rule.

        Returns:
            The created AlertRule instance.
        """
        rule = AlertRule(
            id=uuid.uuid4().hex,
            name=name,
            description=description,
            trigger_type=trigger_type,
            trigger_config=trigger_config,
            scope_type=scope_type,
            scope_targets=scope_targets or [],
            severity=severity,
            labels=labels or {},
            annotations=annotations or {},
            enabled=enabled,
            organization_id=organization_id,
            created_by=created_by,
            updated_by=created_by,
        )
        self.session.add(rule)
        await self.session.commit()
        await self.session.refresh(rule)
        logger.info("Created rule %s for org %s", rule.id, organization_id)
        return rule

    async def count_rules(self, organization_id: str) -> int:
        stmt = select(func.count()).select_from(AlertRule).where(
            AlertRule.organization_id == organization_id,
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def get_rule(
        self, rule_id: str, organization_id: str
    ) -> Optional[AlertRule]:
        """
        Get a rule by ID, scoped to organization.

        Args:
            rule_id: The rule ID to look up.
            organization_id: The organization ID for scoping.

        Returns:
            The AlertRule if found, None otherwise.
        """
        stmt = select(AlertRule).where(
            AlertRule.id == rule_id,
            AlertRule.organization_id == organization_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_rule_or_raise(
        self, rule_id: str, organization_id: str
    ) -> AlertRule:
        """
        Get a rule by ID or raise RuleNotFoundError.

        Args:
            rule_id: The rule ID to look up.
            organization_id: The organization ID for scoping.

        Returns:
            The AlertRule if found.

        Raises:
            RuleNotFoundError: If the rule is not found.
        """
        rule = await self.get_rule(rule_id, organization_id)
        if not rule:
            raise RuleNotFoundError(f"Rule {rule_id} not found")
        return rule

    async def list_rules(
        self,
        organization_id: str,
        *,
        enabled_only: bool = False,
        scope_type: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[List[AlertRule], int]:
        """
        List rules for an organization with pagination.

        Args:
            organization_id: The organization ID for scoping.
            enabled_only: If True, only return enabled rules.
            scope_type: Filter by scope type.
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            A tuple of (list of rules, total count).
        """
        # Build base query
        stmt = select(AlertRule).where(AlertRule.organization_id == organization_id)

        if enabled_only:
            stmt = stmt.where(AlertRule.enabled == True)  # noqa: E712

        if scope_type:
            stmt = stmt.where(AlertRule.scope_type == scope_type)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar_one()

        # Apply pagination
        stmt = stmt.order_by(AlertRule.name.asc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        rules = list(result.scalars().all())

        return rules, total

    async def update_rule(
        self,
        rule_id: str,
        organization_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        trigger_type: Optional[str] = None,
        trigger_config: Optional[Dict[str, Any]] = None,
        scope_type: Optional[str] = None,
        scope_targets: Optional[List[str]] = None,
        severity: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None,
        annotations: Optional[Dict[str, str]] = None,
        enabled: Optional[bool] = None,
        updated_by: Optional[str] = None,
    ) -> AlertRule:
        """
        Update an existing rule.

        Args:
            rule_id: The rule ID to update.
            organization_id: The organization ID for scoping.
            name: New rule name.
            description: New description.
            trigger_type: New trigger type.
            trigger_config: New trigger configuration.
            scope_type: New scope type.
            scope_targets: New scope targets.
            severity: New severity.
            labels: New labels.
            annotations: New annotations.
            enabled: New enabled state.
            updated_by: User ID who updated the rule.

        Returns:
            The updated AlertRule.

        Raises:
            RuleNotFoundError: If the rule is not found.
        """
        rule = await self.get_rule_or_raise(rule_id, organization_id)

        if name is not None:
            rule.name = name
        if description is not None:
            rule.description = description
        if trigger_type is not None:
            rule.trigger_type = trigger_type
        if trigger_config is not None:
            rule.trigger_config = trigger_config
        if scope_type is not None:
            rule.scope_type = scope_type
        if scope_targets is not None:
            rule.scope_targets = scope_targets
        if severity is not None:
            rule.severity = severity
        if labels is not None:
            rule.labels = labels
        if annotations is not None:
            rule.annotations = annotations
        if enabled is not None:
            rule.enabled = enabled

        rule.updated_at = datetime.now(timezone.utc)
        rule.updated_by = updated_by

        self.session.add(rule)
        await self.session.commit()
        await self.session.refresh(rule)
        logger.info("Updated rule %s", rule_id)
        return rule

    async def delete_rule(self, rule_id: str, organization_id: str) -> bool:
        """
        Delete a rule.

        Args:
            rule_id: The rule ID to delete.
            organization_id: The organization ID for scoping.

        Returns:
            True if the rule was deleted.

        Raises:
            RuleNotFoundError: If the rule is not found.
        """
        rule = await self.get_rule_or_raise(rule_id, organization_id)
        await self.session.delete(rule)
        await self.session.commit()
        logger.info("Deleted rule %s", rule_id)
        return True

    async def toggle_rule(
        self,
        rule_id: str,
        organization_id: str,
        enabled: bool,
        updated_by: Optional[str] = None,
    ) -> AlertRule:
        """
        Enable or disable a rule.

        Args:
            rule_id: The rule ID to toggle.
            organization_id: The organization ID for scoping.
            enabled: New enabled state.
            updated_by: User ID who toggled the rule.

        Returns:
            The updated AlertRule.

        Raises:
            RuleNotFoundError: If the rule is not found.
        """
        return await self.update_rule(
            rule_id, organization_id, enabled=enabled, updated_by=updated_by
        )


__all__ = [
    "RuleService",
    "AlertRule",
    "RuleNotFoundError",
]
