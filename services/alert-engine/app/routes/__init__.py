"""API routes for alert-engine service."""

from app.routes.alert_audit import router as alert_audit_router
from app.routes.alerts import router as alerts_router
from app.routes.audit import router as audit_router
from app.routes.containers import router as containers_router
from app.routes.gatekeeper import router as gatekeeper_router
from app.routes.groups import router as groups_router
from app.routes.history import router as history_router
from app.routes.keyword_settings import router as keyword_settings_router
from app.routes.notification_targets import router as notification_targets_router
from app.routes.notifications import router as notifications_router
from app.routes.rule_audit import router as rule_audit_router
from app.routes.rules import router as rules_router
from app.routes.silences import router as silences_router
from app.routes.settings import router as settings_router
from app.routes.templates import router as templates_router

__all__ = [
    "alert_audit_router",
    "alerts_router",
    "audit_router",
    "containers_router",
    "gatekeeper_router",
    "groups_router",
    "history_router",
    "keyword_settings_router",
    "notification_targets_router",
    "notifications_router",
    "rule_audit_router",
    "rules_router",
    "settings_router",
    "silences_router",
    "templates_router",
]
