"""
CRUD operations for AlertState model.

Supports fingerprint-based deduplication and active alert management.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.alerting.alert_state_model import AlertState


async def upsert_alert_state(
    session: AsyncSession,
    *,
    rule_id: str,
    fingerprint: str,
    severity: str,
    organization_id: str,
    labels: Optional[Dict[str, str]] = None,
    annotations: Optional[Dict[str, Any]] = None,
    value: Optional[str] = None,
    status: str = "firing",
    ends_at: Optional[datetime] = None,
) -> AlertState:
    """
    Create or update an alert state by fingerprint.

    If an alert with the same fingerprint exists, update it.
    Otherwise, create a new alert state.
    """
    stmt = select(AlertState).where(AlertState.fingerprint == fingerprint)
    result = await session.execute(stmt)
    state = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if state is None:
        state = AlertState(
            rule_id=rule_id,
            fingerprint=fingerprint,
            status=status,
            severity=severity,
            labels=labels or {},
            annotations=annotations or {},
            value=value,
            started_at=now,
            ends_at=ends_at,
            updated_at=now,
            organization_id=organization_id,
        )
        session.add(state)
    else:
        # Update existing state
        state.status = status
        state.severity = severity
        if labels is not None:
            state.labels = labels
        if annotations is not None:
            state.annotations = annotations
        if value is not None:
            state.value = value
        if ends_at is not None:
            state.ends_at = ends_at
        state.updated_at = now
        session.add(state)

    await session.commit()
    await session.refresh(state)
    return state


async def get_alert_state(
    session: AsyncSession, state_id: str, organization_id: str
) -> Optional[AlertState]:
    """Get an alert state by ID, scoped to organization."""
    stmt = select(AlertState).where(
        AlertState.id == state_id,
        AlertState.organization_id == organization_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_alert_state_by_fingerprint(
    session: AsyncSession, fingerprint: str
) -> Optional[AlertState]:
    """Get an alert state by fingerprint (globally unique)."""
    stmt = select(AlertState).where(AlertState.fingerprint == fingerprint)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_active_alerts_by_organization(
    session: AsyncSession,
    organization_id: str,
    *,
    rule_id: Optional[str] = None,
    severity: Optional[str] = None,
) -> List[AlertState]:
    """Get all active (firing or pending) alerts for an organization."""
    stmt = select(AlertState).where(
        AlertState.organization_id == organization_id,
        AlertState.status.in_(["firing", "pending"]),
    )

    if rule_id:
        stmt = stmt.where(AlertState.rule_id == rule_id)
    if severity:
        stmt = stmt.where(AlertState.severity == severity)

    stmt = stmt.order_by(AlertState.started_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_alert_state(session: AsyncSession, state: AlertState) -> bool:
    """Delete an alert state row."""
    await session.delete(state)
    await session.commit()
    return True


async def get_alert_states_by_rule(
    session: AsyncSession,
    rule_id: str,
    organization_id: str,
) -> List[AlertState]:
    """Get all alert states for a specific rule."""
    stmt = select(AlertState).where(
        AlertState.rule_id == rule_id,
        AlertState.organization_id == organization_id,
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
