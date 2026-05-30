from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models.container.container_model import Container
from app.models.group.group_model import Group
from app.models.herald.herald_model import Herald
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from unicron_shared import HeraldStaticMetrics, HeraldStatus


async def create_herald(
    session: AsyncSession,
    herald_name: str,
    central_url: str,
    herald_id: Optional[str] = None,
    registered_at: Optional[datetime] = None,
    check_in_interval: Optional[int] = None,
    tags: Optional[List[str]] = None,
    cpu_count: Optional[int] = None,
) -> Herald:
    herald = Herald(
        herald_name=herald_name,
        central_url=central_url,
        check_in_interval=check_in_interval or 60,
        tags=tags or [],
        cpu_count=cpu_count,
    )
    if herald_id is not None:
        herald.id = herald_id
    if registered_at is not None:
        registered_at = registered_at.astimezone(timezone.utc)

    session.add(herald)

    await session.commit()
    await session.refresh(herald)
    return herald


async def get_herald(session: AsyncSession, herald_id: str) -> Optional[Herald]:
    return await session.get(Herald, herald_id)


async def update_herald_central_url(session: AsyncSession, herald_id: str, central_url: str) -> Optional[Herald]:
    herald = await session.get(Herald, herald_id)
    if herald:
        herald.central_url = central_url
        await session.commit()
        await session.refresh(herald)
    return herald


async def delete_herald(session: AsyncSession, herald_id: str) -> None:
    herald = await session.get(Herald, herald_id)
    if herald:
        await session.delete(herald)
        await session.commit()


async def update_herald_health(
    session: AsyncSession,
    herald_id: str,
    health_status: str,
    last_ping: datetime,
    health_message: str = "",
    remote_address: Optional[str] = None,
) -> Optional[Herald]:
    herald = await session.get(Herald, herald_id)
    if herald:
        # Coerce to enum value if needed
        try:
            herald.health_status = HeraldStatus(health_status)
        except Exception:
            herald.health_status = HeraldStatus.unknown
        herald.last_ping = last_ping
        herald.health_message = health_message
        # Update remote_address if provided and different
        if remote_address is not None and getattr(herald, "remote_address", None) != remote_address:
            herald.remote_address = remote_address
        await session.commit()
        await session.refresh(herald)
    return herald


async def list_heralds(session: AsyncSession) -> List[Herald]:
    """
    Returns active Herald objects ordered by registration time (oldest first).
    """
    stmt = (
        select(Herald)
        .where(getattr(Herald, "unregistered") == False)  # noqa: E712
        .order_by(getattr(Herald, "registered_at").asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_heralds_by_ids(session: AsyncSession, herald_ids: list[str]) -> List[Herald]:
    if not herald_ids:
        return []
    stmt = (
        select(Herald)
        .where(getattr(Herald, "id").in_(herald_ids))
        .where(getattr(Herald, "unregistered") == False)  # noqa: E712
        .order_by(getattr(Herald, "registered_at").asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_registered_herald_ids_by_ids(session: AsyncSession, herald_ids: list[str]) -> list[str]:
    """Return ids from the given set whose herald lifecycle is still active."""
    if not herald_ids:
        return []

    stmt = (
        select(getattr(Herald, "id"))
        .where(getattr(Herald, "id").in_(herald_ids))
        .where(getattr(Herald, "unregistered") == False)  # noqa: E712
        .order_by(getattr(Herald, "registered_at").asc(), getattr(Herald, "id").asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def summarize_heralds(session: AsyncSession) -> Dict[str, Any]:
    """
    Returns a summary dict with:
        - total: total number of Heralds
        - statuses: dict of health_status -> count
        - last_ping_latest: ISO timestamp of most recent last_ping (or None)
    """
    # counts per health_status + total + last_ping recency
    active_filter = getattr(Herald, "unregistered") == False  # noqa: E712
    status_counts_stmt = (
        select(getattr(Herald, "health_status"), func.count().label("count"))
        .where(active_filter)
        .group_by(Herald.health_status)
    )
    status_counts_result = await session.execute(status_counts_stmt)
    status_counts = {str(row[0]): row[1] for row in status_counts_result.all() if row[0] is not None}

    total_stmt = select(func.count()).select_from(Herald).where(active_filter)
    total = (await session.execute(total_stmt)).scalar_one()

    last_ping_stmt = select(func.max(getattr(Herald, "last_ping"))).where(active_filter)
    last_ping = (await session.execute(last_ping_stmt)).scalar_one()

    online_stmt = (
        select(func.count())
        .select_from(Herald)
        .where(getattr(Herald, "socket_online") == True, active_filter)
    )  # noqa: E712
    socket_online_total = (await session.execute(online_stmt)).scalar_one()

    group_counts_stmt = (
        select(getattr(Group, "name"), func.count())
        .select_from(Container)
        .join(Group, getattr(Container, "group_id") == getattr(Group, "id"))
        .join(Herald, getattr(Container, "herald_id") == getattr(Herald, "id"))
        .where(active_filter)
        .group_by(getattr(Group, "name"))
    )
    group_counts = {row[0]: row[1] for row in (await session.execute(group_counts_stmt)).all() if row[0]}

    region_counts_stmt = (
        select(getattr(Herald, "region"), func.count())
        .where(getattr(Herald, "region").isnot(None), active_filter)
        .group_by(getattr(Herald, "region"))
    )
    region_counts = {row[0]: row[1] for row in (await session.execute(region_counts_stmt)).all() if row[0] is not None}

    return {
        "total": total,
        "statuses": status_counts,
        "last_ping_latest": last_ping.isoformat() if last_ping else None,
        "socket_online_total": socket_online_total,
        "groups": group_counts,
        "regions": region_counts,
    }


async def summarize_heralds_by_ids(session: AsyncSession, herald_ids: list[str]) -> Dict[str, Any]:
    if not herald_ids:
        return {
            "total": 0,
            "statuses": {},
            "last_ping_latest": None,
            "socket_online_total": 0,
            "groups": {},
            "regions": {},
        }

    id_col = getattr(Herald, "id")
    filter_ids = id_col.in_(herald_ids)
    active_filter = getattr(Herald, "unregistered") == False  # noqa: E712

    status_counts_stmt = (
        select(getattr(Herald, "health_status"), func.count().label("count"))
        .where(filter_ids, active_filter)
        .group_by(Herald.health_status)
    )
    status_counts_result = await session.execute(status_counts_stmt)
    status_counts = {str(row[0]): row[1] for row in status_counts_result.all() if row[0] is not None}

    total_stmt = select(func.count()).select_from(Herald).where(filter_ids, active_filter)
    total = (await session.execute(total_stmt)).scalar_one()

    last_ping_stmt = select(func.max(getattr(Herald, "last_ping"))).where(filter_ids, active_filter)
    last_ping = (await session.execute(last_ping_stmt)).scalar_one()

    online_stmt = (
        select(func.count())
        .select_from(Herald)
        .where(getattr(Herald, "socket_online") == True, filter_ids, active_filter)  # noqa: E712
    )
    socket_online_total = (await session.execute(online_stmt)).scalar_one()

    group_counts_stmt = (
        select(getattr(Group, "name"), func.count())
        .select_from(Container)
        .join(Group, getattr(Container, "group_id") == getattr(Group, "id"))
        .join(Herald, getattr(Container, "herald_id") == getattr(Herald, "id"))
        .where(getattr(Container, "herald_id").in_(herald_ids), active_filter)
        .group_by(getattr(Group, "name"))
    )
    group_counts = {row[0]: row[1] for row in (await session.execute(group_counts_stmt)).all() if row[0]}

    region_counts_stmt = (
        select(getattr(Herald, "region"), func.count())
        .where(getattr(Herald, "region").isnot(None), filter_ids, active_filter)
        .group_by(getattr(Herald, "region"))
    )
    region_counts = {row[0]: row[1] for row in (await session.execute(region_counts_stmt)).all() if row[0] is not None}

    return {
        "total": total,
        "statuses": status_counts,
        "last_ping_latest": last_ping.isoformat() if last_ping else None,
        "socket_online_total": socket_online_total,
        "groups": group_counts,
        "regions": region_counts,
    }


async def mark_herald_unregistered(
    session: AsyncSession,
    herald_id: str,
    *,
    reason: str | None = None,
    by: str | None = None,
) -> Optional[Herald]:
    herald = await session.get(Herald, herald_id)
    if not herald:
        return None

    now = datetime.now(timezone.utc)
    herald.unregistered = True
    herald.unregistered_at = herald.unregistered_at or now
    if reason:
        herald.unregistered_reason = reason
    if by:
        herald.unregistered_by = by
    herald.socket_online = False

    await session.commit()
    await session.refresh(herald)
    return herald


async def mark_herald_registered(
    session: AsyncSession,
    herald_id: str,
) -> Optional[Herald]:
    """Clear explicit unregistered lifecycle state for a herald, if present."""
    herald = await session.get(Herald, herald_id)
    if not herald:
        return None

    herald.unregistered = False
    herald.unregistered_at = None
    herald.unregistered_reason = None
    herald.unregistered_by = None

    await session.commit()
    await session.refresh(herald)
    return herald


async def set_socket_presence(
    session: AsyncSession,
    herald_id: str,
    online: bool,
    *,
    at: Optional[datetime] = None,
) -> Optional[Herald]:
    """Set socket presence flags for a Herald.

    Updates socket_online and socket_last_seen (defaults to now UTC).
    """
    herald = await session.get(Herald, herald_id)
    if not herald:
        return None

    ts = at or datetime.now(timezone.utc)
    herald.socket_online = online
    herald.socket_last_seen = ts

    await session.commit()
    await session.refresh(herald)

    return herald


async def update_herald_static_metrics(
    session: AsyncSession, herald_id: str, metrics: HeraldStaticMetrics
) -> Optional[Herald]:
    herald = await session.get(Herald, herald_id)
    if not herald:
        return None

    herald.hostname = metrics.hostname or herald.hostname
    herald.herald_os = metrics.os or herald.herald_os
    herald.os_version = metrics.os_version or herald.os_version
    herald.architecture = metrics.architecture or herald.architecture
    herald.cpu_count = metrics.cpu_count if metrics.cpu_count is not None else herald.cpu_count
    herald.host_total_memory_bytes = (
        metrics.total_memory_bytes if metrics.total_memory_bytes is not None else herald.host_total_memory_bytes
    )
    herald.herald_version = metrics.herald_version or herald.herald_version

    await session.commit()
    await session.refresh(herald)
    return herald
