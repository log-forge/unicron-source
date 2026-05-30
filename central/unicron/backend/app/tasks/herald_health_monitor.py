"""Health monitor tasks for Herald agents.

This module provides a periodic background job that scans all registered Herald
agents and marks them as unhealthy if they have not checked in within an
acceptable window.

Behavior summary:
- Uses an AsyncIOScheduler to run check_stale_heralds on a fixed interval.
- check_stale_heralds opens an async DB session, loads all Herald rows, and for
    each computes the last known ping time (last_ping or registered_at). If the
    elapsed time exceeds herald.check_in_interval + HERALD_STALE_GRACE the
    Herald is marked unhealthy via update_herald_health.
- start_health_monitor_scheduler ensures the scheduler is started (idempotent).

Notes:
- This module is async-friendly and intended to be started during application
    startup. No blocking operations are added here.
"""

from datetime import datetime, timezone

from app.core.config import settings
from app.core.database import session_ctx
from app.core.logging import get_logger
from app.models.herald.crud.herald_crud import update_herald_health
from app.models.herald.herald_model import Herald
from app.socket.emitters.central.health import emit_herald_health_update
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import select

HERALD_STALE_GRACE = settings.HERALD_STALE_GRACE
SOCKET_STALE_GRACE = settings.HERALD_STALE_GRACE
# Jitter policy for scheduled background jobs to avoid thundering-herd on
# scheduler restarts or multiple instances. Default to 10% and cap to 20s.
JITTER_PERCENT = 0.1

logger = get_logger(__name__)


# Helper to compute jitter seconds from an interval (seconds)
def compute_jitter(interval_seconds: int) -> int:
    try:
        if interval_seconds <= 0:
            return 0
        jitter = int(max(1, min(int(interval_seconds * JITTER_PERCENT), 20)))
        return jitter
    except Exception:
        return 0


async def check_stale_heralds():
    """Scan all Herald records and mark stale agents as unhealthy.

    This coroutine:
    - Acquires an async DB session from get_session().
    - Loads all Herald entries.
    - For each Herald, uses last_ping if present otherwise registered_at as the
        baseline time.
    - If (now - baseline) > (herald.check_in_interval + HERALD_STALE_GRACE)
        it calls update_herald_health(session, herald.id, "unhealthy", last_ping, reason).

    Side effects:
    - Updates the database via update_herald_health.
    - Designed to be scheduled periodically by the module scheduler.

    Implementation detail:
    - The function iterates the async session generator and breaks after the
        first session to avoid accidentally opening multiple sessions.
    """
    async with session_ctx() as session:
        now = datetime.now(timezone.utc)
        stmt = select(Herald).where(getattr(Herald, "unregistered") == False)  # noqa: E712
        results = await session.execute(stmt)
        heralds = results.scalars().all()
        for herald in heralds:
            last_ping = herald.last_ping or herald.registered_at
            if (now - last_ping).total_seconds() > (herald.check_in_interval * HERALD_STALE_GRACE):
                updated = await update_herald_health(
                    session, herald.id, "unhealthy", last_ping, "No recent health ping"
                )
                if updated is not None:
                    try:
                        await emit_herald_health_update(updated)
                    except Exception:
                        logger.debug(
                            "check_stale_heralds: failed to emit health update for %s", herald.id, exc_info=True
                        )


async def sweep_socket_presence():
    """Mark sockets offline if last_seen is too old.

    If a herald is marked socket_online but socket_last_seen is older than
    (herald.check_in_interval * SOCKET_STALE_GRACE), flip it to offline.
    """
    async with session_ctx() as session:
        now = datetime.now(timezone.utc)
        stmt = select(Herald).where(
            getattr(Herald, "socket_online") == True,  # noqa: E712
            getattr(Herald, "unregistered") == False,  # noqa: E712
        )
        results = await session.execute(stmt)

        heralds = results.scalars().all()
        changed: list[Herald] = []
        for h in heralds:
            # Only socket_last_seen reflects websocket presence; if missing, mark offline.
            last = h.socket_last_seen
            if last is None:
                if h.socket_online:
                    h.socket_online = False
                    changed.append(h)
                continue
            if (now - last).total_seconds() > (h.check_in_interval * SOCKET_STALE_GRACE):
                if h.socket_online:
                    h.socket_online = False
                    changed.append(h)

        await session.commit()

    for herald in changed:
        try:
            await emit_herald_health_update(herald)
        except Exception:
            logger.debug("sweep_socket_presence: failed to emit update for %s", herald.id, exc_info=True)


def register_jobs(sched: AsyncIOScheduler) -> None:
    """Register all periodic jobs for this service.

    Only call from the lock-owning process before starting the scheduler.
    """
    interval = 60
    sched.add_job(
        check_stale_heralds,
        "interval",
        seconds=interval,  # Check every 1 minutes
        id="check_stale_heralds",
        max_instances=1,
        replace_existing=True,
        jitter=compute_jitter(interval),
    )
    sched.add_job(
        sweep_socket_presence,
        "interval",
        seconds=interval,  # Check every 1 minutes
        id="sweep_socket_presence",
        max_instances=1,
        replace_existing=True,
        jitter=compute_jitter(interval),
    )
