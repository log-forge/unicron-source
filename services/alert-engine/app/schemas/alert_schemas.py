"""Pydantic schemas for alert API operations."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AlertStatus(str, Enum):
    """Alert status states (two-state lifecycle)."""

    FIRING = "firing"
    ACKNOWLEDGED = "acknowledged"


class AlertResponse(BaseModel):
    """Schema for alert in API responses."""

    id: str = Field(..., description="Alert unique identifier")
    rule_id: str = Field(..., description="Associated rule ID")
    fingerprint: str = Field(..., description="Deduplication fingerprint")
    status: AlertStatus = Field(..., description="Current alert status")
    severity: str = Field(..., description="Alert severity level")
    labels: Dict[str, str] = Field(
        default_factory=dict, description="Alert labels"
    )
    annotations: Dict[str, Any] = Field(
        default_factory=dict, description="Alert annotations"
    )
    value: Optional[str] = Field(None, description="Value that triggered alert")
    started_at: datetime = Field(..., description="When alert started firing")
    ends_at: Optional[datetime] = Field(None, description="Expected end time")
    updated_at: datetime = Field(..., description="Last update timestamp")
    organization_id: str = Field(..., description="Organization ID")

    # Stacking fields
    count: int = Field(default=1, description="Number of times this alert has fired (stacking count)")
    first_seen: datetime = Field(..., description="When the alert first fired")
    last_seen: datetime = Field(..., description="When the alert last fired")
    stacking_key: str = Field(default="", description="Stacking key for dedup grouping")
    last_trigger_context: Optional[Dict[str, Any]] = Field(
        None, description="Context from most recent trigger"
    )

    model_config = {"from_attributes": True}


class AlertAcknowledgeRequest(BaseModel):
    """Request body for acknowledging an alert."""

    comment: Optional[str] = Field(
        None,
        max_length=1000,
        description="Optional comment for acknowledgment",
    )

    model_config = {"extra": "forbid"}


class AlertListResponse(BaseModel):
    """Paginated list of alerts."""

    items: List[AlertResponse] = Field(..., description="List of alerts")
    total: int = Field(..., description="Total count of matching alerts")


__all__ = [
    "AlertStatus",
    "AlertResponse",
    "AlertAcknowledgeRequest",
    "AlertListResponse",
]
