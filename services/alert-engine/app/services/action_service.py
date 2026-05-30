"""
Action service for alert-engine.

Provides CRUD operations for rule actions that execute when alerts fire.
Actions are gated by the ActionGatekeeper for safety.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.action import RuleAction

logger = get_logger("alert-engine.services.action")


class ActionNotFoundError(Exception):
    """Raised when an action is not found in the database."""

    pass


class ActionService:
    """
    Service for rule action operations.

    Provides CRUD operations for actions attached to alert rules.
    Actions execute in order_index order when their rule fires.
    """

    async def create_action(
        self,
        session: AsyncSession,
        rule_id: str,
        action_type: str,
        action_config: Optional[Dict[str, Any]] = None,
        order_index: int = 0,
        enabled: bool = True,
    ) -> RuleAction:
        """
        Create a new action for a rule.

        Args:
            session: Async database session.
            rule_id: The rule ID to attach the action to.
            action_type: Type of action (restart, stop, start, kill, run_script, notify).
            action_config: Action-specific configuration.
            order_index: Execution order (lower = first).
            enabled: Whether the action is enabled.

        Returns:
            The created RuleAction instance.
        """
        now = datetime.now(timezone.utc)
        action = RuleAction(
            id=uuid.uuid4().hex,
            rule_id=rule_id,
            action_type=action_type,
            action_config=action_config or {},
            order_index=order_index,
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )
        session.add(action)
        await session.commit()
        await session.refresh(action)
        logger.info("Created action %s for rule %s", action.id, rule_id)
        return action

    async def get_action(
        self,
        session: AsyncSession,
        action_id: str,
    ) -> Optional[RuleAction]:
        """
        Get an action by ID.

        Args:
            session: Async database session.
            action_id: The action ID to look up.

        Returns:
            The RuleAction if found, None otherwise.
        """
        stmt = select(RuleAction).where(RuleAction.id == action_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_action_or_raise(
        self,
        session: AsyncSession,
        action_id: str,
    ) -> RuleAction:
        """
        Get an action by ID or raise ActionNotFoundError.

        Args:
            session: Async database session.
            action_id: The action ID to look up.

        Returns:
            The RuleAction if found.

        Raises:
            ActionNotFoundError: If the action is not found.
        """
        action = await self.get_action(session, action_id)
        if not action:
            raise ActionNotFoundError(f"Action {action_id} not found")
        return action

    async def get_actions_for_rule(
        self,
        session: AsyncSession,
        rule_id: str,
        enabled_only: bool = True,
    ) -> List[RuleAction]:
        """
        Get all actions for a rule, ordered by order_index.

        Args:
            session: Async database session.
            rule_id: The rule ID to get actions for.
            enabled_only: If True, only return enabled actions.

        Returns:
            List of RuleAction instances ordered by order_index.
        """
        stmt = select(RuleAction).where(RuleAction.rule_id == rule_id)

        if enabled_only:
            stmt = stmt.where(RuleAction.enabled == True)  # noqa: E712

        stmt = stmt.order_by(RuleAction.order_index.asc())
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_actions_for_rules(
        self,
        session: AsyncSession,
        rule_ids: List[str],
        enabled_only: bool = True,
    ) -> Dict[str, List[RuleAction]]:
        """
        Get actions for multiple rules in a single query.

        Args:
            session: Async database session.
            rule_ids: List of rule IDs to get actions for.
            enabled_only: If True, only return enabled actions.

        Returns:
            Dict mapping rule_id -> list of RuleAction instances.
        """
        if not rule_ids:
            return {}

        stmt = select(RuleAction).where(RuleAction.rule_id.in_(rule_ids))

        if enabled_only:
            stmt = stmt.where(RuleAction.enabled == True)  # noqa: E712

        stmt = stmt.order_by(RuleAction.order_index.asc())
        result = await session.execute(stmt)
        actions = list(result.scalars().all())

        # Group by rule_id
        actions_by_rule: Dict[str, List[RuleAction]] = {rid: [] for rid in rule_ids}
        for action in actions:
            if action.rule_id in actions_by_rule:
                actions_by_rule[action.rule_id].append(action)

        return actions_by_rule

    async def update_action(
        self,
        session: AsyncSession,
        action_id: str,
        *,
        action_type: Optional[str] = None,
        action_config: Optional[Dict[str, Any]] = None,
        order_index: Optional[int] = None,
        enabled: Optional[bool] = None,
    ) -> RuleAction:
        """
        Update an existing action.

        Args:
            session: Async database session.
            action_id: The action ID to update.
            action_type: New action type.
            action_config: New action configuration.
            order_index: New execution order.
            enabled: New enabled state.

        Returns:
            The updated RuleAction.

        Raises:
            ActionNotFoundError: If the action is not found.
        """
        action = await self.get_action_or_raise(session, action_id)

        if action_type is not None:
            action.action_type = action_type
        if action_config is not None:
            action.action_config = action_config
        if order_index is not None:
            action.order_index = order_index
        if enabled is not None:
            action.enabled = enabled

        action.updated_at = datetime.now(timezone.utc)

        session.add(action)
        await session.commit()
        await session.refresh(action)
        logger.info("Updated action %s", action_id)
        return action

    async def delete_action(
        self,
        session: AsyncSession,
        action_id: str,
    ) -> bool:
        """
        Delete an action.

        Args:
            session: Async database session.
            action_id: The action ID to delete.

        Returns:
            True if the action was deleted.

        Raises:
            ActionNotFoundError: If the action is not found.
        """
        action = await self.get_action_or_raise(session, action_id)
        await session.delete(action)
        await session.commit()
        logger.info("Deleted action %s", action_id)
        return True

    async def delete_actions_for_rule(
        self,
        session: AsyncSession,
        rule_id: str,
    ) -> int:
        """
        Delete all actions for a rule.

        Note: This is typically handled by CASCADE delete on the FK,
        but provided for explicit cleanup scenarios.

        Args:
            session: Async database session.
            rule_id: The rule ID to delete actions for.

        Returns:
            Number of actions deleted.
        """
        # Count before delete
        count_stmt = select(func.count()).where(RuleAction.rule_id == rule_id)
        count_result = await session.execute(count_stmt)
        count = count_result.scalar_one()

        # Delete all
        stmt = delete(RuleAction).where(RuleAction.rule_id == rule_id)
        await session.execute(stmt)
        await session.commit()

        logger.info("Deleted %d actions for rule %s", count, rule_id)
        return count

    async def sync_actions(
        self,
        session: AsyncSession,
        rule_id: str,
        actions: List[Dict[str, Any]],
    ) -> List[RuleAction]:
        """
        Replace all actions for a rule (delete existing, create new).

        This is useful for bulk update scenarios where the full list
        of actions is provided and should replace existing actions.

        Args:
            session: Async database session.
            rule_id: The rule ID to sync actions for.
            actions: List of action dicts with keys:
                - action_type: str
                - action_config: dict (optional)
                - order_index: int (optional, defaults to list index)
                - enabled: bool (optional, defaults to True)

        Returns:
            List of created RuleAction instances.
        """
        # Delete existing actions
        await self.delete_actions_for_rule(session, rule_id)

        # Create new actions
        created = []
        now = datetime.now(timezone.utc)

        for idx, action_data in enumerate(actions):
            action = RuleAction(
                id=uuid.uuid4().hex,
                rule_id=rule_id,
                action_type=action_data["action_type"],
                action_config=action_data.get("action_config", {}),
                order_index=action_data.get("order_index", idx),
                enabled=action_data.get("enabled", True),
                created_at=now,
                updated_at=now,
            )
            session.add(action)
            created.append(action)

        await session.commit()

        # Refresh all
        for action in created:
            await session.refresh(action)

        logger.info("Synced %d actions for rule %s", len(created), rule_id)
        return created


# Singleton instance
action_service = ActionService()

__all__ = ["ActionService", "ActionNotFoundError", "action_service"]
