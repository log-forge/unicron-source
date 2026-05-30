"""Service layer for alert-engine business logic."""

from app.services.action_executor import ActionExecutor, ActionResult, action_executor
from app.services.action_gatekeeper import ActionGatekeeper, gatekeeper
from app.services.action_service import ActionNotFoundError, ActionService, action_service
from app.services.audit_service import AuditService, audit_service
from app.services.history_service import (
    AlertHistory,
    AlertHistoryCreate,
    AlertHistoryService,
    HistoryNotFoundError,
)
from app.services.dedup import (
    DEFAULT_DEDUP_WINDOW_SECONDS,
    DeduplicationService,
    generate_fingerprint,
)
from app.services.evaluator import EvaluationResult, RuleEvaluator
from app.services.grouping import AlertGroup, AlertGrouper
from app.services.silence_service import (
    Silence,
    SilenceNotFoundError,
    SilenceService,
)
from app.services.state_service import (
    AlertNotFoundError,
    AlertStateService,
    InvalidStateTransitionError,
)
from app.services.trigger_service import AlertTriggerService
from app.services.victoria_client import (
    VictoriaLogsClient,
    VictoriaQueryError,
    victoria_logs_client,
)
from app.services.victoria_metrics_client import (
    VictoriaMetricsClient,
    VictoriaMetricsQueryError,
    victoria_metrics_client,
)
from app.services.rule_audit_service import RuleAuditService
from app.services.alert_audit_service import AlertAuditService

__all__ = [
    "ActionExecutor",
    "ActionGatekeeper",
    "ActionNotFoundError",
    "ActionResult",
    "ActionService",
    "AlertGroup",
    "AlertGrouper",
    "AlertHistory",
    "AlertHistoryCreate",
    "AlertHistoryService",
    "AlertNotFoundError",
    "AlertStateService",
    "AlertTriggerService",
    "AuditService",
    "DEFAULT_DEDUP_WINDOW_SECONDS",
    "DeduplicationService",
    "EvaluationResult",
    "HistoryNotFoundError",
    "InvalidStateTransitionError",
    "RuleEvaluator",
    "Silence",
    "SilenceNotFoundError",
    "SilenceService",
    "VictoriaLogsClient",
    "VictoriaMetricsClient",
    "VictoriaMetricsQueryError",
    "VictoriaQueryError",
    "action_executor",
    "action_service",
    "audit_service",
    "gatekeeper",
    "generate_fingerprint",
    "victoria_logs_client",
    "victoria_metrics_client",
    "RuleAuditService",
    "AlertAuditService",
]
