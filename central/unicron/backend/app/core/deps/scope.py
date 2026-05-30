from app.core.access.role_resolver import (
    ActorContext,
    max_role,
    meets_min_role,
    resolve_container_role,
    resolve_group_role,
)
from app.core.database import get_session
from app.core.deps.central_auth import require_admin_user
from app.models.container.crud.container_crud import get_container_by_key
from app.utils.central_auth_client import LocalAdminSession
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession


async def get_actor_context(
    session: LocalAdminSession = Depends(require_admin_user),
) -> ActorContext:
    return ActorContext(
        user_id=session.user_id,
        team_ids=[],
        org_role="admin",
    )


async def require_group_access(
    group_id: str,
    min_role: str,
    actor: ActorContext = Depends(get_actor_context),
    session: AsyncSession = Depends(get_session),
) -> str:
    return await enforce_group_access(session, actor, group_id, min_role)


async def enforce_group_access(
    session: AsyncSession,
    actor: ActorContext,
    group_id: str,
    min_role: str,
) -> str:
    if actor.org_role in {"owner", "admin"}:
        return "admin"
    role = await resolve_group_role(session, actor, group_id)
    if not meets_min_role(role, min_role):
        raise HTTPException(status_code=403, detail="Insufficient scope")
    if role is None:
        raise HTTPException(status_code=403, detail="Insufficient scope")
    return role


async def require_container_access(
    container_key: str,
    min_role: str,
    actor: ActorContext = Depends(get_actor_context),
    session: AsyncSession = Depends(get_session),
) -> str:
    return await enforce_container_access(session, actor, container_key, min_role)


async def enforce_container_access(
    session: AsyncSession,
    actor: ActorContext,
    container_key: str,
    min_role: str,
) -> str:
    if actor.org_role in {"owner", "admin"}:
        return "admin"
    container = await get_container_by_key(session, container_key)
    if not container:
        raise HTTPException(status_code=404, detail="Container not found")
    container_role = await resolve_container_role(session, actor, container.container_key)
    group_role = None
    if container.group_id:
        group_role = await resolve_group_role(session, actor, container.group_id)
    effective = max_role(container_role, group_role)
    if not meets_min_role(effective, min_role):
        raise HTTPException(status_code=403, detail="Insufficient scope")
    if effective is None:
        raise HTTPException(status_code=403, detail="Insufficient scope")
    return effective


__all__ = [
    "get_actor_context",
    "require_group_access",
    "enforce_group_access",
    "require_container_access",
    "enforce_container_access",
]
