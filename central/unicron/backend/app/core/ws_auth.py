"""Browser WebSocket authentication helper.

Validates Better Auth cookies on WebSocket handshake for legacy browser-facing
endpoints (container broadcast, stats, terminal, logs, file browser).

This module is NOT used for agent WebSocket connections, which authenticate
via mTLS/token/IP-check in ws_handler.py.
"""

from typing import Optional
from urllib.parse import urlsplit

from fastapi import WebSocket

from app.core.logging import get_logger
from app.core.origin_policy import is_socket_origin_allowed
from app.utils.central_auth_client import fetch_local_admin_session_from_cookie

logger = get_logger("core.ws_auth")

def _first_csv_token(value: str | None) -> str:
    return (value or "").split(",")[0].strip()


def _normalize_socket_scheme(value: str | None) -> str:
    scheme = _first_csv_token(value).lower()
    if scheme == "wss":
        return "https"
    if scheme == "ws":
        return "http"
    if scheme in {"http", "https"}:
        return scheme
    return ""


def _socket_port_for_scheme(scheme: str, port: int | None) -> str:
    if port is not None:
        return str(port)
    if scheme == "https":
        return "443"
    return "80"


def is_browser_ws_origin_allowed(websocket: WebSocket) -> bool:
    """Enforce browser WebSocket origin policy using the same policy as Socket.IO.

    Browser-facing Starlette WebSockets do not expose a WSGI environ, so we
    build a minimal mapping from request headers + URL components.
    """
    origin = websocket.headers.get("origin")
    if not origin:
        return True

    # Prefer explicit proxy proto. If absent, use browser Origin scheme before
    # backend-local websocket scheme (which may be "ws" behind TLS terminator).
    origin_scheme = _normalize_socket_scheme(urlsplit(origin).scheme)
    scheme = (
        _normalize_socket_scheme(websocket.headers.get("x-forwarded-proto"))
        or origin_scheme
        or _normalize_socket_scheme(websocket.url.scheme)
        or "https"
    )
    host = (
        _first_csv_token(websocket.headers.get("x-forwarded-host"))
        or _first_csv_token(websocket.headers.get("host"))
        or websocket.url.netloc
        or ""
    )
    forwarded_port_raw = _first_csv_token(websocket.headers.get("x-forwarded-port"))
    forwarded_port = int(forwarded_port_raw) if forwarded_port_raw.isdigit() else None

    environ = {
        "HTTP_ORIGIN": origin,
        "HTTP_X_FORWARDED_PROTO": websocket.headers.get("x-forwarded-proto", ""),
        "HTTP_X_FORWARDED_HOST": websocket.headers.get("x-forwarded-host", ""),
        "HTTP_HOST": websocket.headers.get("host", ""),
        "wsgi.url_scheme": scheme,
        "SERVER_NAME": websocket.url.hostname or "",
        "SERVER_PORT": _socket_port_for_scheme(scheme, forwarded_port or websocket.url.port),
    }
    if host:
        environ["HTTP_HOST"] = host
    return is_socket_origin_allowed(origin, environ)


async def authenticate_browser_ws(websocket: WebSocket) -> Optional[str]:
    """Authenticate a legacy browser WebSocket connection via Better Auth cookie.

    This function is intended for browser-facing WebSocket endpoints only.
    Agent WebSocket connections use a separate mTLS/token authentication flow.

    Args:
        websocket: The incoming WebSocket connection (before ``accept()``).

    Returns:
        The authenticated user's ID string, or ``None`` if authentication
        fails for any reason.
    """
    cookie_header = websocket.headers.get("cookie", "")
    if not cookie_header:
        return None

    try:
        session = await fetch_local_admin_session_from_cookie(cookie_header)
        if session and session.user:
            return session.user_id
    except Exception as exc:
        logger.debug("Browser WS auth validation failed: %s", exc)

    return None
