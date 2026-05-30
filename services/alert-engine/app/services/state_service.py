"""Alert state management service for alert-engine.

Provides state transitions for alerts: firing -> acknowledged.
Two-state lifecycle only -- no resolved state.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.redis import get_redis
from app.models.alert_history import AlertHistory
from app.models.alert_state import AlertState
from app.services.dedup import DeduplicationService

logger = get_logger("alert-engine.services.state")

RETIRED_FINGERPRINT_PREFIX = "retired"


class AlertNotFoundError(Exception):
    """Raised when an alert is not found or not accessible."""

    def __init__(self, alert_id: str):
        self.alert_id = alert_id
        super().__init__(f"Alert {alert_id} not found")


class InvalidStateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, current_status: str, target_status: str):
        self.current_status = current_status
        self.target_status = target_status
        super().__init__(
            f"Cannot transition from '{current_status}' to '{target_status}'"
        )


def get_active_fingerprint(alert: AlertState) -> str:
    """Return the active dedup fingerprint for an alert."""
    annotations = alert.annotations or {}
    stored = annotations.get("dedup_fingerprint")
    if stored:
        return str(stored)

    fingerprint = str(alert.fingerprint or "")
    prefix = f"{RETIRED_FINGERPRINT_PREFIX}:"
    if fingerprint.startswith(prefix):
        parts = fingerprint.split(":", 2)
        if len(parts) >= 3:
            return parts[1]

    return fingerprint


def _build_retired_fingerprint(active_fingerprint: str, alert_id: str) -> str:
    """Build a stable archived fingerprint so new alerts can reuse the active one."""
    return f"{RETIRED_FINGERPRINT_PREFIX}:{active_fingerprint}:{alert_id}"


def retire_alert_fingerprint(alert: AlertState) -> bool:
    """
    Archive the active fingerprint on an acknowledged alert.

    This preserves the alert row for history/audit while freeing the original
    fingerprint so the same condition can create a fresh firing alert later.

    Returns:
        True if the alert row was mutated, False otherwise.
    """
    active_fingerprint = get_active_fingerprint(alert)
    if not active_fingerprint:
        return False

    annotations = dict(alert.annotations or {})
    changed = False

    if annotations.get("dedup_fingerprint") != active_fingerprint:
        annotations["dedup_fingerprint"] = active_fingerprint
        changed = True

    retired_fingerprint = _build_retired_fingerprint(active_fingerprint, alert.id)
    if alert.fingerprint != retired_fingerprint:
        alert.fingerprint = retired_fingerprint
        changed = True

    if changed:
        alert.annotations = annotations

    return changed


async def clear_dedup_fingerprint(fingerprint: str) -> None:
    """Clear the Redis dedup key for an alert fingerprint."""
    if not fingerprint:
        return

    try:
        redis = await get_redis()
        dedup = DeduplicationService(redis)
        await dedup.clear(fingerprint)
    except Exception as exc:
        logger.warning(
            "Failed to clear dedup fingerprint %s: %s",
            fingerprint,
            str(exc),
        )


class AlertStateService:
    """
    Service for managing alert state transitions.

    State transitions:
    - firing -> acknowledged: User acknowledges alert

    Two-state lifecycle only. Acknowledged alerts are never reopened;
    if the same rule fires again, a new stack is created with count=1.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize the state service.

        Args:
            session: Async database session.
        """
        self.session = session

    async def list_alerts(
        self,
        org_id: str,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        rule_id: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[AlertState], int]:
        """
        List alerts for an organization with optional filtering.

        Args:
            org_id: Organization ID for tenant isolation.
            status: Optional status filter (firing, acknowledged).
            severity: Optional severity filter.
            rule_id: Optional rule ID filter.
            offset: Pagination offset.
            limit: Pagination limit.

        Returns:
            Tuple of (list of AlertState, total count).
        """
        base_query = select(AlertState).where(AlertState.organization_id == org_id)

        if status:
            base_query = base_query.where(AlertState.status == status)
        if severity:
            base_query = base_query.where(AlertState.severity == severity)
        if rule_id:
            base_query = base_query.where(AlertState.rule_id == rule_id)

        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        query = (
            base_query.order_by(AlertState.started_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(query)
        alerts = list(result.scalars().all())

        return alerts, total

    async def search_alerts(
        self,
        org_id: str,
        q: Optional[str] = None,
        container_id: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Tuple[List[AlertState], int]:
        """
        Search alerts with text query and optional filters.

        Performs case-insensitive ILIKE search across JSONB fields:
        annotations.message, labels.alertname, labels.container_id (container key),
        and labels.rule_name.

        Args:
            org_id: Organization ID for tenant isolation.
            q: Text search query (case-insensitive).
            container_id: Optional exact-match filter on labels.container_id (container key).
            severity: Optional severity filter.
            status: Optional status filter (firing, acknowledged).
            offset: Pagination offset.
            limit: Pagination limit.

        Returns:
            Tuple of (list of AlertState, total count).
        """
        base_query = select(AlertState).where(AlertState.organization_id == org_id)

        if q and q.strip():
            q = q.strip()
            search_filter = or_(
                AlertState.annotations["message"].astext.ilike(f"%{q}%"),
                AlertState.labels["alertname"].astext.ilike(f"%{q}%"),
                AlertState.labels["container_id"].astext.ilike(f"%{q}%"),
                AlertState.labels["rule_name"].astext.ilike(f"%{q}%"),
            )
            base_query = base_query.where(search_filter)

        if container_id:
            base_query = base_query.where(
                AlertState.labels["container_id"].astext == container_id
            )
        if severity:
            base_query = base_query.where(AlertState.severity == severity)
        if status:
            base_query = base_query.where(AlertState.status == status)

        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        query = (
            base_query.order_by(AlertState.started_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(query)
        alerts = list(result.scalars().all())

        return alerts, total

    async def get_alert(
        self,
        alert_id: str,
        org_id: str,
    ) -> Optional[AlertState]:
        """
        Get a single alert by ID.

        Args:
            alert_id: Alert ID.
            org_id: Organization ID for tenant isolation.

        Returns:
            AlertState or None if not found.
        """
        query = select(AlertState).where(
            AlertState.id == alert_id,
            AlertState.organization_id == org_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_alert_or_raise(
        self,
        alert_id: str,
        org_id: str,
    ) -> AlertState:
        """
        Get alert by ID or raise AlertNotFoundError.

        Args:
            alert_id: Alert ID.
            org_id: Organization ID.

        Returns:
            AlertState.

        Raises:
            AlertNotFoundError: If alert not found.
        """
        alert = await self.get_alert(alert_id, org_id)
        if not alert:
            raise AlertNotFoundError(alert_id)
        return alert

    async def acknowledge_alert(
        self,
        alert_id: str,
        org_id: str,
        user_id: str,
        comment: Optional[str] = None,
    ) -> AlertState:
        """
        Acknowledge a firing alert.

        Args:
            alert_id: Alert ID.
            org_id: Organization ID.
            user_id: User performing acknowledgment.
            comment: Optional acknowledgment comment.

        Returns:
            Updated AlertState.

        Raises:
            AlertNotFoundError: If alert not found.
        """
        alert = await self.get_alert_or_raise(alert_id, org_id)

        if alert.status == "acknowledged":
            logger.debug("Alert %s already acknowledged", alert_id)
            if retire_alert_fingerprint(alert):
                now = datetime.now(timezone.utc)
                alert.updated_at = now
                await self.session.commit()
                await self.session.refresh(alert)
            await clear_dedup_fingerprint(get_active_fingerprint(alert))
            return alert

        now = datetime.now(timezone.utc)
        alert.status = "acknowledged"
        alert.updated_at = now

        annotations = dict(alert.annotations or {})
        annotations["acknowledged_by"] = user_id
        annotations["acknowledged_at"] = now.isoformat()
        if comment:
            annotations["acknowledge_comment"] = comment
        alert.annotations = annotations

        retire_alert_fingerprint(alert)

        labels = dict(alert.labels or {})
        history_context = {
            "alert_id": alert.id,
            "labels": labels,
            "stacked": bool(getattr(alert, "count", 1) and int(getattr(alert, "count", 1)) > 1),
            "occurrence_count": int(getattr(alert, "count", 1) or 1),
        }
        if comment:
            history_context["acknowledge_comment"] = comment
        history = AlertHistory(
            id=uuid.uuid4().hex,
            rule_id=alert.rule_id,
            rule_name=str(labels.get("rule_name") or alert.rule_id),
            severity=alert.severity,
            message=str((annotations.get("message") or "")),
            context=history_context,
            status="acknowledged",
            triggered_at=now,
            organization_id=org_id,
            acknowledged_at=now,
            acknowledged_by=user_id,
        )
        self.session.add(history)

        await self.session.commit()
        await self.session.refresh(alert)
        await clear_dedup_fingerprint(get_active_fingerprint(alert))

        logger.info(
            "Alert %s acknowledged by user %s",
            alert_id,
            user_id,
        )

        try:
            from app.services.alert_websocket import broadcast_alert_state_change

            await broadcast_alert_state_change(
                alert_id=alert_id,
                status="acknowledged",
                action="acknowledged",
                updated_at=now,
                organization_id=org_id,
            )
        except Exception as exc:
            logger.warning(
                "Failed to broadcast acknowledge for alert %s: %s",
                alert_id,
                str(exc),
            )

        return alert


__all__ = [
    "AlertNotFoundError",
    "AlertStateService",
    "clear_dedup_fingerprint",
    "get_active_fingerprint",
    "InvalidStateTransitionError",
    "retire_alert_fingerprint",
]
