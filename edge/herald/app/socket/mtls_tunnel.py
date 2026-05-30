"""Control channel client for Herald (Socket.IO over mTLS).

Opens a background reconnecting control channel to the central backend via Traefik mTLS.
"""

import asyncio
from typing import Optional
from urllib.parse import urlparse

from app.core.config import settings
from app.core.logging import get_logger
from app.socket.client import get_socket_client
from app.socket.validation import inspect_ack
from app.tasks.health.report_health import start_socket_heartbeat, stop_socket_heartbeat

from unicron_shared import PongData

CENTRAL_MTLS_URL = settings.CENTRAL_MTLS_URL
SIO_PATH = settings.SIO_PATH

logger = get_logger(__name__)


async def open_control_channel(url: str = CENTRAL_MTLS_URL, path: str = SIO_PATH):
    logger.info(f"Opening Herald control channel to {url} with path {path}")
    sio = get_socket_client()

    # Retry only until first successful connection; thereafter rely on python-socketio's internal auto-reconnect logic.
    backoff = 1
    connected = False
    while not connected:
        try:
            await sio.connect(url, socketio_path=path, transports=["websocket"])
            connected = True
            # Perform an initial ping after first successful connect
            try:
                res = await sio.call("ping", {}, timeout=5)
                ack = inspect_ack(res, ok_data_model=PongData, log_context="control ping", _logger=logger)
                if ack[0]:
                    logger.info("control channel connected; sid=%s", getattr(sio, "sid", "<unknown>"))
                    # Now that the mTLS tunnel is up, start the socket heartbeat task
                    start_socket_heartbeat()
            except Exception as e:
                logger.warning("control ping failed: %s", e, exc_info=True)
        except Exception as e:
            logger.warning("connect error (%s): %s; retry in %ss", type(e).__name__, e, backoff, exc_info=True)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    # Block this coroutine (task) so the process stays alive; this will
    # return when disconnect() is called or the loop is stopped.
    await sio.wait()


async def stop_control_channel(task: Optional[asyncio.Task]):
    # Stop the heartbeat if it's running
    try:
        stop_socket_heartbeat()
    except Exception:
        pass

    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
