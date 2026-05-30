"""Tasks bootstrap and scheduler entrypoint.

Provides a single start_scheduler() used by app startup to initialize all
periodic jobs owned by this service. Individual task modules (e.g.,
report_health) define their jobs and expose a register_jobs(scheduler) hook.
"""

from app.core.logging import get_logger
from app.core.scheduler import scheduler
from app.core.scheduler_lock import acquire_scheduler_lock
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .health.report_health import register_jobs as _register_health_jobs
from .inventory import register_jobs as _register_inventory_jobs

logger = get_logger("herald.tasks")


def _register_all_jobs(sched: AsyncIOScheduler) -> None:
    # Add jobs from each task module here
    _register_health_jobs(sched, immediate_first_run=True)
    _register_inventory_jobs(sched, immediate_first_run=True)


def start_scheduler() -> None:
    """Acquire the scheduler lock, register all jobs, and start the scheduler.

    Safe to call multiple times; only the lock-owning process will start.
    """
    if scheduler.running:
        return

    if not acquire_scheduler_lock():
        logger.info("Another worker owns scheduler lock; skipping start")
        return

    logger.info("Acquired scheduler lock; starting tasks scheduler")
    _register_all_jobs(scheduler)
    scheduler.start()
