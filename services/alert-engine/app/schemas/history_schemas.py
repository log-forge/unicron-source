"""Pydantic schemas for alert history API."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AlertHistoryResponse(BaseModel):
    """Schema for a single alert history entry."""

    id: str = Field(..., description="Unique identifier for the history entry")
    rule_id: str = Field(..., description="Reference to the alert rule that triggered")
    rule_name: str = Field(..., description="Denormalized rule name at time of trigger")
    severity: str = Field(..., description="Alert severity: critical, warning, info")
    message: str = Field(..., description="Alert message with template variables expanded")
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Alert context: container ID, labels, metric values, log excerpts",
    )
    status: str = Field(
        ...,
        description="Alert status: triggered, acknowledged, silenced",
    )
    triggered_at: datetime = Field(
        ..., description="Timestamp when the alert was triggered"
    )
    acknowledged_at: Optional[datetime] = Field(
        None, description="Timestamp when the alert was acknowledged"
    )
    acknowledged_by: Optional[str] = Field(
        None, description="User ID who acknowledged the alert"
    )
    organization_id: str = Field(
        ..., description="Organization ID for multi-tenant isolation"
    )

    model_config = {"from_attributes": True}


class AlertHistorySearchParams(BaseModel):
    """Search parameters for filtering alert history."""

    start_time: Optional[datetime] = Field(
        None, description="Filter alerts triggered after this time"
    )
    end_time: Optional[datetime] = Field(
        None, description="Filter alerts triggered before this time"
    )
    severity: Optional[str] = Field(
        None, description="Filter by severity: critical, warning, info"
    )
    status: Optional[str] = Field(
        None, description="Filter by status: triggered, acknowledged, silenced"
    )
    rule_id: Optional[str] = Field(None, description="Filter by rule ID")
    container_id: Optional[str] = Field(
        None, description="Filter by container key host_id:container_name (from context JSONB)"
    )
    offset: int = Field(0, ge=0, description="Pagination offset")
    limit: int = Field(100, ge=1, le=1000, description="Pagination limit")


class AlertHistoryListResponse(BaseModel):
    """Paginated list response for alert history."""

    items: List[AlertHistoryResponse] = Field(
        ..., description="List of alert history entries"
    )
    total: int = Field(..., description="Total number of matching entries")
    offset: int = Field(..., description="Current offset")
    limit: int = Field(..., description="Current limit")


__all__ = [
    "AlertHistoryResponse",
    "AlertHistorySearchParams",
    "AlertHistoryListResponse",
]
