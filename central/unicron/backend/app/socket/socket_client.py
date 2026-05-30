from typing import Iterable, Optional

import socketio
from app.core.config import settings
from app.core.origin_policy import is_socket_origin_allowed

global _SERVER
_SERVER: Optional[socketio.AsyncServer] = None


def build_socket_server(
    *,
    cors_allowed_origins: Optional[Iterable[str]] = None,
    redis_url: str | None = None,
) -> socketio.AsyncServer:
    mgr = None
    if redis_url:
        mgr = socketio.AsyncRedisManager(redis_url)
    resolved_cors_origins = None
    if cors_allowed_origins is not None:
        resolved_cors_origins = list(cors_allowed_origins)
    else:
        resolved_cors_origins = is_socket_origin_allowed
    sio = socketio.AsyncServer(
        async_mode="asgi",
        # Delegate CORS decisions to the live HTTP/Socket.IO origin policy.
        cors_allowed_origins=resolved_cors_origins,
        client_manager=mgr,
        async_handlers=True,
    )

    # set the module-level server
    global _SERVER
    _SERVER = sio
    return _SERVER


def bootstrap_socketio(allow_origins: Optional[Iterable[str]]):
    redis_url = settings.SOCKETIO_REDIS_URL
    return build_socket_server(cors_allowed_origins=allow_origins, redis_url=redis_url)


def get_socket_server() -> Optional[socketio.AsyncServer]:
    """Retrieve the globally stored socket server, if available."""
    return _SERVER


__all__ = ["build_socket_server", "bootstrap_socketio", "get_socket_server"]
