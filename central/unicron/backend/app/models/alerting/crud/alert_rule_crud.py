"""
CRUD operations for AlertRule model.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.alerting.alert_rule_model import AlertRule


async def create_alert_rule(
    session: AsyncSession,
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
    """Create a new alert rule."""
    rule = AlertRule(
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
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


async def get_alert_rule(
    session: AsyncSession, rule_id: str, organization_id: str
) -> Optional[AlertRule]:
    """Get an alert rule by ID, scoped to organization."""
    stmt = select(AlertRule).where(
        AlertRule.id == rule_id,
        AlertRule.organization_id == organization_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_alert_rules_by_organization(
    session: AsyncSession,
    organization_id: str,
    *,
    enabled_only: bool = False,
    scope_type: Optional[str] = None,
) -> List[AlertRule]:
    """Get all alert rules for an organization with optional filters."""
    stmt = select(AlertRule).where(AlertRule.organization_id == organization_id)

    if enabled_only:
        stmt = stmt.where(AlertRule.enabled == True)

    if scope_type:
        stmt = stmt.where(AlertRule.scope_type == scope_type)

    stmt = stmt.order_by(AlertRule.name.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_enabled_alert_rules(
    session: AsyncSession, organization_id: str
) -> List[AlertRule]:
    """Get all enabled alert rules for an organization."""
    return await get_alert_rules_by_organization(
        session, organization_id, enabled_only=True
    )


async def update_alert_rule(
    session: AsyncSession,
    rule: AlertRule,
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
    """Update an existing alert rule."""
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

    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


async def delete_alert_rule(session: AsyncSession, rule: AlertRule) -> bool:
    """Delete an alert rule."""
    await session.delete(rule)
    await session.commit()
    return True
