from app.core.logging import get_logger
from app.core.scheduler_lock import acquire_scheduler_lock
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .cleanup import register_jobs as _register_cleanup_jobs
from .herald_health_monitor import register_jobs as _register_health_monitor_jobs

logger = get_logger("backend.tasks")


# Define the shared AsyncIOScheduler singleton here
_scheduler: AsyncIOScheduler = AsyncIOScheduler()
scheduler: AsyncIOScheduler = _scheduler


def _register_all_jobs(sched: AsyncIOScheduler) -> None:
    # Add jobs from each task module here
    _register_cleanup_jobs(sched)
    _register_health_monitor_jobs(sched)


def start_scheduler() -> None:
    """Acquire the scheduler lock, register all jobs, and start the scheduler.

    Safe to call multiple times; only the lock-owning process will start.
    """
    if _scheduler.running:
        return

    if not acquire_scheduler_lock():
        logger.info("Another worker owns scheduler lock; skipping start")
        return

    logger.info("Acquired scheduler lock; starting tasks scheduler")
    _register_all_jobs(_scheduler)
    _scheduler.start()
