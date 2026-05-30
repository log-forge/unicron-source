"""REST API endpoints for alert operation audit log queries."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import UserContext, require_authenticated_user
from app.models.alert_audit import AlertOperation
from app.schemas.alert_audit_schemas import (
    AlertAuditListResponse,
    AlertOperationLogResponse,
)
from app.services.alert_audit_service import AlertAuditService

router = APIRouter(prefix="/alerts/audit", tags=["alert-audit"])


@router.get(
    "",
    response_model=AlertAuditListResponse,
    summary="Query alert operation audit logs",
    description="Query audit logs for alert operations (acknowledge, resolve, silence changes).",
)
async def query_alert_audit_logs(
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
    alert_id: Optional[str] = Query(None, description="Filter by alert ID"),
    silence_id: Optional[str] = Query(None, description="Filter by silence ID"),
    rule_id: Optional[str] = Query(None, description="Filter by rule ID"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    operation: Optional[AlertOperation] = Query(None, description="Filter by operation type"),
    start_time: Optional[datetime] = Query(None, description="Filter logs after this time"),
    end_time: Optional[datetime] = Query(None, description="Filter logs before this time"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=500, description="Pagination limit"),
) -> AlertAuditListResponse:
    """Query alert operation audit logs for the user's organization."""
    service = AlertAuditService(session)
    logs, total = await service.query_logs(
        organization_id=user.organization_id,
        alert_id=alert_id,
        silence_id=silence_id,
        rule_id=rule_id,
        user_id=user_id,
        operation=operation,
        start_time=start_time,
        end_time=end_time,
        offset=offset,
        limit=limit,
    )
    return AlertAuditListResponse(
        items=[AlertOperationLogResponse.model_validate(log) for log in logs],
        total=total,
    )


__all__ = ["router"]
