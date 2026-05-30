from __future__ import annotations

from dataclasses import dataclass

from app.models.container.container_model import Container
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


def normalize_container_name(name: str) -> str:
    return str(name or "").strip().lstrip("/")


def build_container_key(herald_id: str, container_name: str) -> str:
    host_id = str(herald_id or "").strip()
    name = normalize_container_name(container_name)
    if not host_id or not name:
        raise ValueError("herald_id and container_name are required")
    return f"{host_id}:{name}"


@dataclass(frozen=True)
class ResolvedContainerIdentity:
    herald_id: str
    name: str
    container_key: str
    docker_container_id: str | None


class ContainerIdentityService:
    def build_identity(
        self,
        *,
        herald_id: str,
        name: str,
        docker_container_id: str | None = None,
    ) -> ResolvedContainerIdentity:
        normalized_name = normalize_container_name(name)
        normalized_docker_id = str(docker_container_id or "").strip() or None
        return ResolvedContainerIdentity(
            herald_id=str(herald_id or "").strip(),
            name=normalized_name,
            container_key=build_container_key(herald_id, normalized_name),
            docker_container_id=normalized_docker_id,
        )

    async def get_by_container_key(
        self,
        session: AsyncSession,
        container_key: str,
    ) -> Container | None:
        stmt = select(Container).where(getattr(Container, "container_key") == str(container_key or "").strip())
        return (await session.execute(stmt)).scalar_one_or_none()

    async def find_inventory_match(
        self,
        session: AsyncSession,
        *,
        herald_id: str,
        name: str,
        docker_container_id: str | None = None,
    ) -> tuple[ResolvedContainerIdentity, Container | None]:
        identity = self.build_identity(
            herald_id=herald_id,
            name=name,
            docker_container_id=docker_container_id,
        )

        existing = await self.get_by_container_key(session, identity.container_key)
        if existing is not None:
            return identity, existing

        if identity.docker_container_id:
            stmt = (
                select(Container)
                .where(getattr(Container, "herald_id") == identity.herald_id)
                .where(getattr(Container, "docker_container_id") == identity.docker_container_id)
                .limit(2)
            )
            matches = list((await session.execute(stmt)).scalars().all())
            if len(matches) == 1:
                return identity, matches[0]

        return identity, None


_SERVICE = ContainerIdentityService()


def get_container_identity_service() -> ContainerIdentityService:
    return _SERVICE


__all__ = [
    "ContainerIdentityService",
    "ResolvedContainerIdentity",
    "build_container_key",
    "get_container_identity_service",
    "normalize_container_name",
]
