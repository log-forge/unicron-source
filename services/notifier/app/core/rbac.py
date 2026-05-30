"""Local admin access helpers for notifier service."""

from typing import List

from fastapi import HTTPException, status

from app.core.deps import UserContext
from app.core.logging import get_logger

logger = get_logger("notifier.rbac")


async def check_container_access(user: UserContext, container_id: str) -> bool:
    """The authenticated local admin can access all containers."""
    return True


async def validate_container_access(
    user: UserContext, container_ids: List[str]
) -> None:
    """Validate local-admin access to the specified containers."""
    if not container_ids:
        return

    inaccessible: List[str] = [
        container_id
        for container_id in container_ids
        if not await check_container_access(user, container_id)
    ]

    if inaccessible:
        logger.warning(
            "User %s denied access to containers: %s",
            user.user_id,
            inaccessible,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied to containers: {', '.join(inaccessible)}",
        )


async def clear_access_cache() -> None:
    """Compatibility no-op; access is not cached in the single-admin model."""
    return None


__all__ = [
    "check_container_access",
    "validate_container_access",
    "clear_access_cache",
]
