"""REST API endpoints for alert history search."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import UserContext, require_authenticated_user
from app.core.logging import get_logger
from app.schemas.history_schemas import (
    AlertHistoryListResponse,
    AlertHistoryResponse,
    AlertHistorySearchParams,
)
from app.services.history_service import AlertHistoryService, HistoryNotFoundError

logger = get_logger("alert-engine.routes.history")

router = APIRouter(prefix="/alerts/history", tags=["history"])


@router.get(
    "",
    response_model=AlertHistoryListResponse,
    summary="Search alert history",
    description="Search alert history with filters for time range, severity, status, rule, and container.",
)
async def search_history(
    start_time: Optional[datetime] = Query(
        None, description="Filter alerts triggered after this time"
    ),
    end_time: Optional[datetime] = Query(
        None, description="Filter alerts triggered before this time"
    ),
    severity: Optional[str] = Query(
        None, description="Filter by severity: critical, warning, info"
    ),
    status: Optional[str] = Query(
        None, description="Filter by status: triggered, acknowledged, silenced"
    ),
    rule_id: Optional[str] = Query(None, description="Filter by rule ID"),
    container_id: Optional[str] = Query(
        None, description="Filter by container key host_id:container_name (from context)"
    ),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit"),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(require_authenticated_user),
) -> AlertHistoryListResponse:
    """Search alert history with comprehensive filters."""
    params = AlertHistorySearchParams(
        start_time=start_time,
        end_time=end_time,
        severity=severity,
        status=status,
        rule_id=rule_id,
        container_id=container_id,
        offset=offset,
        limit=limit,
    )

    service = AlertHistoryService(session)
    items, total = await service.search(user.organization_id, params)

    return AlertHistoryListResponse(
        items=[AlertHistoryResponse.model_validate(item) for item in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{history_id}",
    response_model=AlertHistoryResponse,
    summary="Get alert history entry",
    description="Get a single alert history entry by ID.",
)
async def get_history_entry(
    history_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(require_authenticated_user),
) -> AlertHistoryResponse:
    """Get a single alert history entry by ID."""
    service = AlertHistoryService(session)
    try:
        entry = await service.get_by_id_or_raise(history_id, user.organization_id)
    except HistoryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"History entry {history_id} not found",
        )
    return AlertHistoryResponse.model_validate(entry)


__all__ = ["router"]
