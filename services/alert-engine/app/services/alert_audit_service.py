"""
Service for alert operation audit logging and queries.

Logs alert acknowledge, resolve, and silence operations with user context
for compliance and debugging purposes.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_audit import AlertOperation, AlertOperationLog

logger = logging.getLogger("alert-engine.services.alert_audit")


class AlertAuditService:
    """Service for alert operation audit logging and queries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def log_alert_acknowledged(
        self,
        alert_id: str,
        alert_fingerprint: str,
        rule_id: str,
        rule_name: str,
        container_id: Optional[str],
        user_id: str,
        user_email: str,
        organization_id: str,
        comment: Optional[str] = None,
    ) -> AlertOperationLog:
        """Log an alert acknowledgment."""
        log = AlertOperationLog(
            alert_id=alert_id,
            alert_fingerprint=alert_fingerprint,
            rule_id=rule_id,
            rule_name=rule_name,
            container_id=container_id,
            user_id=user_id,
            user_email=user_email,
            organization_id=organization_id,
            operation=AlertOperation.ACKNOWLEDGED.value,
            details={"comment": comment} if comment else {},
        )
        self._session.add(log)
        await self._session.commit()
        await self._session.refresh(log)
        logger.info("Logged alert acknowledge: alert=%s user=%s", alert_id, user_id)
        return log

    async def log_alert_resolved(
        self,
        alert_id: str,
        alert_fingerprint: str,
        rule_id: str,
        rule_name: str,
        container_id: Optional[str],
        user_id: str,
        user_email: str,
        organization_id: str,
        resolution_note: Optional[str] = None,
    ) -> AlertOperationLog:
        """Log an alert resolution."""
        log = AlertOperationLog(
            alert_id=alert_id,
            alert_fingerprint=alert_fingerprint,
            rule_id=rule_id,
            rule_name=rule_name,
            container_id=container_id,
            user_id=user_id,
            user_email=user_email,
            organization_id=organization_id,
            operation=AlertOperation.RESOLVED.value,
            details={"resolution_note": resolution_note} if resolution_note else {},
        )
        self._session.add(log)
        await self._session.commit()
        await self._session.refresh(log)
        logger.info("Logged alert resolve: alert=%s user=%s", alert_id, user_id)
        return log

    async def log_silence_created(
        self,
        silence_id: str,
        user_id: str,
        user_email: str,
        organization_id: str,
        matchers: List[Dict[str, Any]],
        starts_at: datetime,
        ends_at: datetime,
        comment: Optional[str] = None,
    ) -> AlertOperationLog:
        """Log silence creation."""
        log = AlertOperationLog(
            silence_id=silence_id,
            user_id=user_id,
            user_email=user_email,
            organization_id=organization_id,
            operation=AlertOperation.SILENCE_CREATED.value,
            details={
                "matchers": matchers,
                "starts_at": starts_at.isoformat(),
                "ends_at": ends_at.isoformat(),
                "comment": comment,
            },
        )
        self._session.add(log)
        await self._session.commit()
        await self._session.refresh(log)
        logger.info("Logged silence creation: silence=%s user=%s", silence_id, user_id)
        return log

    async def log_silence_updated(
        self,
        silence_id: str,
        user_id: str,
        user_email: str,
        organization_id: str,
        changes: Dict[str, Any],
    ) -> AlertOperationLog:
        """Log silence update."""
        log = AlertOperationLog(
            silence_id=silence_id,
            user_id=user_id,
            user_email=user_email,
            organization_id=organization_id,
            operation=AlertOperation.SILENCE_UPDATED.value,
            details={"changes": changes},
        )
        self._session.add(log)
        await self._session.commit()
        await self._session.refresh(log)
        logger.info("Logged silence update: silence=%s user=%s", silence_id, user_id)
        return log

    async def log_silence_deleted(
        self,
        silence_id: str,
        user_id: str,
        user_email: str,
        organization_id: str,
        silence_snapshot: Dict[str, Any],
    ) -> AlertOperationLog:
        """Log silence deletion."""
        log = AlertOperationLog(
            silence_id=silence_id,
            user_id=user_id,
            user_email=user_email,
            organization_id=organization_id,
            operation=AlertOperation.SILENCE_DELETED.value,
            details=silence_snapshot,
        )
        self._session.add(log)
        await self._session.commit()
        await self._session.refresh(log)
        logger.info("Logged silence deletion: silence=%s user=%s", silence_id, user_id)
        return log

    async def log_silence_expired(
        self,
        silence_id: str,
        user_id: str,
        user_email: str,
        organization_id: str,
    ) -> AlertOperationLog:
        """Log silence expiration."""
        log = AlertOperationLog(
            silence_id=silence_id,
            user_id=user_id,
            user_email=user_email,
            organization_id=organization_id,
            operation=AlertOperation.SILENCE_EXPIRED.value,
            details={},
        )
        self._session.add(log)
        await self._session.commit()
        await self._session.refresh(log)
        logger.info("Logged silence expiration: silence=%s user=%s", silence_id, user_id)
        return log

    async def query_logs(
        self,
        organization_id: str,
        alert_id: Optional[str] = None,
        silence_id: Optional[str] = None,
        rule_id: Optional[str] = None,
        user_id: Optional[str] = None,
        operation: Optional[AlertOperation] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[AlertOperationLog], int]:
        """Query alert operation logs with filters."""
        query = select(AlertOperationLog).where(
            AlertOperationLog.organization_id == organization_id
        )

        if alert_id:
            query = query.where(AlertOperationLog.alert_id == alert_id)
        if silence_id:
            query = query.where(AlertOperationLog.silence_id == silence_id)
        if rule_id:
            query = query.where(AlertOperationLog.rule_id == rule_id)
        if user_id:
            query = query.where(AlertOperationLog.user_id == user_id)
        if operation:
            query = query.where(AlertOperationLog.operation == operation.value)
        if start_time:
            query = query.where(AlertOperationLog.timestamp >= start_time.isoformat())
        if end_time:
            query = query.where(AlertOperationLog.timestamp <= end_time.isoformat())

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self._session.execute(count_query)
        total = total_result.scalar() or 0

        # Get paginated results
        query = query.order_by(AlertOperationLog.timestamp.desc())
        query = query.offset(offset).limit(limit)
        result = await self._session.execute(query)
        logs = list(result.scalars().all())

        return logs, total


__all__ = ["AlertAuditService"]
