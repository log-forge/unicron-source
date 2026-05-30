from datetime import datetime, timezone
from math import ceil

from app.core.config import settings
from app.core.logging import get_logger
from app.core.scheduler import scheduler
from app.socket.client import get_socket_client
from app.utils import parse_response, send_mtls_request
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from unicron_shared import HeraldHealthRequest, HeraldHealthResponse, HeraldStatus

# Use config.py settings for all paths
PING_INTERVAL = settings.PING_INTERVAL
# avoid synchronized heartbeats across many agents. Use a default of 20%.
JITTER_PERCENT = 0.2
# Compute jitter seconds (at least 1 second when interval >= 1s)
JITTER_SECONDS = max(1, ceil(PING_INTERVAL * JITTER_PERCENT)) if PING_INTERVAL >= 1 else 0

logger = get_logger("herald.tasks.health")


async def health_ping():
    try:
        response = await send_mtls_request(
            "POST",
            "/herald/health",
            json=HeraldHealthRequest(
                herald_name=settings.HERALD_NAME,
                status=HeraldStatus.healthy,
                timestamp=datetime.now(timezone.utc).isoformat(),
                message="Herald is alive",
            ),
            json_model=HeraldHealthRequest,
            timeout=10.0,
        )
        if response is None:
            logger.warning("health_ping: no response object returned from POST to /herald/health")
        else:
            parsed = parse_response(response, HeraldHealthResponse)
            if parsed is None:
                logger.info(
                    "health_ping: response did not validate as HeraldHealthResponse or had error; raw status=%s, body=%s",
                    getattr(response, "status_code", getattr(response, "status", "?")),
                    getattr(response, "text", "<no-body>"),
                )
    except Exception as e:
        # Use exception to capture stack trace in logs for easier debugging
        logger.error("health_ping exception: %s", e, exc_info=True)


def register_jobs(sched: AsyncIOScheduler, *, immediate_first_run: bool = False) -> None:
    """Register all periodic jobs for this service.

    Only call from the lock-owning process before starting the scheduler.
    """
    if immediate_first_run:
        sched.add_job(
            health_ping,
            "interval",
            seconds=PING_INTERVAL,
            id="health_ping",
            max_instances=1,
            replace_existing=True,
            jitter=JITTER_SECONDS,
            next_run_time=datetime.now(timezone.utc),
        )
    else:
        sched.add_job(
            health_ping,
            "interval",
            seconds=PING_INTERVAL,
            id="health_ping",
            max_instances=1,
            replace_existing=True,
            jitter=JITTER_SECONDS,
        )


async def _socket_beat():
    """Emit a lightweight heartbeat over the control socket to refresh last_seen."""
    sio = get_socket_client()
    try:
        await sio.call("beat", {}, timeout=5)
    except Exception as e:
        logger.debug(f"socket beat error: {e}")


def start_socket_heartbeat():
    """Start the scheduled socket heartbeat after the control socket is connected.

    Safe to call multiple times; it will replace the existing job if present.
    """
    if not scheduler.running:
        # Scheduler isn't running in this worker; nothing to do.
        return
    try:
        scheduler.add_job(
            _socket_beat,
            "interval",
            seconds=PING_INTERVAL,
            id="socket_heartbeat",
            max_instances=1,
            replace_existing=True,
            jitter=JITTER_SECONDS,
        )
    except Exception:
        pass


def stop_socket_heartbeat():
    """Stop the scheduled socket heartbeat job and clear the client reference."""
    if scheduler.running:
        try:
            scheduler.remove_job("socket_heartbeat")
        except Exception:
            pass
