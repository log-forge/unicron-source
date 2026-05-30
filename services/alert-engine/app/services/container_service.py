"""Container data access service for alert-engine.

Queries container inventory from the shared PostgreSQL database
(populated by Herald via Central's inventory ingest endpoint). Uses lightweight
read-only data classes to avoid conflicts with Central's SQLModel definitions.

NOTE: We define read-only data classes here because:
1. Alert-engine connects to same PostgreSQL as Central
2. Tables already exist (created by Central's alembic migrations)
3. We only need to READ container/group data, not write
4. Using raw SQL with text() avoids SQLModel registration conflicts
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger("alert-engine.services.container_service")


class ContainerReadModel:
    """Lightweight container data class for read operations.

    Not a SQLModel - just a data container to avoid model registration conflicts.
    """

    def __init__(self, row: Any):
        self.id: str = row.id
        self.name: str = row.name
        self.container_key: str = (
            getattr(row, "container_key", None)
            or getattr(row, "container_id", None)
            or ""
        )
        # Backward-compatible alias for older call sites.
        self.container_id: str = self.container_key
        self.status: Optional[str] = row.status
        self.image: Optional[str] = row.image
        self.herald_id: Optional[str] = row.herald_id
        self.group_id: Optional[str] = row.group_id
        self.labels: Dict[str, str] = row.labels or {}
        self.started_at: Optional[datetime] = row.started_at
        self.cpu_limit: Optional[float] = getattr(row, "cpu_limit", None)
        self.memory_limit_bytes: Optional[int] = getattr(row, "memory_limit_bytes", None)


class GroupReadModel:
    """Lightweight group data class for read operations."""

    def __init__(self, row: Any):
        self.id: str = row.id
        self.name: Optional[str] = row.name
        self.created_at: Optional[datetime] = row.created_at


class ContainerService:
    """Service for container data operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_containers(
        self,
        accessible_container_ids: Optional[List[str]] = None,
    ) -> List[ContainerReadModel]:
        """
        List containers, optionally filtered by accessible IDs.

        Args:
            accessible_container_ids: If provided, filter to only these canonical
                                     container keys (host_id:container_name).
                                     If None, return all containers (admin case).

        Returns:
            List of ContainerReadModel objects.
        """
        # Build query using text() for explicit table name
        base_query = """
            SELECT id, name, container_key, status, image, herald_id, group_id,
                   labels, started_at, cpu_limit, memory_limit_bytes
            FROM container
        """

        if accessible_container_ids is not None:
            if not accessible_container_ids:
                # Empty list means no access - return empty
                return []
            # Parameterized query for safety
            placeholders = ", ".join([f":id_{i}" for i in range(len(accessible_container_ids))])
            query = text(f"{base_query} WHERE container_key IN ({placeholders}) ORDER BY name ASC")
            params = {f"id_{i}": cid for i, cid in enumerate(accessible_container_ids)}
            result = await self.session.execute(query, params)
        else:
            query = text(f"{base_query} ORDER BY name ASC")
            result = await self.session.execute(query)

        rows = result.fetchall()
        return [ContainerReadModel(row) for row in rows]

    async def list_groups(
        self,
        group_ids: Optional[List[str]] = None,
    ) -> List[GroupReadModel]:
        """
        List groups, optionally filtered by IDs.

        Args:
            group_ids: If provided, filter to only these group IDs.
                      If None, return all groups.

        Returns:
            List of GroupReadModel objects.
        """
        # Quote "group" - it's a reserved SQL keyword
        base_query = 'SELECT id, name, created_at FROM "group"'

        if group_ids is not None:
            if not group_ids:
                return []
            placeholders = ", ".join([f":id_{i}" for i in range(len(group_ids))])
            query = text(f"{base_query} WHERE id IN ({placeholders}) ORDER BY name ASC")
            params = {f"id_{i}": gid for i, gid in enumerate(group_ids)}
            result = await self.session.execute(query, params)
        else:
            query = text(f"{base_query} ORDER BY name ASC")
            result = await self.session.execute(query)

        rows = result.fetchall()
        return [GroupReadModel(row) for row in rows]

    async def list_groups_paginated(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[GroupReadModel], int]:
        """List groups using offset/limit pagination."""
        offset = max(0, int(offset))
        limit = max(1, int(limit))

        total_query = text('SELECT COUNT(*) FROM "group"')
        total_result = await self.session.execute(total_query)
        total = int(total_result.scalar() or 0)

        query = text("""
            SELECT id, name, created_at
            FROM "group"
            ORDER BY name ASC
            OFFSET :offset
            LIMIT :limit
        """)
        result = await self.session.execute(query, {"offset": offset, "limit": limit})
        rows = result.fetchall()
        return [GroupReadModel(row) for row in rows], total

    async def get_containers_by_group(
        self,
        group_id: str,
    ) -> List[ContainerReadModel]:
        """Get all containers belonging to a specific group."""
        query = text("""
            SELECT id, name, container_key, status, image, herald_id, group_id,
                   labels, started_at, cpu_limit, memory_limit_bytes
            FROM container
            WHERE group_id = :group_id
        """)
        result = await self.session.execute(query, {"group_id": group_id})
        rows = result.fetchall()
        return [ContainerReadModel(row) for row in rows]

    async def get_group_members_for_groups(
        self,
        group_ids: List[str],
    ) -> Dict[str, List[Tuple[str, str]]]:
        """Fetch members for multiple groups in one query.

        Returns:
            Mapping ``group_id -> [(host_id, container_name), ...]``.
        """
        if not group_ids:
            return {}

        placeholders = ", ".join([f":group_id_{i}" for i in range(len(group_ids))])
        query = text(f"""
            SELECT group_id, herald_id, name
            FROM container
            WHERE group_id IN ({placeholders})
            ORDER BY group_id ASC, name ASC
        """)
        params = {f"group_id_{i}": group_id for i, group_id in enumerate(group_ids)}
        result = await self.session.execute(query, params)
        rows = result.fetchall()

        members_by_group: Dict[str, List[Tuple[str, str]]] = {}
        for row in rows:
            gid = row.group_id
            if gid is None:
                continue
            members = members_by_group.setdefault(gid, [])
            members.append(((row.herald_id or "local"), row.name))
        return members_by_group


def build_container_identifier(container: ContainerReadModel) -> str:
    """Build frontend identifier string using canonical container key."""
    host_id = container.herald_id or "local"
    if container.container_key:
        return container.container_key
    return f"{host_id}:{container.name}"


__all__ = [
    "ContainerService",
    "ContainerReadModel",
    "GroupReadModel",
    "build_container_identifier",
]
