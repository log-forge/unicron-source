"""Pydantic schemas for action audit API."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ActionAuditLogResponse(BaseModel):
    """Schema for a single action audit log entry."""

    id: str = Field(..., description="Unique identifier for the audit log entry")
    rule_id: str = Field(..., description="Reference to the alert rule")
    rule_name: str = Field(..., description="Denormalized rule name at time of action")
    action_type: str = Field(
        ..., description="Action type: restart, stop, start, kill, run_script, notify"
    )
    container_id: str = Field(..., description="Target container ID")
    herald_id: str = Field(..., description="Herald managing the container")
    status: str = Field(
        ..., description="Outcome: allowed, blocked, success, failed"
    )
    block_reason: Optional[str] = Field(
        None, description="Reason for blocking (if status=blocked)"
    )
    error_message: Optional[str] = Field(
        None, description="Error message (if status=failed)"
    )
    duration_ms: Optional[int] = Field(
        None, description="Execution duration in milliseconds"
    )
    initiated_by: str = Field(
        ..., description="Initiator: rule_evaluation, manual, etc."
    )
    triggered_at: datetime = Field(
        ..., description="Timestamp when the action was triggered"
    )

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    """Paginated list response for audit logs."""

    items: List[ActionAuditLogResponse] = Field(
        ..., description="List of audit log entries"
    )
    total: int = Field(..., description="Total number of matching entries")


class AuditLogQuery(BaseModel):
    """Query parameters for filtering audit logs."""

    rule_id: Optional[str] = Field(None, description="Filter by rule ID")
    container_id: Optional[str] = Field(None, description="Filter by container ID")
    action_type: Optional[str] = Field(
        None, description="Filter by action type: restart, stop, start, kill, etc."
    )
    status: Optional[str] = Field(
        None, description="Filter by status: allowed, blocked, success, failed"
    )
    start_time: Optional[datetime] = Field(
        None, description="Filter actions triggered after this time"
    )
    end_time: Optional[datetime] = Field(
        None, description="Filter actions triggered before this time"
    )
    limit: int = Field(100, ge=1, le=1000, description="Pagination limit")
    offset: int = Field(0, ge=0, description="Pagination offset")


class AuditStats(BaseModel):
    """Aggregate statistics for action audit logs."""

    total_actions: int = Field(..., description="Total number of actions in period")
    actions_by_status: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of actions by status (allowed, blocked, success, failed)",
    )
    actions_by_type: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of actions by type (restart, stop, start, kill, etc.)",
    )
    period_start: datetime = Field(..., description="Start of the statistics period")
    period_end: datetime = Field(..., description="End of the statistics period")


__all__ = [
    "ActionAuditLogResponse",
    "AuditLogListResponse",
    "AuditLogQuery",
    "AuditStats",
]
