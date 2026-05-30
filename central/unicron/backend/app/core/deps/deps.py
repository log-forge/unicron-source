import re
from typing import Any
from urllib.parse import unquote

import socketio
from app.core.logging import get_logger
from fastapi import Header, HTTPException, Request, status

logger = get_logger(__name__)


def ensure_client_cert(request: Request):
    """Ensure an mTLS client cert was validated upstream.

    Accept if either the PEM header or the INFO header is present, since some
    deployments may omit the PEM due to header-size limits.
    """
    pem = request.headers.get("x-forwarded-tls-client-cert")
    info = request.headers.get("x-forwarded-tls-client-cert-info")
    if not pem and not info:
        # log a small sample of headers (safe)
        sample = {k.lower(): (v[:80] + "…") if len(v) > 80 else v for k, v in list(request.headers.items())[:20]}
        logger.error("Client certificate missing for endpoint. seen_headers=%s", sample)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client certificate required for this endpoint",
        )


def get_socketio_server(request: Request) -> "socketio.AsyncServer":
    sio = getattr(request.app.state, "sio", None)
    if sio is None:
        raise RuntimeError("Socket.IO not initialized; run with backend.app.main:asgi_app")
    return sio


def require_bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return token
