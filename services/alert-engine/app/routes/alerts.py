"""REST API endpoints for alert management operations."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import UserContext, require_authenticated_user
from app.core.logging import get_logger
from app.schemas.alert_schemas import (
    AlertAcknowledgeRequest,
    AlertListResponse,
    AlertResponse,
)
from app.services.alert_audit_service import AlertAuditService
from app.services.state_service import (
    AlertNotFoundError,
    AlertStateService,
    InvalidStateTransitionError,
    get_active_fingerprint,
)

logger = get_logger("alert-engine.routes.alerts")

router = APIRouter(prefix="/alerts", tags=["alerts"])


# Response model for delivery status
class DeliveryStatusItem(BaseModel):
    """Delivery status for a single notification channel."""

    channel_name: str
    channel_type: str
    status: str  # pending, sent, failed, retrying
    sent_at: Optional[str] = None
    attempt_count: int


class DeliveryStatusResponse(BaseModel):
    """Delivery status for all channels of an alert."""

    items: List[DeliveryStatusItem]


@router.get(
    "",
    response_model=AlertListResponse,
    summary="List alerts",
    description="List alerts for the authenticated user's organization with optional filtering.",
)
async def list_alerts(
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
    status: Optional[str] = Query(
        None,
        description="Filter by status (firing, acknowledged)",
    ),
    severity: Optional[str] = Query(
        None,
        description="Filter by severity (critical, warning, info)",
    ),
    rule_id: Optional[str] = Query(
        None,
        description="Filter by rule ID",
    ),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=500, description="Pagination limit"),
) -> AlertListResponse:
    """List alerts for the user's organization."""
    service = AlertStateService(session)
    alerts, total = await service.list_alerts(
        org_id=user.organization_id,
        status=status,
        severity=severity,
        rule_id=rule_id,
        offset=offset,
        limit=limit,
    )
    return AlertListResponse(
        items=[AlertResponse.model_validate(a) for a in alerts],
        total=total,
    )


@router.get(
    "/search",
    response_model=AlertListResponse,
    summary="Search alerts",
    description="Search alerts by text query with optional container and severity filters.",
)
async def search_alerts(
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
    q: Optional[str] = Query(
        None,
        description="Text search query (searches message, rule name, container key)",
    ),
    container_id: Optional[str] = Query(
        None,
        description="Filter by container key host_id:container_name (exact match on labels.container_id)",
    ),
    severity: Optional[str] = Query(
        None,
        description="Filter by severity (critical, warning, info)",
    ),
    status: Optional[str] = Query(
        None,
        description="Filter by status (firing, acknowledged)",
    ),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=500, description="Pagination limit"),
) -> AlertListResponse:
    """Search alerts with full-text query and filters."""
    service = AlertStateService(session)
    alerts, total = await service.search_alerts(
        org_id=user.organization_id,
        q=q,
        container_id=container_id,
        severity=severity,
        status=status,
        offset=offset,
        limit=limit,
    )
    return AlertListResponse(
        items=[AlertResponse.model_validate(a) for a in alerts],
        total=total,
    )


@router.get(
    "/{alert_id}",
    response_model=AlertResponse,
    summary="Get alert",
    description="Get a specific alert by ID.",
)
async def get_alert(
    alert_id: str,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> AlertResponse:
    """Get a single alert by ID."""
    service = AlertStateService(session)
    try:
        alert = await service.get_alert_or_raise(alert_id, user.organization_id)
    except AlertNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found",
        )
    return AlertResponse.model_validate(alert)


@router.get(
    "/{alert_id}/delivery-status",
    response_model=DeliveryStatusResponse,
    summary="Get alert delivery status",
    description="Get notification delivery status for all channels of an alert.",
)
async def get_alert_delivery_status(
    alert_id: str,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> DeliveryStatusResponse:
    """
    Get notification delivery status for an alert.

    Queries the notifier's notification_log table to retrieve delivery
    status for each channel the alert was sent to.
    """
    # First verify the alert exists and belongs to user's org
    service = AlertStateService(session)
    try:
        await service.get_alert_or_raise(alert_id, user.organization_id)
    except AlertNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found",
        )

    # Query notification logs with channel info using raw SQL
    # (cross-service table access via shared database)
    query = text("""
        SELECT
            nl.status,
            nl.sent_at,
            nl.attempt_count,
            COALESCE(nc.label, cp.label, 'Unknown Channel') AS channel_name,
            COALESCE(nc.channel_type, cp.channel_type, 'unknown') AS channel_type
        FROM notifications.notificationlog nl
        LEFT JOIN notifications.notificationchannel nc ON nl.channel_id = nc.id
        LEFT JOIN notifications.channelpreset cp ON nl.channel_id = cp.id
        WHERE nl.alert_id = :alert_id
        ORDER BY nl.created_at ASC
    """)

    result = await session.execute(query, {"alert_id": alert_id})
    rows = result.fetchall()

    items = []
    for row in rows:
        items.append(
            DeliveryStatusItem(
                channel_name=row.channel_name,
                channel_type=row.channel_type,
                status=row.status,
                sent_at=row.sent_at.isoformat() if row.sent_at else None,
                attempt_count=row.attempt_count,
            )
        )

    return DeliveryStatusResponse(items=items)


@router.post(
    "/{alert_id}/acknowledge",
    response_model=AlertResponse,
    summary="Acknowledge alert",
    description="Acknowledge a firing alert. Prevents auto-escalation.",
)
async def acknowledge_alert(
    alert_id: str,
    body: Optional[AlertAcknowledgeRequest] = None,
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> AlertResponse:
    """Acknowledge a firing alert."""
    service = AlertStateService(session)
    comment = body.comment if body else None
    try:
        alert = await service.acknowledge_alert(
            alert_id=alert_id,
            org_id=user.organization_id,
            user_id=user.user_id,
            comment=comment,
        )
    except AlertNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found",
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot acknowledge alert: {e}",
        )

    # Log the acknowledge operation to audit trail
    audit_service = AlertAuditService(session)
    rule_name = alert.labels.get("alertname", alert.labels.get("rule_name", "unknown"))
    container_id = alert.labels.get("container_id")
    await audit_service.log_alert_acknowledged(
        alert_id=alert.id,
        alert_fingerprint=get_active_fingerprint(alert),
        rule_id=alert.rule_id,
        rule_name=rule_name,
        container_id=container_id,
        user_id=user.user_id,
        user_email=user.email,
        organization_id=user.organization_id,
        comment=comment,
    )

    logger.info("Alert %s acknowledged by user %s", alert_id, user.user_id)
    return AlertResponse.model_validate(alert)


__all__ = ["router"]
