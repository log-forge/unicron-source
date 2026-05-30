from app.core.logging import get_logger
from app.utils.central_auth_client import LocalAdminSession, fetch_local_admin_session_from_cookie
from fastapi import Depends, HTTPException, Request, status

logger = get_logger("backend.deps.central_auth")


async def get_central_auth_session(request: Request) -> LocalAdminSession:
    cookie_header = request.headers.get("cookie")
    if not cookie_header:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    try:
        session = await fetch_local_admin_session_from_cookie(cookie_header)
    except Exception as exc:
        logger.warning("Failed to fetch Central Auth session: %s", exc)
        session = None

    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return session


async def require_admin_user(
    session: LocalAdminSession = Depends(get_central_auth_session),
) -> LocalAdminSession:
    if not session.user or not session.isAdmin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated")
    return session


__all__ = ["get_central_auth_session", "require_admin_user"]
