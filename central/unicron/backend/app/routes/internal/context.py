"""Internal context API for local admin access.

These endpoints allow alert-engine to query local admin visibility without
direct database access.

Security: Protected by X-Internal-Secret header validation.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.internal_secret import verify_internal_secret_header
from app.core.access.role_resolver import (
    ActorContext,
    list_accessible_container_keys,
)
from app.models.container.container_model import Container
from app.models.group.group_model import Group
from app.models.herald.herald_model import Herald

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/context", tags=["internal"])

# ---- Request/Response Schemas ----


class AccessCheckRequest(BaseModel):
    """Request to check user's access to a container."""

    user_id: str
    container_key: str
    required_role: str  # "read_only" | "operator" | "admin"


class AccessCheckResponse(BaseModel):
    """Response from access check."""

    allowed: bool
    actual_role: Optional[str] = None
    reason: Optional[str] = None


class ContainersRequest(BaseModel):
    """Request to get accessible containers for user."""

    user_id: str
    organization_id: str
    scope_type: str  # "container" | "group" | "herald"


class ContainersResponse(BaseModel):
    """Response with accessible container IDs."""

    container_keys: List[str] = []
    group_ids: List[str] = []
    herald_ids: List[str] = []


async def _resolve_container_identifier(
    session: AsyncSession,
    container_identifier: str,
) -> str:
    """
    Resolve a container identifier into canonical container_key.
    """
    value = (container_identifier or "").strip()
    return value


# ---- Security Dependency ----


async def verify_internal_secret(
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
) -> None:
    """Verify the internal API secret header.

    Fail-closed: rejects requests when no secret is configured in production.
    In development (ENVIRONMENT != 'production'), allows silently (warning was logged at startup).
    """
    verify_internal_secret_header(x_internal_secret)


# ---- Endpoints ----


@router.post("/access", response_model=AccessCheckResponse)
async def check_access(
    request: AccessCheckRequest,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_internal_secret),
) -> AccessCheckResponse:
    """Check if the local admin has required access to a container."""
    resolved_container_key = await _resolve_container_identifier(session, request.container_key)
    result = await session.execute(
        select(Container.container_key)
        .join(Herald, getattr(Container, "herald_id") == getattr(Herald, "id"))
        .where(
            Container.container_key == resolved_container_key,
            getattr(Herald, "unregistered") == False,  # noqa: E712
        )
    )
    if result.scalar_one_or_none() is None:
        return AccessCheckResponse(
            allowed=False,
            actual_role=None,
            reason="Container not found",
        )

    return AccessCheckResponse(allowed=True, actual_role="admin", reason=None)


@router.post("/containers", response_model=ContainersResponse)
async def get_accessible_containers(
    request: ContainersRequest,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_internal_secret),
) -> ContainersResponse:
    """Get containers/groups/heralds visible to the local admin."""
    actor = ActorContext(
        user_id=request.user_id,
        team_ids=[],
        org_role="admin",
    )

    response = ContainersResponse()

    if request.scope_type == "container":
        container_keys = await list_accessible_container_keys(session, actor)
        response.container_keys = container_keys

    elif request.scope_type == "group":
        stmt = select(Group.id)
        result = await session.execute(stmt)
        response.group_ids = list(result.scalars().all())

    elif request.scope_type == "herald":
        stmt = select(Herald.id).where(getattr(Herald, "unregistered") == False)  # noqa: E712
        result = await session.execute(stmt)
        response.herald_ids = [str(value) for value in result.scalars().all() if value]

    return response


__all__ = ["router"]
