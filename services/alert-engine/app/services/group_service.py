"""Container group management service.

Implements business logic for group operations:
- Mutual exclusivity: container can only be in one group
- Auto-dissolve: group deleted when fewer than 2 members
- Merge on collision: creating group with existing name merges containers

Uses raw SQL to avoid SQLModel table registration conflicts with Central.
Central owns the Group and Container models - alert-engine writes via SQL.
"""

from datetime import datetime, timezone
from typing import List, Optional, Tuple
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.services.container_service import ContainerReadModel, GroupReadModel

logger = get_logger("alert-engine.services.group_service")


class GroupNotFoundError(Exception):
    """Raised when a group is not found."""
    pass


class GroupValidationError(Exception):
    """Raised when group operation validation fails."""
    pass


class GroupService:
    """Service for container group management.

    Uses raw SQL to avoid SQLModel conflicts with Central's model definitions.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_group(self, group_id: str) -> Optional[GroupReadModel]:
        """Get group by ID."""
        query = text('SELECT id, name, created_at FROM "group" WHERE id = :group_id')
        result = await self.session.execute(query, {"group_id": group_id})
        row = result.fetchone()
        return GroupReadModel(row) if row else None

    async def get_group_by_name(self, name: str) -> Optional[GroupReadModel]:
        """Get group by name."""
        normalized = (name or "").strip()
        if not normalized:
            return None

        query = text('SELECT id, name, created_at FROM "group" WHERE name = :name')
        result = await self.session.execute(query, {"name": normalized})
        row = result.fetchone()
        return GroupReadModel(row) if row else None

    async def get_group_members(self, group_id: str) -> List[ContainerReadModel]:
        """Get all containers in a group."""
        query = text("""
            SELECT id, name, container_key, status, image, herald_id, group_id,
                   labels, started_at, cpu_limit, memory_limit_bytes
            FROM container
            WHERE group_id = :group_id
        """)
        result = await self.session.execute(query, {"group_id": group_id})
        rows = result.fetchall()
        return [ContainerReadModel(row) for row in rows]

    async def get_group_member_count(self, group_id: str) -> int:
        """Get count of containers in a group."""
        query = text("SELECT COUNT(*) FROM container WHERE group_id = :group_id")
        result = await self.session.execute(query, {"group_id": group_id})
        return result.scalar() or 0

    async def create_group(
        self,
        name: str,
        container_ids: List[str],
    ) -> Tuple[GroupReadModel, bool]:
        """
        Create a new group or merge into existing.

        Args:
            name: Group name
            container_ids: Canonical container keys to add (minimum 2)

        Returns:
            Tuple of (group, created) where created is False if merged

        Raises:
            GroupValidationError: If validation fails
        """
        normalized_name = (name or "").strip()
        if not normalized_name:
            raise GroupValidationError("Group name is required")

        if len(container_ids) < 2:
            raise GroupValidationError("Group requires at least 2 containers")

        # Check for existing group with same name (merge case)
        existing = await self.get_group_by_name(normalized_name)

        if existing:
            # Merge: add containers to existing group
            await self._add_containers_to_group(existing.id, container_ids)
            logger.info("Merged %d containers into existing group %s", len(container_ids), existing.id)
            # Re-fetch to get updated state
            updated = await self.get_group(existing.id)
            await self.session.commit()
            return updated, False

        # Create new group using raw SQL INSERT
        group_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc)

        insert_query = text('''
            INSERT INTO "group" (id, name, created_at)
            VALUES (:id, :name, :created_at)
        ''')
        await self.session.execute(insert_query, {
            "id": group_id,
            "name": normalized_name,
            "created_at": created_at,
        })

        # Add containers to new group
        await self._add_containers_to_group(group_id, container_ids)

        await self.session.commit()

        # Fetch the created group
        group = await self.get_group(group_id)
        logger.info("Created group %s with %d containers", group_id, len(container_ids))
        return group, True

    async def update_group(
        self,
        group_id: str,
        name: Optional[str] = None,
        add_container_ids: Optional[List[str]] = None,
        remove_container_ids: Optional[List[str]] = None,
    ) -> GroupReadModel:
        """
        Update a group's name and/or membership.

        Args:
            group_id: Group ID to update
            name: New name (if changing)
            add_container_ids: Canonical container keys to add
            remove_container_ids: Canonical container keys to remove

        Returns:
            Updated group

        Raises:
            GroupNotFoundError: If group doesn't exist
            GroupValidationError: If update would leave group with <2 members
        """
        group = await self.get_group(group_id)
        if not group:
            raise GroupNotFoundError(f"Group {group_id} not found")

        # Update name if provided
        if name is not None:
            normalized = name.strip()
            if normalized:
                update_query = text('UPDATE "group" SET name = :name WHERE id = :group_id')
                await self.session.execute(update_query, {"name": normalized, "group_id": group_id})

        # Remove containers first
        if remove_container_ids:
            await self._remove_containers_from_group(group_id, remove_container_ids)

        # Add containers
        if add_container_ids:
            await self._add_containers_to_group(group_id, add_container_ids)

        # Check member count after modifications
        member_count = await self.get_group_member_count(group_id)

        if member_count < 2:
            # Auto-dissolve: delete group
            logger.info("Auto-dissolving group %s (only %d members)", group_id, member_count)
            await self._dissolve_group(group_id)
            await self.session.commit()
            raise GroupValidationError("Group dissolved: fewer than 2 members remaining")

        await self.session.commit()
        return await self.get_group(group_id)

    async def delete_group(self, group_id: str) -> bool:
        """
        Delete a group and clear container membership.

        Args:
            group_id: Group ID to delete

        Returns:
            True if deleted, False if not found
        """
        group = await self.get_group(group_id)
        if not group:
            return False

        await self._dissolve_group(group_id)
        await self.session.commit()

        logger.info("Deleted group %s", group_id)
        return True

    async def _add_containers_to_group(
        self,
        group_id: str,
        container_ids: List[str],
    ) -> int:
        """
        Add containers to a group, enforcing mutual exclusivity.

        Returns count of containers added.
        """
        if not container_ids:
            return 0

        # Update containers to belong to this group using raw SQL
        # This automatically removes them from any previous group (mutual exclusivity)
        placeholders = ", ".join([f":id_{i}" for i in range(len(container_ids))])
        query = text(f"""
            UPDATE container
            SET group_id = :group_id
            WHERE container_key IN ({placeholders})
        """)
        params = {"group_id": group_id}
        params.update({f"id_{i}": cid for i, cid in enumerate(container_ids)})
        result = await self.session.execute(query, params)
        return result.rowcount

    async def _remove_containers_from_group(
        self,
        group_id: str,
        container_ids: List[str],
    ) -> int:
        """Remove containers from a group."""
        if not container_ids:
            return 0

        placeholders = ", ".join([f":id_{i}" for i in range(len(container_ids))])
        query = text(f"""
            UPDATE container
            SET group_id = NULL
            WHERE container_key IN ({placeholders})
              AND group_id = :group_id
        """)
        params = {"group_id": group_id}
        params.update({f"id_{i}": cid for i, cid in enumerate(container_ids)})
        result = await self.session.execute(query, params)
        return result.rowcount

    async def _dissolve_group(self, group_id: str) -> None:
        """Remove group and clear all container memberships."""
        # Clear container memberships
        clear_query = text("UPDATE container SET group_id = NULL WHERE group_id = :group_id")
        await self.session.execute(clear_query, {"group_id": group_id})

        # Delete group
        delete_query = text('DELETE FROM "group" WHERE id = :group_id')
        await self.session.execute(delete_query, {"group_id": group_id})


__all__ = [
    "GroupService",
    "GroupNotFoundError",
    "GroupValidationError",
]
