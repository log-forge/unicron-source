"""REST API endpoints for action audit log queries."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import UserContext, require_authenticated_user
from app.core.logging import get_logger
from app.schemas.audit_schemas import (
    ActionAuditLogResponse,
    AuditLogListResponse,
    AuditLogQuery,
    AuditStats,
)
from app.services.audit_service import audit_service

logger = get_logger("alert-engine.routes.audit")

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get(
    "/actions",
    response_model=AuditLogListResponse,
    summary="List action audit logs",
    description="Query action audit logs with filters for rule, container, action type, status, and time range.",
)
async def list_action_logs(
    rule_id: Optional[str] = Query(None, description="Filter by rule ID"),
    container_id: Optional[str] = Query(None, description="Filter by container ID"),
    action_type: Optional[str] = Query(
        None, description="Filter by action type: restart, stop, start, kill, etc."
    ),
    status: Optional[str] = Query(
        None, description="Filter by status: allowed, blocked, success, failed"
    ),
    start_time: Optional[datetime] = Query(
        None, description="Filter actions triggered after this time"
    ),
    end_time: Optional[datetime] = Query(
        None, description="Filter actions triggered before this time"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_session),
    current_user: UserContext = Depends(require_authenticated_user),
) -> AuditLogListResponse:
    """
    Query action audit logs with filters.

    Returns a paginated list of audit log entries matching the specified filters.
    Results are ordered by triggered_at descending (most recent first).
    """
    query = AuditLogQuery(
        rule_id=rule_id,
        container_id=container_id,
        action_type=action_type,
        status=status,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )

    logs, total = await audit_service.query_logs(session, query)

    logger.debug(
        "User %s queried audit logs: %d results of %d total",
        current_user.user_id,
        len(logs),
        total,
    )

    return AuditLogListResponse(
        items=[ActionAuditLogResponse.model_validate(log) for log in logs],
        total=total,
    )


@router.get(
    "/actions/stats",
    response_model=AuditStats,
    summary="Get action audit statistics",
    description="Get aggregate statistics for action audit logs within a time period.",
)
async def get_action_stats(
    start_time: datetime = Query(..., description="Start of the statistics period"),
    end_time: datetime = Query(..., description="End of the statistics period"),
    session: AsyncSession = Depends(get_session),
    current_user: UserContext = Depends(require_authenticated_user),
) -> AuditStats:
    """
    Get aggregate stats for action audit logs.

    Returns counts of actions by status and by action type for the specified
    time period. Useful for dashboard displays and compliance reporting.
    """
    stats = await audit_service.get_stats(session, start_time, end_time)

    logger.debug(
        "User %s retrieved audit stats: %d actions from %s to %s",
        current_user.user_id,
        stats.total_actions,
        start_time.isoformat(),
        end_time.isoformat(),
    )

    return stats


__all__ = ["router"]
