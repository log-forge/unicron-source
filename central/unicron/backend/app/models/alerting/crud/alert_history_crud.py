"""
CRUD operations for AlertHistory model.

Supports partition-aware queries for time-based data retrieval.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.alerting.alert_history_model import AlertHistory


async def create_alert_history(
    session: AsyncSession,
    *,
    rule_id: str,
    rule_name: str,
    severity: str,
    message: str,
    organization_id: str,
    context: Optional[Dict[str, Any]] = None,
    status: str = "triggered",
    triggered_at: Optional[datetime] = None,
) -> AlertHistory:
    """Create a new alert history record."""
    history = AlertHistory(
        rule_id=rule_id,
        rule_name=rule_name,
        severity=severity,
        message=message,
        context=context or {},
        status=status,
        triggered_at=triggered_at or datetime.now(timezone.utc),
        organization_id=organization_id,
    )
    session.add(history)
    await session.commit()
    await session.refresh(history)
    return history


async def get_alert_history(
    session: AsyncSession,
    history_id: str,
    organization_id: str,
    *,
    triggered_at: Optional[datetime] = None,
) -> Optional[AlertHistory]:
    """
    Get an alert history record by ID.

    If triggered_at is provided, it enables partition pruning for faster lookups.
    """
    stmt = select(AlertHistory).where(
        AlertHistory.id == history_id,
        AlertHistory.organization_id == organization_id,
    )

    if triggered_at:
        stmt = stmt.where(AlertHistory.triggered_at == triggered_at)

    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_alert_history_by_rule(
    session: AsyncSession,
    rule_id: str,
    organization_id: str,
    *,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 100,
) -> List[AlertHistory]:
    """
    Get alert history for a specific rule with optional time range filtering.

    Time range filtering enables efficient partition pruning.
    """
    stmt = select(AlertHistory).where(
        AlertHistory.rule_id == rule_id,
        AlertHistory.organization_id == organization_id,
    )

    if start_time:
        stmt = stmt.where(AlertHistory.triggered_at >= start_time)
    if end_time:
        stmt = stmt.where(AlertHistory.triggered_at < end_time)

    stmt = stmt.order_by(AlertHistory.triggered_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_alert_history_by_organization(
    session: AsyncSession,
    organization_id: str,
    *,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[AlertHistory]:
    """
    Get alert history for an organization with filters.

    Time range filtering enables efficient partition pruning.
    """
    stmt = select(AlertHistory).where(
        AlertHistory.organization_id == organization_id,
    )

    if start_time:
        stmt = stmt.where(AlertHistory.triggered_at >= start_time)
    if end_time:
        stmt = stmt.where(AlertHistory.triggered_at < end_time)
    if severity:
        stmt = stmt.where(AlertHistory.severity == severity)
    if status:
        stmt = stmt.where(AlertHistory.status == status)

    stmt = stmt.order_by(AlertHistory.triggered_at.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_alert_history_status(
    session: AsyncSession,
    history: AlertHistory,
    *,
    status: str,
    acknowledged_by: Optional[str] = None,
) -> AlertHistory:
    """
    Update alert history status.
    """
    now = datetime.now(timezone.utc)

    history.status = status

    if status == "acknowledged" and history.acknowledged_at is None:
        history.acknowledged_at = now
        history.acknowledged_by = acknowledged_by

    session.add(history)
    await session.commit()
    await session.refresh(history)
    return history


async def ensure_partition_exists(
    session: AsyncSession, partition_date: datetime
) -> None:
    """
    Ensure a partition exists for the given date.

    Calls the partition maintenance function created in the migration.
    """
    await session.execute(
        text("SELECT alerting.create_alerthistory_partition(:partition_date)"),
        {"partition_date": partition_date.date()},
    )
    await session.commit()
