"""Schemas for rule audit log operations."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict

from app.models.rule_audit import RuleAuditAction


class RuleAuditLogResponse(BaseModel):
    """Response schema for rule audit log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    rule_id: str
    rule_name: str
    user_id: str
    user_email: Optional[str]
    organization_id: str
    action: RuleAuditAction
    timestamp: datetime
    details: Dict[str, Any]
    changes: Optional[Dict[str, Any]]


class RuleAuditQuery(BaseModel):
    """Query parameters for audit log search."""

    rule_id: Optional[str] = None
    user_id: Optional[str] = None
    action: Optional[RuleAuditAction] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    offset: int = 0
    limit: int = 100


class RuleAuditListResponse(BaseModel):
    """Paginated list of audit log entries."""

    items: List[RuleAuditLogResponse]
    total: int


__all__ = [
    "RuleAuditLogResponse",
    "RuleAuditQuery",
    "RuleAuditListResponse",
]
