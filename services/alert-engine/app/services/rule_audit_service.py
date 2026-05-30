"""
Service for rule audit logging and queries.

Provides methods to log rule operations and query the audit trail
with filters for rule, user, action, and time range.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rule_audit import RuleAuditAction, RuleAuditLog

logger = logging.getLogger(__name__)


class RuleAuditService:
    """Service for rule audit logging and queries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def log_rule_created(
        self,
        rule_id: str,
        rule_name: str,
        user_id: str,
        user_email: str,
        organization_id: str,
        rule_snapshot: Dict[str, Any],
    ) -> RuleAuditLog:
        """Log a rule creation."""
        log = RuleAuditLog(
            rule_id=rule_id,
            rule_name=rule_name,
            user_id=user_id,
            user_email=user_email,
            organization_id=organization_id,
            action=RuleAuditAction.CREATED,
            details=rule_snapshot,
        )
        self._session.add(log)
        await self._session.commit()
        await self._session.refresh(log)
        logger.info("Logged rule creation: rule=%s user=%s", rule_id, user_id)
        return log

    async def log_rule_updated(
        self,
        rule_id: str,
        rule_name: str,
        user_id: str,
        user_email: str,
        organization_id: str,
        changes: Dict[str, Any],  # {"field": {"old": x, "new": y}}
    ) -> RuleAuditLog:
        """Log a rule update with changed fields."""
        log = RuleAuditLog(
            rule_id=rule_id,
            rule_name=rule_name,
            user_id=user_id,
            user_email=user_email,
            organization_id=organization_id,
            action=RuleAuditAction.UPDATED,
            details={"updated_fields": list(changes.keys())},
            changes=changes,
        )
        self._session.add(log)
        await self._session.commit()
        await self._session.refresh(log)
        logger.info(
            "Logged rule update: rule=%s user=%s fields=%s",
            rule_id,
            user_id,
            list(changes.keys()),
        )
        return log

    async def log_rule_deleted(
        self,
        rule_id: str,
        rule_name: str,
        user_id: str,
        user_email: str,
        organization_id: str,
        rule_snapshot: Dict[str, Any],
    ) -> RuleAuditLog:
        """Log a rule deletion with final state snapshot."""
        log = RuleAuditLog(
            rule_id=rule_id,
            rule_name=rule_name,
            user_id=user_id,
            user_email=user_email,
            organization_id=organization_id,
            action=RuleAuditAction.DELETED,
            details=rule_snapshot,
        )
        self._session.add(log)
        await self._session.commit()
        await self._session.refresh(log)
        logger.info("Logged rule deletion: rule=%s user=%s", rule_id, user_id)
        return log

    async def log_rule_toggled(
        self,
        rule_id: str,
        rule_name: str,
        user_id: str,
        user_email: str,
        organization_id: str,
        enabled: bool,
    ) -> RuleAuditLog:
        """Log a rule enable/disable."""
        action = RuleAuditAction.ENABLED if enabled else RuleAuditAction.DISABLED
        log = RuleAuditLog(
            rule_id=rule_id,
            rule_name=rule_name,
            user_id=user_id,
            user_email=user_email,
            organization_id=organization_id,
            action=action,
            details={"enabled": enabled},
        )
        self._session.add(log)
        await self._session.commit()
        await self._session.refresh(log)
        logger.info("Logged rule %s: rule=%s user=%s", action.value, rule_id, user_id)
        return log

    async def query_logs(
        self,
        organization_id: str,
        rule_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[RuleAuditAction] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[RuleAuditLog], int]:
        """Query audit logs with filters."""
        query = select(RuleAuditLog).where(
            RuleAuditLog.organization_id == organization_id
        )

        if rule_id:
            query = query.where(RuleAuditLog.rule_id == rule_id)
        if user_id:
            query = query.where(RuleAuditLog.user_id == user_id)
        if action:
            query = query.where(RuleAuditLog.action == action)
        if start_time:
            query = query.where(RuleAuditLog.timestamp >= start_time.isoformat())
        if end_time:
            query = query.where(RuleAuditLog.timestamp <= end_time.isoformat())

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self._session.execute(count_query)
        total = total_result.scalar() or 0

        # Get paginated results
        query = query.order_by(RuleAuditLog.timestamp.desc())
        query = query.offset(offset).limit(limit)
        result = await self._session.execute(query)
        logs = list(result.scalars().all())

        return logs, total


__all__ = ["RuleAuditService"]
