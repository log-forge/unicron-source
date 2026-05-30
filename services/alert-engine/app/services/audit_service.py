"""
Service for audit log operations.

Provides logging and querying of action audit entries for compliance
and debugging purposes.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.action import ActionAuditLog
from app.schemas.audit_schemas import AuditLogQuery, AuditStats

logger = get_logger("alert-engine.services.audit_service")


class AuditService:
    """
    Service for audit log operations.

    Provides methods to log action attempts and query the audit trail
    with filters for rule, container, time range, and status.
    """

    async def log_action(
        self,
        session: AsyncSession,
        rule_id: str,
        rule_name: str,
        action_type: str,
        container_id: str,
        herald_id: str,
        status: str,
        initiated_by: str,
        block_reason: Optional[str] = None,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> ActionAuditLog:
        """
        Log an action attempt to the audit trail.

        Args:
            session: Async database session.
            rule_id: ID of the alert rule that triggered the action.
            rule_name: Name of the rule at time of action.
            action_type: Type of action (restart, stop, start, kill, etc.).
            container_id: Target container ID.
            herald_id: Herald managing the container.
            status: Outcome status (allowed, blocked, success, failed).
            initiated_by: Initiator (rule_evaluation, manual, etc.).
            block_reason: Reason for blocking (if status=blocked).
            error_message: Error message (if status=failed).
            duration_ms: Execution duration in milliseconds.

        Returns:
            Created ActionAuditLog entry.
        """
        log_entry = ActionAuditLog(
            id=uuid.uuid4().hex,
            rule_id=rule_id,
            rule_name=rule_name,
            action_type=action_type,
            container_id=container_id,
            herald_id=herald_id,
            status=status,
            block_reason=block_reason,
            error_message=error_message,
            duration_ms=duration_ms,
            initiated_by=initiated_by,
            triggered_at=datetime.now(timezone.utc),
        )

        session.add(log_entry)
        await session.commit()
        await session.refresh(log_entry)

        logger.debug(
            "Logged action audit: rule=%s, action=%s, status=%s, container=%s",
            rule_id,
            action_type,
            status,
            container_id,
        )

        return log_entry

    async def query_logs(
        self,
        session: AsyncSession,
        query: AuditLogQuery,
    ) -> Tuple[List[ActionAuditLog], int]:
        """
        Query audit logs with filters.

        Args:
            session: Async database session.
            query: Query parameters for filtering.

        Returns:
            Tuple of (list of matching logs, total count).
        """
        stmt = select(ActionAuditLog)

        # Apply filters
        if query.rule_id:
            stmt = stmt.where(ActionAuditLog.rule_id == query.rule_id)
        if query.container_id:
            stmt = stmt.where(ActionAuditLog.container_id == query.container_id)
        if query.action_type:
            stmt = stmt.where(ActionAuditLog.action_type == query.action_type)
        if query.status:
            stmt = stmt.where(ActionAuditLog.status == query.status)
        if query.start_time:
            stmt = stmt.where(ActionAuditLog.triggered_at >= query.start_time)
        if query.end_time:
            stmt = stmt.where(ActionAuditLog.triggered_at <= query.end_time)

        # Count total matching records
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Apply pagination and ordering (most recent first)
        stmt = stmt.order_by(ActionAuditLog.triggered_at.desc())
        stmt = stmt.offset(query.offset).limit(query.limit)

        result = await session.execute(stmt)
        logs = list(result.scalars().all())

        logger.debug(
            "Queried audit logs: found %d of %d total matching entries",
            len(logs),
            total,
        )

        return logs, total

    async def get_stats(
        self,
        session: AsyncSession,
        start_time: datetime,
        end_time: datetime,
    ) -> AuditStats:
        """
        Get aggregate stats for a time period.

        Args:
            session: Async database session.
            start_time: Start of the statistics period.
            end_time: End of the statistics period.

        Returns:
            AuditStats with aggregated counts.
        """
        # Base filter for time period
        base_filter = (
            (ActionAuditLog.triggered_at >= start_time)
            & (ActionAuditLog.triggered_at <= end_time)
        )

        # Total count
        total_stmt = select(func.count(ActionAuditLog.id)).where(base_filter)
        total_result = await session.execute(total_stmt)
        total_actions = total_result.scalar() or 0

        # Count by status
        status_stmt = (
            select(
                ActionAuditLog.status,
                func.count(ActionAuditLog.id).label("count"),
            )
            .where(base_filter)
            .group_by(ActionAuditLog.status)
        )
        status_result = await session.execute(status_stmt)
        actions_by_status = {row.status: row.count for row in status_result.all()}

        # Count by action type
        type_stmt = (
            select(
                ActionAuditLog.action_type,
                func.count(ActionAuditLog.id).label("count"),
            )
            .where(base_filter)
            .group_by(ActionAuditLog.action_type)
        )
        type_result = await session.execute(type_stmt)
        actions_by_type = {row.action_type: row.count for row in type_result.all()}

        logger.debug(
            "Retrieved audit stats: %d actions from %s to %s",
            total_actions,
            start_time.isoformat(),
            end_time.isoformat(),
        )

        return AuditStats(
            total_actions=total_actions,
            actions_by_status=actions_by_status,
            actions_by_type=actions_by_type,
            period_start=start_time,
            period_end=end_time,
        )


# Singleton instance
audit_service = AuditService()

__all__ = ["AuditService", "audit_service"]
