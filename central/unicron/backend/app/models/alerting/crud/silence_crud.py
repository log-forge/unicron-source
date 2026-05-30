"""
CRUD operations for Silence model.

Supports time-range queries for active silence detection.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.alerting.silence_model import Silence


async def create_silence(
    session: AsyncSession,
    *,
    starts_at: datetime,
    ends_at: datetime,
    created_by: str,
    organization_id: str,
    matchers: Optional[List[Dict[str, Any]]] = None,
    comment: Optional[str] = None,
    recurring: bool = False,
    recurrence_rule: Optional[str] = None,
) -> Silence:
    """Create a new silence."""
    silence = Silence(
        matchers=matchers or [],
        starts_at=starts_at,
        ends_at=ends_at,
        created_by=created_by,
        comment=comment,
        recurring=recurring,
        recurrence_rule=recurrence_rule,
        organization_id=organization_id,
    )
    session.add(silence)
    await session.commit()
    await session.refresh(silence)
    return silence


async def get_silence(
    session: AsyncSession, silence_id: str, organization_id: str
) -> Optional[Silence]:
    """Get a silence by ID, scoped to organization."""
    stmt = select(Silence).where(
        Silence.id == silence_id,
        Silence.organization_id == organization_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_active_silences(
    session: AsyncSession,
    organization_id: str,
    *,
    at_time: Optional[datetime] = None,
) -> List[Silence]:
    """
    Get all currently active silences for an organization.

    A silence is active if:
    - starts_at <= at_time < ends_at
    - not expired
    """
    now = at_time or datetime.now(timezone.utc)

    stmt = select(Silence).where(
        Silence.organization_id == organization_id,
        Silence.starts_at <= now,
        Silence.ends_at > now,
        Silence.expired == False,
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_silences_by_organization(
    session: AsyncSession,
    organization_id: str,
    *,
    include_expired: bool = False,
    include_past: bool = False,
) -> List[Silence]:
    """Get all silences for an organization with optional filters."""
    stmt = select(Silence).where(Silence.organization_id == organization_id)

    if not include_expired:
        stmt = stmt.where(Silence.expired == False)

    if not include_past:
        now = datetime.now(timezone.utc)
        stmt = stmt.where(Silence.ends_at > now)

    stmt = stmt.order_by(Silence.starts_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def expire_silence(session: AsyncSession, silence: Silence) -> Silence:
    """Manually expire a silence before its end time."""
    silence.expired = True
    silence.updated_at = datetime.now(timezone.utc)
    session.add(silence)
    await session.commit()
    await session.refresh(silence)
    return silence


async def delete_silence(session: AsyncSession, silence: Silence) -> bool:
    """Delete a silence."""
    await session.delete(silence)
    await session.commit()
    return True


async def update_silence(
    session: AsyncSession,
    silence: Silence,
    *,
    starts_at: Optional[datetime] = None,
    ends_at: Optional[datetime] = None,
    matchers: Optional[List[Dict[str, Any]]] = None,
    comment: Optional[str] = None,
    recurring: Optional[bool] = None,
    recurrence_rule: Optional[str] = None,
) -> Silence:
    """Update an existing silence."""
    if starts_at is not None:
        silence.starts_at = starts_at
    if ends_at is not None:
        silence.ends_at = ends_at
    if matchers is not None:
        silence.matchers = matchers
    if comment is not None:
        silence.comment = comment
    if recurring is not None:
        silence.recurring = recurring
    if recurrence_rule is not None:
        silence.recurrence_rule = recurrence_rule

    silence.updated_at = datetime.now(timezone.utc)
    session.add(silence)
    await session.commit()
    await session.refresh(silence)
    return silence
