"""Pydantic schemas for alert-engine service."""

from app.schemas.action_schemas import (
    ActionCreate,
    ActionResponse,
    ActionType,
    ActionUpdate,
    ContainerActionConfig,
    NotifyActionConfig,
    RunScriptConfig,
)
from app.schemas.alert_schemas import (
    AlertAcknowledgeRequest,
    AlertListResponse,
    AlertResponse,
    AlertStatus,
)
from app.schemas.audit_schemas import (
    ActionAuditLogResponse,
    AuditLogListResponse,
    AuditLogQuery,
    AuditStats,
)
from app.schemas.common import (
    ErrorDetail,
    ErrorResponse,
    PaginatedResponse,
    SuccessResponse,
)
from app.schemas.rule_schemas import (
    AbsenceConfig,
    KeywordConfig,
    RateConfig,
    RuleCreate,
    RuleListResponse,
    RuleResponse,
    RuleUpdate,
    Severity,
    ScopeType,
    ThresholdConfig,
    TriggerType,
)
from app.schemas.history_schemas import (
    AlertHistoryListResponse,
    AlertHistoryResponse,
    AlertHistorySearchParams,
)
from app.schemas.silence_schemas import (
    MatcherSchema,
    SilenceCreateRequest,
    SilenceListResponse,
    SilenceResponse,
    SilenceUpdateRequest,
)
from app.schemas.rule_audit_schemas import (
    RuleAuditListResponse,
    RuleAuditLogResponse,
    RuleAuditQuery,
)
from app.schemas.alert_audit_schemas import (
    AlertAuditListResponse,
    AlertAuditQuery,
    AlertOperationLogResponse,
)

__all__ = [
    # Action schemas
    "ActionType",
    "ContainerActionConfig",
    "RunScriptConfig",
    "NotifyActionConfig",
    "ActionCreate",
    "ActionUpdate",
    "ActionResponse",
    # Alert schemas
    "AlertStatus",
    "AlertResponse",
    "AlertAcknowledgeRequest",
    "AlertListResponse",
    # Audit schemas
    "ActionAuditLogResponse",
    "AuditLogListResponse",
    "AuditLogQuery",
    "AuditStats",
    # Common schemas
    "ErrorDetail",
    "ErrorResponse",
    "PaginatedResponse",
    "SuccessResponse",
    # Rule schemas
    "TriggerType",
    "ScopeType",
    "Severity",
    "ThresholdConfig",
    "KeywordConfig",
    "RateConfig",
    "AbsenceConfig",
    "RuleCreate",
    "RuleUpdate",
    "RuleResponse",
    "RuleListResponse",
    # Silence schemas
    "MatcherSchema",
    "SilenceCreateRequest",
    "SilenceUpdateRequest",
    "SilenceResponse",
    "SilenceListResponse",
    # History schemas
    "AlertHistoryResponse",
    "AlertHistorySearchParams",
    "AlertHistoryListResponse",
    # Rule audit schemas
    "RuleAuditListResponse",
    "RuleAuditLogResponse",
    "RuleAuditQuery",
    # Alert audit schemas
    "AlertAuditListResponse",
    "AlertAuditQuery",
    "AlertOperationLogResponse",
]
