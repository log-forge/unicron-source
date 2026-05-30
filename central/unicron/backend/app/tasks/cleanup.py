"""Background tasks for cleaning up stale Herald tokens.

This module defines an asynchronous cleanup job that periodically scans the
database for Herald tokens that have remained in a 'pending' state beyond the
configured expiry window and marks them as 'expired'. It also exposes a small
helper to start the asyncio scheduler that drives the periodic job.

Constants:
- CLEANUP_INTERVAL_SECONDS: how often (in seconds) the cleanup job runs.
- TOKEN_EXPIRY_SECONDS: token age (in seconds) after which a 'pending' token is
    considered stale and will be marked as 'expired'.

Behaviour:
- cleanup_stale_tokens() will obtain a database session, compute the cutoff
    time, select pending tokens older than that cutoff, and mark each as expired
    via update_herald_token_status().
- start_cleanup_scheduler() ensures the scheduler is started once; it is safe
    to call multiple times (the scheduler will not be restarted if already running).
"""

from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.database import get_session
from app.models.herald.crud.herald_token_crud import update_herald_token_status
from app.models.herald.herald_token_model import Herald_Token
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import select

CLEANUP_INTERVAL_SECONDS = settings.CLEANUP_INTERVAL_SECONDS or 3600  # 1 hour
TOKEN_EXPIRY_SECONDS = settings.TOKEN_EXPIRY_SECONDS or 18000  # 5 hours


async def cleanup_stale_tokens():
    """Scan for and expire stale Herald tokens.

    This coroutine retrieves a database session from get_session(), computes an
    expiry cutoff based on TOKEN_EXPIRY_SECONDS, queries for Herald_Token rows
    that are still 'pending' and older than the cutoff, and updates each token's
    status to 'expired' via update_herald_token_status(session, token.id, "expired").

    Notes:
    - The function is intended to be scheduled and run periodically by the
        AsyncIOScheduler configured in this module.
    - It uses timezone-aware UTC datetimes to compare against Herald_Token.created_at.
    - The loop breaks after a single session iteration to avoid opening multiple
        sessions in a single run; the scheduler will call this coroutine repeatedly.
    """
    async for session in get_session():
        expiry_time = datetime.now(timezone.utc) - timedelta(seconds=TOKEN_EXPIRY_SECONDS)
        stmt = select(Herald_Token).where(Herald_Token.status == "pending", Herald_Token.created_at < expiry_time)
        results = await session.execute(stmt)
        tokens = results.scalars().all()
        for token in tokens:
            await update_herald_token_status(session, token.id, "expired")
        break


def register_jobs(sched: AsyncIOScheduler) -> None:
    """Register all periodic jobs for this service.

    Only call from the lock-owning process before starting the scheduler.
    """
    sched.add_job(
        cleanup_stale_tokens,
        "interval",
        seconds=CLEANUP_INTERVAL_SECONDS,
        id="cleanup_stale_tokens",
        max_instances=1,
        replace_existing=True,
    )
