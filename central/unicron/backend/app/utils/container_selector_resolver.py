from __future__ import annotations

from typing import Optional

from app.base_schemas import ContainerSelector
from app.services.container_identity import build_container_key
from sqlalchemy.ext.asyncio import AsyncSession


async def resolve_container_selector_to_key(
    session: AsyncSession, selector: ContainerSelector
) -> ContainerSelector:
    """
    Enforces that downstream telemetry queries are always scoped by `container_key`.
    """
    _ = session
    selector.ensure_container_key()
    return selector

async def resolve_container_key(session: AsyncSession, *, container_key: Optional[str] = None) -> str:
    selector = ContainerSelector(container_key=container_key)
    await resolve_container_selector_to_key(session, selector)
    if not selector.container_key:
        raise ValueError("container_key is required")
    return selector.container_key


__all__ = ["resolve_container_key", "resolve_container_selector_to_key", "build_container_key"]
