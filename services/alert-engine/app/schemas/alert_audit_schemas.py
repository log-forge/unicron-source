"""Schemas for alert operation audit logs."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict

from app.models.alert_audit import AlertOperation


class AlertOperationLogResponse(BaseModel):
    """Response schema for alert operation log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    alert_id: Optional[str] = None
    alert_fingerprint: Optional[str] = None
    silence_id: Optional[str] = None
    rule_id: Optional[str] = None
    rule_name: Optional[str] = None
    container_id: Optional[str] = None
    user_id: str
    user_email: Optional[str] = None
    organization_id: str
    operation: str
    timestamp: datetime
    details: Dict[str, Any]


class AlertAuditQuery(BaseModel):
    """Query parameters for alert audit log search."""

    alert_id: Optional[str] = None
    silence_id: Optional[str] = None
    rule_id: Optional[str] = None
    user_id: Optional[str] = None
    operation: Optional[AlertOperation] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    offset: int = 0
    limit: int = 100


class AlertAuditListResponse(BaseModel):
    """Paginated list of alert operation log entries."""

    items: List[AlertOperationLogResponse]
    total: int


__all__ = [
    "AlertAuditListResponse",
    "AlertAuditQuery",
    "AlertOperationLogResponse",
]
