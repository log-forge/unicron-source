"""Authentication dependencies for notifier service.

Notifier validates browser sessions directly against Central Auth. This
service doesn't have its own user database.
"""

from typing import Optional

import httpx
from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("notifier.deps")


class UserContext(BaseModel):
    """Authenticated user context from Central session."""

    user_id: str
    email: str
    username: str | None = None
    display_name: str | None = None
    organization_id: str
    roles: list[str] = []


async def get_user_context(request: Request) -> Optional[UserContext]:
    """
    Validate session by calling Central Auth with the incoming cookie header.

    Returns None if authentication fails (no valid session).
    """
    cookie_header = request.headers.get("cookie")
    if not cookie_header:
        return None

    try:
        async with httpx.AsyncClient(
            base_url=settings.CENTRAL_AUTH_BASE_URL.rstrip("/"),
            verify=settings.CENTRAL_AUTH_VERIFY_TLS,
            timeout=10.0,
        ) as client:
            resp = await client.get(
                "/api/v1/profile",
                headers={"Cookie": cookie_header},
            )
            if resp.status_code != 200:
                logger.debug("Central Auth profile returned %d", resp.status_code)
                return None

            data = resp.json().get("data", {})
            user_data = data.get("user", {})
            user_id = str(user_data.get("id") or "")
            username = str(
                user_data.get("username")
                or user_data.get("displayUsername")
                or user_data.get("name")
                or ""
            )
            if not user_id:
                return None
            return UserContext(
                user_id=user_id,
                email=username,
                username=username,
                display_name=str(user_data.get("displayUsername") or user_data.get("name") or username),
                organization_id=str(data.get("deploymentId") or "local"),
                roles=["admin"],
            )
    except httpx.RequestError as e:
        logger.warning("Central Auth profile request failed: %s", e)
        return None
    except (KeyError, ValueError) as e:
        logger.warning("Central Auth profile response parse error: %s", e)
        return None


async def get_current_user(
    request: Request,
    user: Optional[UserContext] = Depends(get_user_context),
) -> UserContext:
    """
    Require authenticated user or raise 401.

    Use as a dependency in protected routes:
        @router.get("/channels")
        async def list_channels(user: UserContext = Depends(get_current_user)):
            ...
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


__all__ = ["UserContext", "get_user_context", "get_current_user"]
