"""REST API endpoints for rule audit log queries."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import UserContext, require_authenticated_user
from app.models.rule_audit import RuleAuditAction
from app.schemas.rule_audit_schemas import (
    RuleAuditListResponse,
    RuleAuditLogResponse,
)
from app.services.rule_audit_service import RuleAuditService

router = APIRouter(prefix="/rules/audit", tags=["rule-audit"])


@router.get(
    "",
    response_model=RuleAuditListResponse,
    summary="Query rule audit logs",
    description="Query rule audit logs for the authenticated user's organization.",
)
async def query_rule_audit_logs(
    user: UserContext = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
    rule_id: Optional[str] = Query(None, description="Filter by rule ID"),
    user_id: Optional[str] = Query(None, description="Filter by user ID who made the change"),
    action: Optional[RuleAuditAction] = Query(None, description="Filter by action type"),
    start_time: Optional[datetime] = Query(None, description="Filter by start time"),
    end_time: Optional[datetime] = Query(None, description="Filter by end time"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=500, description="Pagination limit"),
) -> RuleAuditListResponse:
    """Query rule audit logs for the user's organization."""
    service = RuleAuditService(session)
    logs, total = await service.query_logs(
        organization_id=user.organization_id,
        rule_id=rule_id,
        user_id=user_id,
        action=action,
        start_time=start_time,
        end_time=end_time,
        offset=offset,
        limit=limit,
    )
    return RuleAuditListResponse(
        items=[RuleAuditLogResponse.model_validate(log) for log in logs],
        total=total,
    )


__all__ = ["router"]
