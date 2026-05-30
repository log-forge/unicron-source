"""Singleton Socket.IO AsyncClient for the Herald control channel.

Provides a lazy-initialized AsyncClient bound to an aiohttp session configured
with the Herald mTLS SSL context. Use get_control_client() anywhere you need
the socket instance; it will be created on first access.
"""

from typing import Optional

import aiohttp
import socketio
from app.utils.httpx_client import get_cached_ssl_context

_session: Optional[aiohttp.ClientSession] = None
_sio: Optional[socketio.AsyncClient] = None


def get_socket_client() -> socketio.AsyncClient:
    global _session, _sio
    if _sio is not None:
        return _sio

    # Build SSL and session once
    ssl_ctx = get_cached_ssl_context()
    # Only pass the SSL context if we actually have one to satisfy type checkers
    connector = aiohttp.TCPConnector(ssl=ssl_ctx) if ssl_ctx is not None else aiohttp.TCPConnector()
    _session = aiohttp.ClientSession(connector=connector)
    _sio = socketio.AsyncClient(
        http_session=_session,
        reconnection=True,
        reconnection_attempts=0,
        reconnection_delay=1,
        reconnection_delay_max=30,
        randomization_factor=0.5,
    )

    try:
        init_socket_handlers(_sio)
    except Exception:
        pass
    return _sio


async def close_socket_client():
    global _session, _sio
    if _sio is not None:
        try:
            await _sio.disconnect()
        except Exception:
            pass
    if _session is not None and not _session.closed:
        await _session.close()
    _sio = None
    _session = None


def init_socket_handlers(sio: socketio.AsyncClient) -> None:
    """Idempotently register application Socket.IO handlers onto `sio`.

    This function performs a local import of the app-specific registration to
    avoid circular imports when this module is imported early. It sets an
    attribute on the `sio` instance to ensure handlers are only registered
    once per client instance.
    """
    if getattr(sio, "_herald_events_registered", False):
        return

    # Local import prevents import-time circular dependencies.
    try:
        from app.socket.listeners import register_all_events

        register_all_events(sio)
        setattr(sio, "_herald_events_registered", True)
    except Exception:
        # Let callers handle/log failures; keep function safe to call.
        raise
